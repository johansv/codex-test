from __future__ import annotations

import json
from datetime import date

import pytest

from agentlab.cli import garmin_fetch
from agentlab.core.garmin import EndpointResult, GarminCredentials, GarminFetchRequest


class StubFetcher:
    def __init__(self, names: list[str], results: list[EndpointResult]) -> None:
        self._names = names
        self._results = results
        self.requests: list[GarminFetchRequest] = []
        self.credentials: list[GarminCredentials] = []

    @property
    def supported_endpoints(self) -> list[str]:
        return list(self._names)

    def fetch(
        self,
        credentials: GarminCredentials,
        request: GarminFetchRequest,
    ) -> list[EndpointResult]:
        self.credentials.append(credentials)
        self.requests.append(request)
        return list(self._results)


def test_cli_lists_endpoints(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fetcher = StubFetcher(["alpha", "beta"], [])
    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    monkeypatch.setattr(garmin_fetch, "GarminDataFetcher", lambda: fetcher)

    exit_code = garmin_fetch.main(["--list-endpoints"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.strip().splitlines() == ["alpha", "beta"]


def test_cli_runs_fetch_and_outputs_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = EndpointResult(endpoint="alpha", scope={"date": "2024-01-01"}, payload={"value": 1})
    fetcher = StubFetcher(["alpha"], [result])

    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    monkeypatch.setattr(garmin_fetch, "GarminDataFetcher", lambda: fetcher)

    exit_code = garmin_fetch.main(
        [
            "--date",
            "2024-01-01",
            "--endpoint",
            "alpha",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload == [
        {"endpoint": "alpha", "scope": {"date": "2024-01-01"}, "payload_type": "dict"}
    ]

    assert fetcher.credentials[0].username == "user@example.com"
    assert fetcher.requests[0].start_date == date(2024, 1, 1)
    assert fetcher.requests[0].endpoints == ["alpha"]


def test_cli_rejects_unknown_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    fetcher = StubFetcher(["alpha"], [])
    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    monkeypatch.setattr(garmin_fetch, "GarminDataFetcher", lambda: fetcher)

    with pytest.raises(SystemExit) as excinfo:
        garmin_fetch.main(["--date", "2024-01-01", "--endpoint", "unknown"])

    assert "Unknown endpoint(s)" in str(excinfo.value)
