from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

import apicheck


@pytest.mark.asyncio
async def test_check_apis_reports_statuses_and_request_failures(monkeypatch, capsys):
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.get.side_effect = [
        SimpleNamespace(status_code=200),
        httpx.ConnectError("network down"),
        SimpleNamespace(status_code=503),
        SimpleNamespace(status_code=200),
    ]
    client_factory = Mock(return_value=client)
    monkeypatch.setattr(apicheck.httpx, "AsyncClient", client_factory)

    await apicheck.check_apis()

    output = capsys.readouterr().out
    assert "[200] Dog CEO is working." in output
    assert "[FAIL] JokeAPI: network down" in output
    assert "[503] Open Library is working." in output
    assert "[200] Open-Meteo is working." in output
    assert client.get.await_count == 4
    client_factory.assert_called_once_with(timeout=5.0)