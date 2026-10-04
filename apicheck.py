import asyncio
import httpx


async def check_apis():
    endpoints = {
        "Dog CEO": "https://dog.ceo/api/breeds/image/random",
        "JokeAPI": "https://v2.jokeapi.dev/joke/Any?safe-mode",
        "Open Library": "https://openlibrary.org/search.json?q=test&limit=1",
        "Open-Meteo": "https://api.open-meteo.com/v1/forecast?latitude=0&longitude=0&current=temperature_2m",
    }
    async with httpx.AsyncClient(timeout=5.0) as client:
        for name, url in endpoints.items():
            try:
                res = await client.get(url)
                print(f"[{res.status_code}] {name} is working.")
            except Exception as e:
                print(f"[FAIL] {name}: {e}")


if __name__ == "__main__":
    asyncio.run(check_apis())