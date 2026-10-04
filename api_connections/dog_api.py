from typing import Any

import httpx


async def fetch_dog_image(breed: str = "") -> dict[str, Any]:
	"""Fetch a random dog image, optionally filtered by breed."""
	normalized_breed = breed.strip().lower()
	url = (
		f"https://dog.ceo/api/breed/{normalized_breed}/images/random"
		if normalized_breed
		else "https://dog.ceo/api/breeds/image/random"
	)

	try:
		async with httpx.AsyncClient(timeout=10.0) as client:
			response = await client.get(url)
			data = response.json()
		if data.get("status") == "success":
			return {"success": True, "image_url": data["message"]}
		return {
			"success": False,
			"error": data.get("message", "Breed not found"),
		}
	except Exception as exc:
		return {"success": False, "error": str(exc)}
