import re
from typing import Any

import httpx


async def fetch_weather(
	lat: float | None = None,
	lon: float | None = None,
	city: str | None = None,
	country_code: str | None = None,
) -> dict[str, Any]:
	"""Fetch current conditions by city or coordinates."""
	try:
		async with httpx.AsyncClient(timeout=10.0) as client:
			location_name = city.strip() if city and city.strip() else None
			if location_name:
				geocode_params = {
					"name": location_name,
					"count": 100 if country_code else 10,
					"language": "en",
					"format": "json",
				}
				if country_code:
					geocode_params["countryCode"] = country_code.upper()
				geocode_response = await client.get(
					"https://geocoding-api.open-meteo.com/v1/search",
					params=geocode_params,
				)
				geocode_response.raise_for_status()
				locations = geocode_response.json().get("results", [])
				if not locations:
					return {"success": False, "error": f"No weather location found for '{location_name}'."}
				normalize = lambda value: re.sub(r"[^a-z0-9]", "", value.casefold())
				exact_matches = [
					item
					for item in locations
					if normalize(item.get("name", "")) == normalize(location_name)
				]
				if not exact_matches:
					return {
						"success": False,
						"error": f"No exact match for '{location_name}'. Include the country or provide coordinates.",
					}
				countries = {
					item.get("country_code")
					for item in exact_matches
					if item.get("country_code")
				}
				if not country_code and len(countries) > 1:
					return {
						"success": False,
						"error": f"'{location_name}' matches places in multiple countries. Specify the country or provide coordinates.",
					}
				location = max(
					exact_matches,
					key=lambda item: item.get("population") or 0,
				)
				lat = float(location["latitude"])
				lon = float(location["longitude"])
				location_name = location.get("name", location_name)
			elif lat is None or lon is None:
				return {
					"success": False,
					"error": "Provide a city or both latitude and longitude.",
				}

			if not -90 <= lat <= 90 or not -180 <= lon <= 180:
				return {"success": False, "error": "Coordinates are outside valid ranges."}

			params = {
				"latitude": lat,
				"longitude": lon,
				"current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
			}
			response = await client.get(
				"https://api.open-meteo.com/v1/forecast", params=params
			)
			response.raise_for_status()
			data = response.json()

		current = data.get("current", {})
		units = data.get("current_units", {})
		return {
			"success": True,
			"location": location_name or f"({lat}, {lon})",
			"latitude": lat,
			"longitude": lon,
			"temperature": f"{current.get('temperature_2m')}{units.get('temperature_2m', '°C')}",
			"humidity": f"{current.get('relative_humidity_2m')}{units.get('relative_humidity_2m', '%')}",
			"wind_speed": f"{current.get('wind_speed_10m')} {units.get('wind_speed_10m', 'km/h')}",
		}
	except Exception as exc:
		return {"success": False, "error": str(exc)}
