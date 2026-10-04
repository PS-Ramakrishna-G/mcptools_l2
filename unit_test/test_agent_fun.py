from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from orchastrator import agent_fun


@pytest.mark.asyncio
async def test_execute_tool_requires_mcp_session(monkeypatch):
    monkeypatch.setattr(agent_fun, "_mcp_session", None)

    with pytest.raises(RuntimeError, match="MCP session is not connected"):
        await agent_fun.execute_tool("dog_tool", "show a dog")


@pytest.mark.asyncio
async def test_execute_tool_calls_mcp_and_returns_text(monkeypatch):
    session = SimpleNamespace(
        call_tool=AsyncMock(
            return_value=SimpleNamespace(
                content=[SimpleNamespace(text="Dog image URL: https://example.test/dog.jpg")],
                isError=False,
            )
        )
    )
    monkeypatch.setattr(agent_fun, "_mcp_session", session)

    result = await agent_fun.execute_tool("dog_tool", "show a dog")

    assert result["status"] == "success"
    assert "dog.jpg" in result["output"]
    assert result["latency_ms"] >= 0
    session.call_tool.assert_awaited_once_with("get_dog_image", {})


@pytest.mark.asyncio
async def test_execute_tool_reports_mcp_errors(monkeypatch):
    session = SimpleNamespace(call_tool=AsyncMock(side_effect=RuntimeError("offline")))
    monkeypatch.setattr(agent_fun, "_mcp_session", session)

    result = await agent_fun.execute_tool("weather_tool", "weather")

    assert result["status"] == "error"
    assert result["output"] == "offline"


@pytest.mark.asyncio
async def test_process_user_query_returns_without_tools(monkeypatch):
    monkeypatch.setattr(
        agent_fun,
        "make_decision",
        lambda query: {
            "executable_tools": [],
            "guardrail_banned_tools": ["weather_tool"],
            "blocked_due_to_guardrail": ["weather_tool"],
        },
    )
    execute_tool = AsyncMock()
    monkeypatch.setattr(agent_fun, "execute_tool", execute_tool)

    result = await agent_fun.process_user_query("no weather")

    assert result["tool_results"] == []
    assert "weather_tool" in result["reply"]
    execute_tool.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_user_query_executes_each_allowed_tool(monkeypatch):
    monkeypatch.setattr(
        agent_fun,
        "make_decision",
        lambda query: {
            "executable_tools": ["dog_tool", "books_tool"],
            "guardrail_banned_tools": ["weather_tool"],
            "blocked_due_to_guardrail": ["weather_tool"],
        },
    )
    execute_tool = AsyncMock(
        side_effect=lambda tool, query: {
            "tool": tool,
            "output": f"result for {tool}",
        }
    )
    monkeypatch.setattr(agent_fun, "execute_tool", execute_tool)

    result = await agent_fun.process_user_query("dog and books, no weather")

    assert [item["tool"] for item in result["tool_results"]] == [
        "dog_tool",
        "books_tool",
    ]
    assert "weather_tool" in result["banned_tools"]
    assert "result for dog_tool" in result["reply"]
    assert execute_tool.await_count == 2