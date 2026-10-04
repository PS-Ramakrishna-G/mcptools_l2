import json
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from ollama import AsyncClient

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

OLLAMA_HOST = os.getenv("DEFAULT_OLLAMA_HOST", "http://localhost:11434")
QWEN_MODEL = os.getenv("DEFAULT_QWEN_MODEL", "qwen2.5:7b")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
_ollama_client = AsyncClient(host=OLLAMA_HOST)


def configured_provider() -> str:
    return "gemini" if os.getenv("GEMINI_API_KEY") or os.getenv("gemini_apikey") else "ollama"


async def _generate_with_gemini(
    api_key: str,
    system_prompt: str,
    user_prompt: str,
) -> str:
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 900},
    }
    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.post(
            endpoint,
            headers={"x-goog-api-key": api_key},
            json=payload,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()

    candidates = data.get("candidates", [])
    if not candidates:
        raise ValueError("Gemini returned no candidates")
    parts = candidates[0].get("content", {}).get("parts", [])
    answer = "\n".join(
        part["text"] for part in parts if isinstance(part.get("text"), str)
    ).strip()
    if not answer:
        raise ValueError("Gemini returned an empty answer")
    return answer


async def _generate_with_ollama(system_prompt: str, user_prompt: str) -> str:
    response = await _ollama_client.chat(
        model=QWEN_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        options={"temperature": 0.2},
    )
    answer = response.message.content.strip()
    if not answer:
        raise ValueError("Local model returned an empty answer")
    return answer


async def classify_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    """Use local Qwen for low-temperature JSON intent classification."""
    response = await _ollama_client.chat(
        model=QWEN_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        format="json",
        options={"temperature": 0},
    )
    result = json.loads(response.message.content)
    if not isinstance(result, dict):
        raise ValueError("Qwen returned JSON that was not an object")
    return result


async def generate_answer(
    system_prompt: str,
    user_prompt: str,
) -> tuple[str, str, str | None]:
    """Prefer Gemini when configured; otherwise use local Qwen."""
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("gemini_apikey")
    fallback_reason = None

    if api_key:
        try:
            answer = await _generate_with_gemini(api_key, system_prompt, user_prompt)
            return answer, "gemini", None
        except Exception as exc:
            fallback_reason = type(exc).__name__

    try:
        answer = await _generate_with_ollama(system_prompt, user_prompt)
    except Exception as exc:
        raise RuntimeError("Local Qwen generation failed") from exc

    return answer, "ollama", fallback_reason