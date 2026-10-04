# C:\projects\Mcp_tool_l2\test_api_connections.py
import pytest
import respx
from httpx import Response
from api_connections.dog_api import fetch_dog_image
from api_connections.wather_api import fetch_weather
from api_connections.books_api import query_books


# -------------------------------------------------------------
# 1. Tests for Dog API
# -------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_fetch_dog_image_success():
    """Test fetching random dog image successfully."""
    mock_url = "https://dog.ceo/api/breeds/image/random"
    mock_response = {
        "message": "https://images.dog.ceo/breeds/hound/n02089561_1.jpg",
        "status": "success",
    }
    respx.get(mock_url).mock(return_value=Response(200, json=mock_response))

    result = await fetch_dog_image()
    assert result["success"] is True
    assert "https://images.dog.ceo" in result["image_url"]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_dog_image_specific_breed():
    """Test fetching dog image with specific breed."""
    mock_url = "https://dog.ceo/api/breed/hound/images/random"
    mock_response = {
        "message": "https://images.dog.ceo/breeds/hound/n02089561_2.jpg",
        "status": "success",
    }
    respx.get(mock_url).mock(return_value=Response(200, json=mock_response))

    result = await fetch_dog_image("hound")
    assert result["success"] is True
    assert "hound" in result["image_url"]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_dog_image_error_handling():
    """Test API returning failure status for non-existent breed."""
    mock_url = "https://dog.ceo/api/breed/invalidbreed123/images/random"
    mock_response = {
        "status": "error",
        "message": "Breed not found (master breed does not exist)",
        "code": 404,
    }
    respx.get(mock_url).mock(return_value=Response(404, json=mock_response))

    result = await fetch_dog_image("invalidbreed123")
    assert result["success"] is False
    assert "Breed not found" in result["error"]


# -------------------------------------------------------------
# 2. Tests for Weather API
# -------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_fetch_weather_success():
    """Test weather lookup with coordinates."""
    mock_url = "https://api.open-meteo.com/v1/forecast"
    mock_response = {
        "current_units": {
            "temperature_2m": "°C",
            "relative_humidity_2m": "%",
            "wind_speed_10m": "km/h",
        },
        "current": {
            "temperature_2m": 31.4,
            "relative_humidity_2m": 65,
            "wind_speed_10m": 12.5,
        },
    }
    respx.get(mock_url).mock(return_value=Response(200, json=mock_response))

    result = await fetch_weather(lat=17.385, lon=78.486)
    assert result["success"] is True
    assert result["temperature"] == "31.4°C"
    assert result["humidity"] == "65%"
    assert result["wind_speed"] == "12.5 km/h"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_weather_server_error():
    """Test weather API error handling when upstream fails."""
    mock_url = "https://api.open-meteo.com/v1/forecast"
    respx.get(mock_url).mock(return_value=Response(500))

    result = await fetch_weather()
    assert result["success"] is False
    assert "error" in result


# -------------------------------------------------------------
# 3. Tests for Books API
# -------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_query_books_success():
    """Test searching Open Library for titles."""
    mock_url = "https://openlibrary.org/search.json"
    mock_response = {
        "numFound": 1,
        "docs": [
            {
                "title": "Clean Code",
                "author_name": ["Robert C. Martin"],
                "first_publish_year": 2008,
            }
        ],
    }
    respx.get(mock_url).mock(return_value=Response(200, json=mock_response))

    result = await query_books("clean code", limit=1)
    assert result["success"] is True
    assert len(result["results"]) == 1
    assert result["results"][0]["title"] == "Clean Code"
    assert result["results"][0]["author"] == "Robert C. Martin"
    assert result["results"][0]["first_publish_year"] == 2008


@pytest.mark.asyncio
@respx.mock
async def test_query_books_empty():
    """Test book search when no records match."""
    mock_url = "https://openlibrary.org/search.json"
    mock_response = {"numFound": 0, "docs": []}
    respx.get(mock_url).mock(return_value=Response(200, json=mock_response))

    result = await query_books("non_existent_random_book_query_xyz")
    assert result["success"] is True
    assert result["results"] == []
    