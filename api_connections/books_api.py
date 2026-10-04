from typing import Any

import httpx


async def query_books(search_query: str, limit: int = 3) -> dict[str, Any]:
	"""Search Open Library and return a compact list of book results."""
	params = {"q": search_query, "limit": limit}

	try:
		async with httpx.AsyncClient(timeout=10.0) as client:
			response = await client.get(
				"https://openlibrary.org/search.json", params=params
			)
			response.raise_for_status()
			data = response.json()

		books = []
		for item in data.get("docs", []):
			books.append(
				{
					"title": item.get("title", "Unknown"),
					"author": ", ".join(item.get("author_name", ["Unknown"])),
					"first_publish_year": item.get("first_publish_year", "N/A"),
				}
			)
		return {"success": True, "results": books}
	except Exception as exc:
		return {"success": False, "error": str(exc)}
