"""
Single-question Agent Evaluation Harness

Usage:
    python benchmark_one_by_one.py

Each execution asks ONE question, sends ONE request to Ollama,
prints the complete evaluation, and APPENDS one JSON record to:

    benchmark_results.json

You can later feed a 1000-question JSON bank to this same runner.

IMPORTANT:
The "reasoning" stored here is an evaluation rationale / decision explanation,
NOT hidden chain-of-thought. The model is explicitly asked for concise,
auditable reasons such as:
    - why a tool was selected
    - why a tool was banned
    - what evidence in the question triggered the decision
    - confidence
"""

import argparse
import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import httpx
from dotenv import load_dotenv
from app import app as fastapi_app

load_dotenv()

MODEL_NAME = os.getenv("DEFAULT_QWEN_MODEL", "qwen2.5:7b")
OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://localhost:11434/api/chat"
)

RESULTS_FILE = Path(
    os.getenv(
        "RESULTS_FILE",
        str(Path(__file__).with_name("testquestion_results.jsonl")),
    )
)

QUESTIONS_FILE = Path(
    os.getenv("QUESTIONS_FILE", str(Path(__file__).with_name("qeustion.json")))
)

# ============================================================================
# AVAILABLE TOOLS
# ============================================================================

AVAILABLE_TOOLS = {
    "weather_tool": "Live weather, temperature, rain and climate information.",
    "books_tool": "Book and reading recommendations.",
    "dog_tool": "Dog pictures/images.",
    "joke_tool": "Jokes, puns and humor.",
}


# ============================================================================
# MODEL PROMPT
# ============================================================================

SYSTEM_PROMPT = """
You are an Agent Evaluation Router.

Your job is to analyze ONE user question and decide which available tools
should be executed.

AVAILABLE TOOLS:

weather_tool:
  Live weather, temperature, rain and climate.

books_tool:
  Books, reading recommendations, authors and book topics.

dog_tool:
  Dog pictures/images.

joke_tool:
  Jokes, puns and humor.

IMPORTANT RULES:

1. Identify every positive user intent.
2. Identify explicit negative constraints such as:
   "don't show weather",
   "no dogs",
   "skip jokes",
   "do not call weather".
3. A negative constraint overrides a corresponding positive request.
4. A banned tool MUST NOT appear in executable_tools.
5. Preserve all valid positive intents.
6. For books, extract every requested topic and count.
7. If count is not specified, use 10.
8. Normalize dog breeds when possible.
9. If no available tool is required, executable_tools must be [].
10. Do not invent live information.
11. Do not claim a tool was executed if this program only performed routing.
12. Confidence must represent confidence in the ROUTING DECISION.
13. Give a concise AUDIT RATIONALE, not private chain-of-thought.
    The rationale must identify the user evidence that caused each tool
    selection or rejection.

Return ONLY valid JSON with exactly this structure:

{
  "executable_tools": [
    "weather_tool"
  ],
  "banned_tools": [],
  "book_requests": [
    {
      "topic": "python",
      "count": 10
    }
  ],
  "dog_breed": null,
  "is_help": false,
  "confidence": 0.95,
  "tool_reasons": {
    "weather_tool": "Selected because the user explicitly asks for current weather."
  },
  "decision_rationale": "The request explicitly asks for current weather, so weather_tool is required."
}
"""


# ============================================================================
# HELPERS
# ============================================================================

def load_existing_results() -> List[Dict[str, Any]]:
    if not RESULTS_FILE.exists():
        return []

    try:
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            return data

        return []

    except (json.JSONDecodeError, OSError):
        return []


def save_results(results: List[Dict[str, Any]]) -> None:
    temp_file = RESULTS_FILE.with_suffix(".tmp")

    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(
            results,
            f,
            indent=2,
            ensure_ascii=False
        )

    temp_file.replace(RESULTS_FILE)


def normalize_tools(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []

    return sorted(
        str(x).strip()
        for x in value
        if str(x).strip()
    )


def safe_confidence(value: Any) -> float:
    try:
        value = float(value)
        return max(0.0, min(1.0, value))
    except (TypeError, ValueError):
        return 0.0


# ============================================================================
# OLLAMA CALL
# ============================================================================

async def call_router(
    question: str,
    client: httpx.AsyncClient
) -> Dict[str, Any]:

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": question
            }
        ],
        "format": "json",
        "stream": False,
        "options": {
            "num_thread": int(
                os.getenv("OLLAMA_THREADS", "4")
            ),
            "num_ctx": int(
                os.getenv("OLLAMA_CONTEXT", "4096")
            ),
            "temperature": 0.0
        }
    }

    response = await client.post(
        OLLAMA_URL,
        json=payload
    )

    response.raise_for_status()

    body = response.json()

    content = body["message"]["content"]

    return json.loads(content)


# ============================================================================
# EVALUATION
# ============================================================================

def evaluate(
    expected: Dict[str, Any],
    decision: Dict[str, Any]
) -> Dict[str, Any]:

    expected_tools = normalize_tools(
        expected.get("expected_tools", [])
    )

    expected_banned = normalize_tools(
        expected.get("expected_banned", [])
    )

    actual_tools = normalize_tools(
        decision.get("executable_tools", [])
    )

    actual_banned = normalize_tools(
        decision.get("banned_tools", [])
    )

    tools_match = actual_tools == expected_tools

    guardrail_match = (
        set(expected_banned).issubset(set(actual_banned))
        and not (
            set(expected_banned)
            .intersection(set(actual_tools))
        )
    )

    banned_tools_executed = sorted(
        set(actual_tools).intersection(
            set(expected_banned)
        )
    )

    confidence = safe_confidence(
        decision.get("confidence", 0)
    )

    # For benchmark routing, a confidence >= 0.70 is considered
    # a sufficiently confident decision. Adjust this threshold if needed.
    confidence_ok = confidence >= 0.70

    status = (
        "PASS"
        if tools_match
        and guardrail_match
        and len(banned_tools_executed) == 0
        else "FAIL"
    )

    return {
        "status": status,
        "tools_match": tools_match,
        "guardrail_match": guardrail_match,
        "confidence_ok": confidence_ok,
        "banned_tools_executed": banned_tools_executed,
        "expected_tools": expected_tools,
        "actual_tools": actual_tools,
        "expected_banned": expected_banned,
        "actual_banned": actual_banned,
    }


# ============================================================================
# SINGLE QUESTION
# ============================================================================

async def run_one_question(
    question: str,
    expected: Dict[str, Any]
) -> Dict[str, Any]:

    started = time.perf_counter()

    async with httpx.AsyncClient(timeout=120.0) as client:

        try:
            decision = await call_router(
                question,
                client
            )

            latency_ms = (
                time.perf_counter() - started
            ) * 1000

            evaluation = evaluate(
                expected,
                decision
            )

            record_id = expected.get(
                "id",
                f"manual_{int(time.time())}"
            )

            record = {
                "id": record_id,

                "timestamp_utc": datetime.now(
                    timezone.utc
                ).isoformat(),

                "model": MODEL_NAME,

                "complexity": expected.get(
                    "complexity",
                    "unknown"
                ),

                "category": expected.get(
                    "category",
                    "manual"
                ),

                "question": question,

                "expected_answer": expected.get(
                    "expected_answer",
                    ""
                ),

                "model_answer": decision.get(
                    "answer",
                    ""
                ),

                "expected_tools": evaluation[
                    "expected_tools"
                ],

                "actual_tools": evaluation[
                    "actual_tools"
                ],

                "expected_banned_tools": evaluation[
                    "expected_banned"
                ],

                "actual_banned_tools": evaluation[
                    "actual_banned"
                ],

                "tool_reasons": decision.get(
                    "tool_reasons",
                    {}
                ),

                "decision_rationale": decision.get(
                    "decision_rationale",
                    ""
                ),

                "confidence": safe_confidence(
                    decision.get(
                        "confidence",
                        0
                    )
                ),

                "book_requests": decision.get(
                    "book_requests",
                    []
                ),

                "dog_breed": decision.get(
                    "dog_breed"
                ),

                "is_help": decision.get(
                    "is_help",
                    False
                ),

                "latency_ms": round(
                    latency_ms,
                    2
                ),

                **evaluation,

                "error": None
            }

            return record

        except Exception as exc:

            latency_ms = (
                time.perf_counter() - started
            ) * 1000

            return {
                "id": expected.get(
                    "id",
                    f"manual_{int(time.time())}"
                ),

                "timestamp_utc": datetime.now(
                    timezone.utc
                ).isoformat(),

                "model": MODEL_NAME,

                "complexity": expected.get(
                    "complexity",
                    "unknown"
                ),

                "category": expected.get(
                    "category",
                    "manual"
                ),

                "question": question,

                "expected_answer": expected.get(
                    "expected_answer",
                    ""
                ),

                "model_answer": "",

                "expected_tools": expected.get(
                    "expected_tools",
                    []
                ),

                "actual_tools": [],

                "expected_banned_tools": expected.get(
                    "expected_banned",
                    []
                ),

                "actual_banned_tools": [],

                "tool_reasons": {},

                "decision_rationale": "",

                "confidence": 0.0,

                "latency_ms": round(
                    latency_ms,
                    2
                ),

                "status": "ERROR",

                "tools_match": False,

                "guardrail_match": False,

                "confidence_ok": False,

                "banned_tools_executed": [],

                "error": str(exc)
            }


# ============================================================================
# LOAD ONE QUESTION FROM 1000-QUESTION BANK
# ============================================================================

def get_question_from_bank(
    question_number: int
) -> Dict[str, Any]:

    if not QUESTIONS_FILE.exists():
        raise FileNotFoundError(
            f"{QUESTIONS_FILE} not found."
        )

    with open(
        QUESTIONS_FILE,
        "r",
        encoding="utf-8"
    ) as f:
        questions = json.load(f)

    if not isinstance(questions, list):
        raise ValueError(
            "questions_1000.json must contain a JSON array."
        )

    if question_number < 1 or question_number > len(
        questions
    ):
        raise IndexError(
            f"Question number must be between 1 and {len(questions)}."
        )

    return questions[question_number - 1]


# ============================================================================
# PRINT RESULT
# ============================================================================

def print_result(record: Dict[str, Any]) -> None:

    print("\n" + "=" * 100)
    print("SINGLE QUESTION EVALUATION")
    print("=" * 100)

    print(f"ID         : {record['id']}")
    print(f"Complexity : {record['complexity']}")
    print(f"Category   : {record['category']}")
    print(f"Status     : {record['status']}")
    print(f"Confidence : {record['confidence']:.2f}")
    print(f"Latency    : {record['latency_ms']:.2f} ms")

    print("\nQUESTION")
    print("-" * 100)
    print(record["question"])

    print("\nEXPECTED ANSWER")
    print("-" * 100)
    print(record["expected_answer"] or "(not supplied)")

    print("\nMODEL ANSWER")
    print("-" * 100)
    print(record["model_answer"] or "(none)")

    print("\nTOOL DECISION")
    print("-" * 100)
    print(f"Expected tools : {record['expected_tools']}")
    print(f"Actual tools   : {record['actual_tools']}")
    print(f"Expected banned: {record['expected_banned_tools']}")
    print(f"Actual banned  : {record['actual_banned_tools']}")

    print("\nWHY / AUDIT RATIONALE")
    print("-" * 100)

    reasons = record.get("tool_reasons", {})

    if reasons:
        for tool, reason in reasons.items():
            print(f"{tool}: {reason}")

    print(
        f"\nOverall decision: "
        f"{record.get('decision_rationale', '')}"
    )

    print("\nVALIDATION")
    print("-" * 100)
    print(
        f"Tools match     : "
        f"{'PASS' if record['tools_match'] else 'FAIL'}"
    )
    print(
        f"Guardrails      : "
        f"{'PASS' if record['guardrail_match'] else 'FAIL'}"
    )
    print(
        f"Confidence >= .70: "
        f"{'PASS' if record['confidence_ok'] else 'FAIL'}"
    )

    if record["banned_tools_executed"]:
        print(
            f"BANNED TOOLS EXECUTED: "
            f"{record['banned_tools_executed']}"
        )

    print("\n" + "=" * 100)


def load_question_bank(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as question_file:
        data = json.load(question_file)

    questions = data.get("questions") if isinstance(data, dict) else data
    if not isinstance(questions, list):
        raise ValueError("Question JSON must be an array or an object with a 'questions' array.")

    cases = []
    for index, item in enumerate(questions, start=1):
        if isinstance(item, str):
            item = {"question": item}
        if not isinstance(item, dict):
            raise ValueError(f"Question {index} must be a string or JSON object.")

        question = item.get("question", item.get("query"))
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"Question {index} is missing a non-empty 'question' field.")

        cases.append({
            **item,
            "id": str(item.get("id", f"q_{index:04d}")),
            "question": question.strip(),
        })
    return cases


def load_completed_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()

    completed = set()
    with path.open("r", encoding="utf-8") as results_file:
        for line in results_file:
            try:
                result = json.loads(line)
            except json.JSONDecodeError:
                continue
            if result.get("id") and isinstance(result.get("timing"), dict):
                completed.add(str(result["id"]))
    return completed


def build_result_record(
    case: Dict[str, Any],
    response_data: Dict[str, Any],
    http_status: int,
    latency_ms: float,
) -> Dict[str, Any]:
    actual_tools = normalize_tools(response_data.get("executable_tools", []))
    actual_banned = normalize_tools(response_data.get("banned_tools", []))
    expected_tools = case.get("expected_tools")
    expected_banned = case.get("expected_banned", case.get("expected_banned_tools"))
    category_expectations = {
        "weather_single": ["weather_tool"],
        "books_single": ["books_tool"],
        "books_quantified": ["books_tool"],
        "dog_single": ["dog_tool"],
        "dog_normalization": ["dog_tool"],
        "joke_single": ["joke_tool"],
        "help_or_out_of_scope": [],
    }
    if expected_tools is None:
        expected_tools = category_expectations.get(case.get("category"))
    if expected_banned is None and case.get("category") in category_expectations:
        expected_banned = []

    tools_match = (
        actual_tools == normalize_tools(expected_tools)
        if isinstance(expected_tools, list)
        else None
    )
    guardrail_match = None
    if isinstance(expected_banned, list):
        normalized_expected_banned = normalize_tools(expected_banned)
        guardrail_match = (
            set(normalized_expected_banned).issubset(set(actual_banned))
            and not set(normalized_expected_banned).intersection(actual_tools)
        )

    tool_results = response_data.get("tool_results", [])
    actual_executed_tools = normalize_tools(
        [result.get("tool") for result in tool_results if result.get("tool")]
    )
    tool_execution_match = (
        actual_executed_tools == normalize_tools(expected_tools)
        if isinstance(expected_tools, list)
        else None
    )
    tool_execution_ok = (
        all(result.get("status") == "success" for result in tool_results)
        if isinstance(expected_tools, list)
        else None
    )

    parameters = response_data.get("parameters", {})
    expected_weather_city = (
        parameters.get("city") if isinstance(parameters, dict) else None
    )
    resolved_weather_city = None
    if expected_weather_city:
        weather_result = next(
            (result for result in tool_results if result.get("tool") == "weather_tool"),
            None,
        )
        if weather_result:
            first_line = str(weather_result.get("output", "")).splitlines()[0]
            if first_line.startswith("Weather for ") and first_line.endswith(":"):
                resolved_weather_city = first_line[len("Weather for "):-1]

    def normalized_location(value: str | None) -> str:
        if not value:
            return ""
        return "".join(character.casefold() for character in value if character.isalnum())

    location_match = (
        normalized_location(expected_weather_city)
        == normalized_location(resolved_weather_city)
        if expected_weather_city
        else None
    )

    has_expectations = tools_match is not None and guardrail_match is not None
    status = "ERROR" if http_status >= 400 else "UNSCORED"
    if http_status < 400 and has_expectations:
        passed = (
            tools_match is not False
            and guardrail_match is not False
            and tool_execution_match is not False
            and tool_execution_ok is not False
            and location_match is not False
        )
        status = "PASS" if passed else "FAIL"

    detected_intents = response_data.get("detected_intents", [])
    provider = response_data.get("provider", "unknown")
    request_id = response_data.get("request_id")

    return {
        "id": case["id"],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "question": case["question"],
        "category": case.get("category", "unspecified"),
        "complexity": case.get("complexity", "unspecified"),
        "http_status": http_status,
        "status": status,
        "latency_ms": round(latency_ms, 2),
        "timing": response_data.get("timing", {"total_ms": round(latency_ms, 2)}),
        "expected_tools": expected_tools,
        "actual_tools": actual_tools,
        "executed_tools": actual_executed_tools,
        "expected_banned_tools": expected_banned,
        "actual_banned_tools": actual_banned,
        "tools_match": tools_match,
        "guardrail_match": guardrail_match,
        "tool_execution_match": tool_execution_match,
        "tool_execution_ok": tool_execution_ok,
        "expected_weather_city": expected_weather_city,
        "resolved_weather_city": resolved_weather_city,
        "location_match": location_match,
        "detected_intents": detected_intents,
        "parameters": parameters,
        "tool_results": tool_results,
        "provider": provider,
        "confidence": response_data.get("confidence"),
        "confidence_source": response_data.get("confidence_source"),
        "request_id": request_id,
        "answer": response_data.get("reply", response_data.get("detail", "")),
        "audit_reason": {
            "detected_intents": detected_intents,
            "allowed_tools": actual_tools,
            "executed_tools": actual_executed_tools,
            "banned_tools": actual_banned,
            "parameters": parameters,
            "expected_weather_city": expected_weather_city,
            "resolved_weather_city": resolved_weather_city,
            "location_match": location_match,
            "tool_evidence": [
                {
                    "tool": result.get("tool"),
                    "status": result.get("status"),
                    "arguments": result.get("arguments"),
                    "latency_ms": result.get("latency_ms"),
                    "output": result.get("output"),
                }
                for result in tool_results
            ],
            "answer_provider": provider,
            "confidence": response_data.get("confidence"),
            "confidence_source": response_data.get("confidence_source"),
            "request_id": request_id,
            "timing": response_data.get("timing", {"total_ms": round(latency_ms, 2)}),
            "note": "Observable application trace; not hidden model chain-of-thought.",
        },
        "expected_answer": case.get("expected_answer"),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run qeustion.json through the existing FastAPI agent and MCP tools."
    )
    parser.add_argument("--questions", type=Path, default=QUESTIONS_FILE)
    parser.add_argument("--results", type=Path, default=RESULTS_FILE)
    parser.add_argument("--limit", type=int, help="Run only the first N questions (useful for a smoke run).")
    parser.add_argument("--resume", action="store_true", help="Skip IDs already present in the JSONL result file.")
    args = parser.parse_args()

    question_path = args.questions.resolve()
    results_path = args.results.resolve()
    if not question_path.exists():
        raise SystemExit(f"Question file not found: {question_path}")

    cases = load_question_bank(question_path)
    if not cases:
        raise SystemExit(f"No questions found in {question_path}; add records to its 'questions' array.")
    if args.limit is not None:
        if args.limit < 1:
            raise SystemExit("--limit must be greater than zero")
        cases = cases[:args.limit]

    completed_ids = load_completed_ids(results_path) if args.resume else set()
    cases = [case for case in cases if case["id"] not in completed_ids]
    if not cases:
        print("No unprocessed questions remain.")
        return

    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.touch(exist_ok=True)
    print(f"Questions to run: {len(cases)}")
    print(f"Model: {MODEL_NAME}")
    print(f"Results: {results_path}")
    print("Each request uses the existing FastAPI /api/chat route and MCP session.")

    status_counts: Dict[str, int] = {}
    async with fastapi_app.router.lifespan_context(fastapi_app):
        transport = httpx.ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            timeout=180.0,
        ) as client:
            for index, case in enumerate(cases, start=1):
                started = time.perf_counter()
                request_payload = {
                    "query": case["question"],
                }
                if case.get("latitude") is not None and case.get("longitude") is not None:
                    request_payload["latitude"] = case["latitude"]
                    request_payload["longitude"] = case["longitude"]
                try:
                    response = await client.post("/api/chat", json=request_payload)
                    response_data = response.json()
                except Exception as exc:
                    response = None
                    response_data = {"detail": f"{type(exc).__name__}: {exc}"}

                latency_ms = (time.perf_counter() - started) * 1000
                record = build_result_record(
                    case,
                    response_data,
                    response.status_code if response is not None else 0,
                    latency_ms,
                )
                with results_path.open("a", encoding="utf-8") as results_file:
                    results_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                    results_file.flush()

                status_counts[record["status"]] = status_counts.get(record["status"], 0) + 1
                print(
                    f"[{index}/{len(cases)}] {record['id']} {record['status']} "
                    f"tools={record['actual_tools']} provider={record['provider']} "
                    f"latency={record['latency_ms']:.0f}ms "
                    f"status={record['status']}"
                )

    print(f"Finished. Status counts: {status_counts}")
    print(f"Detailed answers and audit traces: {results_path}")


if __name__ == "__main__":
    asyncio.run(main())
