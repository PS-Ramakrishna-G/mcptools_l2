from routing_engine import guardrail_engine


class Similarity:
    def __init__(self, score):
        self.score = score

    def max(self):
        return self

    def __float__(self):
        return self.score


def patch_scores(monkeypatch, scores):
    monkeypatch.setattr(guardrail_engine.model, "encode", lambda text, **kwargs: text)

    def cosine_similarity(clause, intent_vectors):
        tool_name = next(
            name
            for name, vectors in guardrail_engine.INTENT_VECTORS.items()
            if vectors is intent_vectors
        )
        return Similarity(scores.get((clause, tool_name), 0.01))

    monkeypatch.setattr(guardrail_engine.util, "cos_sim", cosine_similarity)


def test_extract_guardrail_negations_maps_tool_categories():
    assert guardrail_engine.extract_guardrail_negations("don't mention weather") == {
        "weather_tool"
    }
    assert guardrail_engine.extract_guardrail_negations("skip books") == {"books_tool"}
    assert guardrail_engine.extract_guardrail_negations("no dog photos") == {"dog_tool"}
    assert guardrail_engine.extract_guardrail_negations("avoid jokes") == {"joke_tool"}


def test_split_clauses_splits_conjunctions_and_punctuation():
    assert guardrail_engine.split_clauses(
        "find books and tell a joke; show me a dog"
    ) == ["find books", "tell a joke", "show me a dog"]


def test_parse_and_route_preserves_allowed_tools_and_bans_weather(monkeypatch):
    patch_scores(
        monkeypatch,
        {("show me a dog photo", "dog_tool"): 0.9},
    )

    result = guardrail_engine.parse_and_route(
        "show me a dog photo and tell me the weather, but don't mention any weather"
    )

    assert result["executable_tools"] == ["dog_tool"]
    assert result["guardrail_banned_tools"] == ["weather_tool"]
    assert result["is_general_chat"] is False


def test_parse_and_route_blocks_a_detected_banned_tool(monkeypatch):
    patch_scores(
        monkeypatch,
        {("tell me the weather", "weather_tool"): 0.9},
    )

    result = guardrail_engine.parse_and_route(
        "tell me the weather. don't mention weather"
    )

    assert result["executable_tools"] == []
    assert result["blocked_due_to_guardrail"] == ["weather_tool"]
    assert result["is_general_chat"] is True