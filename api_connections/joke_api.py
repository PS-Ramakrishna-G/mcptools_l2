import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

JOKE_API_URL = os.getenv(
    "JOKE_API_URL",
    "https://v2.jokeapi.dev/joke/Any?safe-mode",
)


async def fetch_joke() -> dict[str, Any]:
    """Fetch one safe, single-part joke from JokeAPI."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(JOKE_API_URL, params={"type": "single"})
            response.raise_for_status()
            data = response.json()

        if data.get("error"):
            return {"success": False, "error": data.get("message", "JokeAPI error")}
        joke = data.get("joke")
        if not joke:
            return {"success": False, "error": "JokeAPI returned no joke"}
        return {"success": True, "joke": joke}
    except Exception as exc:
        return {"success": False, "error": str(exc)}