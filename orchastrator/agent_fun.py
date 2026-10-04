import asyncio
import json
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from llm_client import generate_answer
from logs import new_request_id, write_event
from routing_engine.decision import classify_user_intent

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROMPT_DIR = PROJECT_ROOT / "agents"
_mcp_session: ClientSession | None = None


@asynccontextmanager
async def open_mcp_session() -> AsyncIterator[ClientSession]:
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "orchastrator.server_fun"],
        cwd=PROJECT_ROOT,
    )
    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            yield session


async def execute_tool(
    tool_name: str,
    query: str,
    latitude: float | None = None,
    longitude: float | None = None,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if _mcp_session is None:
        raise RuntimeError("MCP session is not connected")

    parameters = parameters or {}
    coordinates = parameters.get("weather_coords")
    if isinstance(coordinates, list) and len(coordinates) == 2:
        latitude, longitude = coordinates
    city = parameters.get("city")
    if isinstance(city, str) and city.strip() and not coordinates:
        weather_arguments = {
            "city": city,
            "country_code": parameters.get("country_code"),
        }
    elif latitude is not None and longitude is not None:
        weather_arguments = {"lat": latitude, "lon": longitude}
    else:
        weather_arguments = None

    tool_calls = {
        "dog_tool": (
            "get_dog_image",
            {"breed": parameters.get("dog_breed") or ""},
        ),
        "weather_tool": ("get_weather", weather_arguments),
        "books_tool": (
            "search_library_books",
            {"search_query": parameters.get("book_topic") or query},
        ),
        "joke_tool": ("get_joke", {}),
    }

    if tool_name not in tool_calls:
        return {"tool": tool_name, "status": "skipped", "output": "Unknown tool"}

    mcp_tool_name, arguments = tool_calls[tool_name]
    if tool_name == "weather_tool" and arguments is None:
        return {
            "tool": tool_name,
            "status": "needs_input",
            "arguments": {},
            "output": "Tell me a city or provide both latitude and longitude for the weather lookup.",
        }

    started = time.perf_counter()

    try:
        result = await _mcp_session.call_tool(mcp_tool_name, arguments)
        output = "\n".join(
            block.text
            for block in result.content
            if getattr(block, "text", None) is not None
        )
        return {
            "tool": tool_name,
            "status": "error" if getattr(result, "isError", False) else "success",
            "arguments": arguments,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "output": output or "Tool returned no text.",
        }
    except Exception as exc:
        return {
            "tool": tool_name,
            "status": "error",
            "arguments": arguments,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "output": str(exc),
        }


async def process_user_query(
    user_query: str,
    latitude: float | None = None,
    longitude: float | None = None,
    request_id: str | None = None,
    request_name: str = "cli.user_query",
) -> dict[str, Any]:
    request_id = request_id or new_request_id()
    started = time.perf_counter()
    write_event(
        request_id,
        request_name,
        "request_received",
        query=user_query,
        latitude=latitude,
        longitude=longitude,
    )

    try:
        router_started = time.perf_counter()
        routing = await classify_user_intent(user_query)
        router_ms = round((time.perf_counter() - router_started) * 1000, 2)
        executable_tools = routing.get("executable_tools", [])
        banned_tools = routing.get("guardrail_banned_tools", [])
        blocked_tools = routing.get("blocked_due_to_guardrail", [])
        detected_intents = routing.get("detected_intents", [])
        parameters = routing.get("parameters", {})
        write_event(
            request_id,
            request_name,
            "decision_made",
            detected_intents=detected_intents,
            executable_tools=executable_tools,
            banned_tools=banned_tools,
            blocked_tools=blocked_tools,
            primary_tool=routing.get("primary_tool", "no_tool"),
            confidence=routing.get("confidence", 0.0),
            confidence_source=routing.get("confidence_source", "unknown"),
            classifier_provider=routing.get("classifier_provider"),
            classifier_fallback=routing.get("classifier_fallback"),
            parameters=parameters,
            router_ms=router_ms,
        )

        tools_started = time.perf_counter()
        tool_results = await asyncio.gather(
            *(
                execute_tool(tool, user_query, latitude, longitude, parameters)
                for tool in executable_tools
            )
        ) if executable_tools else []
        tool_wall_ms = round((time.perf_counter() - tools_started) * 1000, 2)

        for tool_result in tool_results:
            write_event(
                request_id,
                request_name,
                "tool_completed",
                **tool_result,
            )

        system_prompt = "\n\n".join(
            (PROMPT_DIR / filename).read_text(encoding="utf-8")
            for filename in ("systemprompt.md", "guardrails.md")
        )
        user_prompt_template = (PROMPT_DIR / "user_prompt.md").read_text(
            encoding="utf-8"
        )
        user_prompt = user_prompt_template.format(
            user_query=user_query,
            detected_intents=json.dumps(detected_intents, ensure_ascii=False),
            executable_tools=json.dumps(executable_tools, ensure_ascii=False),
            banned_tools=json.dumps(banned_tools, ensure_ascii=False),
            tool_outputs=json.dumps(tool_results, ensure_ascii=False, indent=2)
            if tool_results
            else "No tools were run.",
        )

        synthesis_started = time.perf_counter()
        reply, provider, fallback_reason = await generate_answer(
            system_prompt,
            user_prompt,
        )
        synthesis_ms = round((time.perf_counter() - synthesis_started) * 1000, 2)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        timing = {
            "total_ms": elapsed_ms,
            "router_ms": router_ms,
            "tool_wall_ms": tool_wall_ms,
            "tool_calls_ms": round(
                sum(item.get("latency_ms", 0.0) for item in tool_results), 2
            ),
            "synthesis_ms": synthesis_ms,
        }
        if fallback_reason:
            write_event(
                request_id,
                request_name,
                "provider_fallback",
                reason=fallback_reason,
                selected_provider=provider,
            )

        response = {
            "query": user_query,
            "detected_intents": detected_intents,
            "parameters": parameters,
            "classifier_provider": routing.get("classifier_provider"),
            "classifier_fallback": routing.get("classifier_fallback"),
            "confidence": routing.get("confidence"),
            "confidence_source": routing.get("confidence_source", "unknown"),
            "executable_tools": executable_tools,
            "banned_tools": banned_tools,
            "tool_results": tool_results,
            "reply": reply,
            "provider": provider,
            "request_id": request_id,
            "timing": timing,
        }
        write_event(
            request_id,
            request_name,
            "request_completed",
            provider=provider,
            fallback_reason=fallback_reason,
            **timing,
            response=reply,
        )
        return response
    except Exception as exc:
        write_event(
            request_id,
            request_name,
            "request_failed",
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise


async def main() -> None:
    global _mcp_session

    async with open_mcp_session() as session:
        _mcp_session = session
        try:
            while True:
                user_query = input("\nYou: ").strip()
                if user_query.lower() in {"exit", "quit"}:
                    break
                if not user_query:
                    continue

                result = await process_user_query(user_query)
                print(f"\nTools: {result['executable_tools']}")
                print(f"Provider: {result['provider']} · Request: {result['request_id']}")
                print(f"Reply:\n{result['reply']}")
        finally:
            _mcp_session = None


if __name__ == "__main__":
    asyncio.run(main())