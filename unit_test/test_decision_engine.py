from routing_engine import decision


def test_make_decision_selects_highest_confidence_tool(monkeypatch):
    monkeypatch.setattr(
        decision,
        "parse_and_route",
        lambda query: {
            "original_prompt": query,
            "detected_intents": ["dog_tool", "weather_tool"],
            "guardrail_banned_tools": [],
            "blocked_due_to_guardrail": [],
            "executable_tools": ["dog_tool", "weather_tool"],
            "clause_decisions": [
                {"tool": "dog_tool", "score": 0.72},
                {"tool": "weather_tool", "score": 0.91},
            ],
        },
    )

    result = decision.make_decision("dog and weather")

    assert result["executable_tools"] == ["dog_tool", "weather_tool"]
    assert result["primary_tool"] == "weather_tool"
    assert result["confidence"] == 0.91


def test_make_decision_never_selects_guardrail_blocked_tool(monkeypatch):
    monkeypatch.setattr(
        decision,
        "parse_and_route",
        lambda query: {
            "original_prompt": query,
            "detected_intents": ["dog_tool", "weather_tool"],
            "guardrail_banned_tools": ["weather_tool"],
            "blocked_due_to_guardrail": ["weather_tool"],
            "executable_tools": ["dog_tool"],
            "clause_decisions": [
                {"tool": "dog_tool", "score": 0.72},
                {"tool": "weather_tool", "score": 0.99},
            ],
        },
    )

    result = decision.make_decision("dog, no weather")

    assert result["executable_tools"] == ["dog_tool"]
    assert result["primary_tool"] == "dog_tool"
    assert result["confidence"] == 0.72


def test_system_one_decision_returns_no_tool_for_general_chat(monkeypatch):
    monkeypatch.setattr(
        decision,
        "parse_and_route",
        lambda query: {
            "original_prompt": query,
            "detected_intents": [],
            "guardrail_banned_tools": [],
            "blocked_due_to_guardrail": [],
            "executable_tools": [],
            "clause_decisions": [],
        },
    )

    assert decision.system_one_decision("hello") == ("no_tool", 0.0)