import json
import os
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_LOG_PATH = Path(tempfile.gettempdir()) / "mcp_tool_l2" / "requests.jsonl"
LOG_PATH = Path(os.getenv("AGENT_LOG_PATH", str(DEFAULT_LOG_PATH))).expanduser()
if not LOG_PATH.is_absolute():
    LOG_PATH = PROJECT_ROOT / LOG_PATH

_write_lock = threading.Lock()


def new_request_id() -> str:
    return uuid4().hex


def write_event(
    request_id: str,
    request_name: str,
    stage: str,
    **details: Any,
) -> None:
    """Append one secret-redacted JSON event to the local request log."""
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "request_name": request_name,
        "stage": stage,
        **details,
    }
    secrets = {
        value
        for value in (os.getenv("GEMINI_API_KEY"), os.getenv("gemini_apikey"))
        if value
    }
    serialized = json.dumps(record, ensure_ascii=False, default=str)
    for secret in secrets:
        serialized = serialized.replace(secret, "[REDACTED]")

    with _write_lock:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as log_file:
            log_file.write(serialized + "\n")

    console_fields = (
        "detected_intents",
        "executable_tools",
        "banned_tools",
        "blocked_tools",
        "primary_tool",
        "confidence",
        "confidence_source",
        "classifier_provider",
        "classifier_fallback",
        "parameters",
        "tool",
        "status",
        "latency_ms",
        "provider",
        "selected_provider",
        "elapsed_ms",
        "total_ms",
        "router_ms",
        "tool_wall_ms",
        "tool_calls_ms",
        "synthesis_ms",
        "error_type",
    )
    summary = " ".join(
        f"{field}={json.dumps(record[field], ensure_ascii=False)}"
        for field in console_fields
        if field in record
    )
    print(
        f"[{record['timestamp']}] [{request_id[:8]}] {request_name} {stage} {summary}".rstrip(),
        file=sys.stderr,
        flush=True,
    )