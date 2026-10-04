# C:\projects\Mcp_tool_l2\routing_engine\guardrail_engine.py
import re
from typing import Dict, List, Set
from sentence_transformers import SentenceTransformer, util

# Lightweight local CPU model (~80 MB)
model = SentenceTransformer("all-MiniLM-L6-v2")

# Intent definitions
TOOL_INTENTS = {
    "dog_tool": [
        "show me a dog photo",
        "puppy pictures",
        "pictures of dogs or breeds",
    ],
    "weather_tool": [
        "what is the weather today",
        "current temperature",
        "rain forecast climate conditions",
    ],
    "books_tool": [
        "search for a book",
        "look up author in library catalog",
        "find novels",
    ],
    "joke_tool": [
        "tell me a funny joke",
        "programming joke or pun",
        "make me laugh",
    ],
}

INTENT_VECTORS = {
    tool: model.encode(phrases, convert_to_tensor=True)
    for tool, phrases in TOOL_INTENTS.items()
}

# Regex patterns for negative instructions
NEGATIVE_PATTERNS = [
    r"(?:don't|do not|never|avoid|skip|exclude|don\'t tell|no)\s+(?:me\s+)?(?:about\s+)?(?:any\s+)?([a-zA-Z\s]+?)(?:$|\.|\band\b|\balso\b|,)",
    r"(?:dont\s+say|dont\s+show|dont\s+mention)\s+([a-zA-Z\s]+?)(?:$|\.|\band\b|\balso\b|,)",
]


def extract_guardrail_negations(text: str) -> Set[str]:
    """Detect topics explicitly blocked by the user."""
    banned_topics = set()
    lowered = text.lower()

    for pattern in NEGATIVE_PATTERNS:
        matches = re.finditer(pattern, lowered)
        for m in matches:
            topic = m.group(1).strip()
            # Match detected exclusion against known tool categories
            if any(w in topic for w in ["weather", "temp", "rain", "forecast"]):
                banned_topics.add("weather_tool")
            elif any(w in topic for w in ["dog", "puppy", "hound"]):
                banned_topics.add("dog_tool")
            elif any(w in topic for w in ["book", "library", "author"]):
                banned_topics.add("books_tool")
            elif any(w in topic for w in ["joke", "pun", "humor"]):
                banned_topics.add("joke_tool")

    return banned_topics


def split_clauses(text: str) -> List[str]:
    """Split multi-question prompts on punctuation, commas, or coordinating conjunctions."""
    delimiters = r"[.?!;]|(?<=\s)and(?=\s)|(?<=\s)also(?=\s)|(?<=\s)plus(?=\s)"
    clauses = [
        clause.strip()
        for clause in re.split(delimiters, text, flags=re.IGNORECASE)
    ]
    return [c for c in clauses if len(c) > 3]


def parse_and_route(user_prompt: str, threshold: float = 0.40) -> Dict:
    """Multi-Intent Router + Negative Guardrail Filter."""
    # 1. Detect Negations / Guardrails
    banned_tools = extract_guardrail_negations(user_prompt)

    # 2. Extract Sub-queries
    sub_clauses = split_clauses(user_prompt)

    activated_tools = set()
    clause_decisions = []

    for clause in sub_clauses:
        # Check if the clause itself is a negative instruction
        is_negative = bool(
            re.search(
                r"\b(don\'?t|do not|never|avoid|skip|exclude|no)\b",
                clause.lower(),
            )
        )
        if is_negative:
            continue

        clause_emb = model.encode(clause, convert_to_tensor=True)
        best_tool = None
        highest_score = 0.0

        for tool_name, vectors in INTENT_VECTORS.items():
            score = float(util.cos_sim(clause_emb, vectors).max())
            if score > highest_score and score >= threshold:
                highest_score = score
                best_tool = tool_name

        if best_tool:
            clause_decisions.append(
                {"clause": clause, "tool": best_tool, "score": highest_score}
            )
            activated_tools.add(best_tool)

    # 3. Apply Guardrail Filters (Block requested exclusions)
    blocked_executions = activated_tools.intersection(banned_tools)
    allowed_tools = [
        tool
        for tool in TOOL_INTENTS
        if tool in activated_tools and tool not in banned_tools
    ]

    return {
        "original_prompt": user_prompt,
        "detected_intents": list(activated_tools),
        "guardrail_banned_tools": list(banned_tools),
        "blocked_due_to_guardrail": list(blocked_executions),
        "executable_tools": allowed_tools,
        "clause_decisions": clause_decisions,
        "is_general_chat": len(allowed_tools) == 0,
    }