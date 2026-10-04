from typing import Any

from mcp.server.mcpserver import MCPServer

from api_connections.books_api import query_books
from api_connections.dog_api import fetch_dog_image
from api_connections.joke_api import fetch_joke
from api_connections.wather_api import fetch_weather

mcp = MCPServer(name="LocalToolsServer")


@mcp.tool()
async def get_dog_image(breed: str = "") -> str:
    """Fetch a random dog image URL, optionally filtered by breed."""
    result = await fetch_dog_image(breed)
    if result.get("success"):
        return f"Dog image URL: {result['image_url']}"
    return f"Failed to retrieve dog image: {result.get('error', 'Unknown error')}"


@mcp.tool()
async def get_weather(
    lat: float | None = None,
    lon: float | None = None,
    city: str = "",
    country_code: str = "",
) -> str:
    """Fetch current temperature, humidity, and wind for a city or coordinates."""
    result = await fetch_weather(
        lat,
        lon,
        city=city or None,
        country_code=country_code or None,
    )
    if not result.get("success"):
        return f"Failed to fetch weather: {result.get('error', 'Unknown error')}"

    return (
        f"Weather for {result.get('location', f'({lat}, {lon})')}:\n"
        f"- Temperature: {result['temperature']}\n"
        f"- Relative humidity: {result['humidity']}\n"
        f"- Wind speed: {result['wind_speed']}"
    )


@mcp.tool()
async def get_joke() -> str:
    """Fetch one safe, single-part joke."""
    result = await fetch_joke()
    if result.get("success"):
        return result["joke"]
    return f"Joke lookup failed: {result.get('error', 'Unknown error')}"


@mcp.tool()
async def search_library_books(search_query: str, limit: int = 3) -> str:
    """Search Open Library by title, author, or topic."""
    result = await query_books(search_query, limit)
    if not result.get("success"):
        return f"Book search failed: {result.get('error', 'Unknown error')}"

    books = result.get("results", [])
    if not books:
        return f"No books found for '{search_query}'."

    return "\n".join(
        f"{index}. {book['title']} by {book['author']} "
        f"(Published: {book['first_publish_year']})"
        for index, book in enumerate(books, start=1)
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")