import math
import re
from pathlib import Path
from typing import Any

from llm_client import classify_json
from routing_engine.guardrail_engine import (
    TOOL_INTENTS,
    extract_guardrail_negations,
    parse_and_route,
)

ROUTER_PROMPT_PATH = Path(__file__).resolve().parents[1] / "agents" / "router_prompt.md"


def _validated_confidence(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("Qwen confidence must be a number")
    try:
        confidence = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Qwen confidence must be a number") from exc
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        raise ValueError("Qwen confidence must be between 0.0 and 1.0")
    return confidence


def make_decision(user_query: str) -> dict[str, Any]:
    """Return all allowed tools and the highest-confidence allowed intent."""
    routing = parse_and_route(user_query)
    executable_tools = routing.get("executable_tools", [])
    eligible_decisions = [
        item
        for item in routing.get("clause_decisions", [])
        if item.get("tool") in executable_tools
    ]

    if eligible_decisions:
        primary = max(eligible_decisions, key=lambda item: item["score"])
        primary_tool = primary["tool"]
        confidence = float(primary["score"])
    else:
        primary_tool = "no_tool"
        confidence = 0.0

    return {
        **routing,
        "primary_tool": primary_tool,
        "confidence": confidence,
    }


def system_one_decision(user_query: str) -> tuple[str, float]:
    """Return the top allowed tool and confidence for the benchmark runner."""
    decision = make_decision(user_query)
    return decision["primary_tool"], decision["confidence"]


def _validated_parameters(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}

    params: dict[str, Any] = {}
    coordinates = value.get("weather_coords")
    if isinstance(coordinates, (list, tuple)) and len(coordinates) == 2:
        try:
            latitude, longitude = map(float, coordinates)
        except (TypeError, ValueError):
            pass
        else:
            if (
                math.isfinite(latitude)
                and math.isfinite(longitude)
                and -90 <= latitude <= 90
                and -180 <= longitude <= 180
            ):
                params["weather_coords"] = [latitude, longitude]

    city = value.get("city")
    if isinstance(city, str) and city.strip():
        params["city"] = city.strip()[:120]

    country_code = value.get("country_code")
    if isinstance(country_code, str) and re.fullmatch(r"[A-Za-z]{2}", country_code.strip()):
        params["country_code"] = country_code.strip().upper()

    book_topic = value.get("book_topic")
    if isinstance(book_topic, str) and book_topic.strip():
        params["book_topic"] = book_topic.strip()[:160]

    dog_breed = value.get("dog_breed")
    if isinstance(dog_breed, str) and re.fullmatch(
        r"[a-zA-Z]+(?:[-/][a-zA-Z]+)*", dog_breed.strip()
    ):
        params["dog_breed"] = dog_breed.strip().lower()

    return params


async def classify_user_intent(user_query: str) -> dict[str, Any]:
    """Add local Qwen intent/parameter extraction, with existing routing as fallback."""
    try:
        system_prompt = ROUTER_PROMPT_PATH.read_text(encoding="utf-8")
        parsed = await classify_json(system_prompt, user_query)

        selected = parsed.get("selected_tools", [])
        model_banned = parsed.get("banned_tools", [])
        if not isinstance(selected, list) or not isinstance(model_banned, list):
            raise ValueError("Qwen intent response has invalid tool lists")

        known_tools = set(TOOL_INTENTS)
        selected_tools = {item for item in selected if item in known_tools}
        banned_tools = set(extract_guardrail_negations(user_query))
        banned_tools.update(item for item in model_banned if item in known_tools)
        detected_intents = selected_tools
        executable_tools = [
            tool
            for tool in TOOL_INTENTS
            if tool in selected_tools and tool not in banned_tools
        ]
        ordered_banned = [tool for tool in TOOL_INTENTS if tool in banned_tools]
        ordered_detected = [tool for tool in TOOL_INTENTS if tool in detected_intents]
        blocked_tools = [tool for tool in TOOL_INTENTS if tool in detected_intents & banned_tools]
        primary_tool = executable_tools[0] if executable_tools else "no_tool"
        raw_confidence = parsed.get("confidence")
        if raw_confidence is None:
            confidence = make_decision(user_query)["confidence"]
            confidence_source = "embedding_similarity_fallback"
        else:
            confidence = _validated_confidence(raw_confidence)
            confidence_source = "qwen_self_estimate"

        return {
            "original_prompt": user_query,
            "clause_decisions": [],
            "detected_intents": ordered_detected,
            "executable_tools": executable_tools,
            "guardrail_banned_tools": ordered_banned,
            "blocked_due_to_guardrail": blocked_tools,
            "primary_tool": primary_tool,
            "confidence": confidence,
            "confidence_source": confidence_source,
            "parameters": _validated_parameters(parsed.get("parameters")),
            "is_help_or_greeting": parsed.get("is_help_or_greeting") is True,
            "is_general_chat": not executable_tools,
            "classifier_provider": "ollama",
            "classifier_fallback": None,
        }
    except Exception as exc:
        fallback = make_decision(user_query)
        return {
            **fallback,
            "parameters": {},
            "is_help_or_greeting": False,
            "classifier_provider": "embedding_fallback",
            "classifier_fallback": type(exc).__name__,
            "confidence_source": "embedding_similarity_fallback",
        }