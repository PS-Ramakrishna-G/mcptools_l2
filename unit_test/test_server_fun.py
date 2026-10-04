from unittest.mock import AsyncMock

import pytest

from orchastrator import server_fun


@pytest.mark.asyncio
async def test_get_dog_image_formats_success(monkeypatch):
	fetch = AsyncMock(
		return_value={"success": True, "image_url": "https://example.test/dog.jpg"}
	)
	monkeypatch.setattr(server_fun, "fetch_dog_image", fetch)

	result = await server_fun.get_dog_image("hound")

	assert result == "Dog image URL: https://example.test/dog.jpg"
	fetch.assert_awaited_once_with("hound")


@pytest.mark.asyncio
async def test_get_dog_image_formats_failure(monkeypatch):
	monkeypatch.setattr(
		server_fun,
		"fetch_dog_image",
		AsyncMock(return_value={"success": False, "error": "Breed not found"}),
	)

	result = await server_fun.get_dog_image("unknown")

	assert "Breed not found" in result


@pytest.mark.asyncio
async def test_get_weather_formats_success(monkeypatch):
	fetch = AsyncMock(
		return_value={
			"success": True,
			"temperature": "29°C",
			"humidity": "60%",
			"wind_speed": "10 km/h",
		}
	)
	monkeypatch.setattr(server_fun, "fetch_weather", fetch)

	result = await server_fun.get_weather(17.385, 78.486)

	assert "29°C" in result
	assert "60%" in result
	assert "10 km/h" in result
	fetch.assert_awaited_once_with(17.385, 78.486)


@pytest.mark.asyncio
async def test_get_weather_formats_failure(monkeypatch):
	monkeypatch.setattr(
		server_fun,
		"fetch_weather",
		AsyncMock(return_value={"success": False, "error": "offline"}),
	)

	assert "offline" in await server_fun.get_weather()


@pytest.mark.asyncio
async def test_search_library_books_formats_results(monkeypatch):
	query = AsyncMock(
		return_value={
			"success": True,
			"results": [
				{
					"title": "Dune",
					"author": "Frank Herbert",
					"first_publish_year": 1965,
				}
			],
		}
	)
	monkeypatch.setattr(server_fun, "query_books", query)

	result = await server_fun.search_library_books("dune", 1)

	assert "Dune by Frank Herbert" in result
	assert "1965" in result
	query.assert_awaited_once_with("dune", 1)


@pytest.mark.asyncio
async def test_search_library_books_handles_empty_and_failed_results(monkeypatch):
	query = AsyncMock(return_value={"success": True, "results": []})
	monkeypatch.setattr(server_fun, "query_books", query)

	empty_result = await server_fun.search_library_books("nothing")
	assert "No books found" in empty_result

	query.return_value = {"success": False, "error": "offline"}
	failed_result = await server_fun.search_library_books("nothing")
	assert "offline" in failed_result
