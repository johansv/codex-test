from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from agentlab.cli import garmin_fetch
from agentlab.core.garmin import (
    EndpointError,
    EndpointResult,
    FetchOutcome,
    GarminCredentials,
    GarminFetchRequest,
)


class StubFetcher:
    def __init__(self, names: list[str], outcomes: list[FetchOutcome]) -> None:
        self._names = names
        self._outcomes = list(outcomes)
        self.credentials: list[GarminCredentials] = []
        self.requests: list[GarminFetchRequest] = []
        self.observed: list[str] = []

    @property
    def supported_endpoints(self) -> list[str]:
        return list(self._names)

    def fetch(
        self,
        credentials: GarminCredentials,
        request: GarminFetchRequest,
        observer=None,
    ) -> FetchOutcome:
        self.credentials.append(credentials)
        self.requests.append(request)
        outcome = self._outcomes.pop(0)
        if observer:
            for result in outcome.results:
                observer(result.endpoint)
                self.observed.append(result.endpoint)
            for error in outcome.errors:
                observer(error.endpoint)
                self.observed.append(error.endpoint)
        return outcome


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


def test_cli_runs_fetch_writes_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = EndpointResult(endpoint="alpha", scope={}, payload={"value": 1})
    outcome = FetchOutcome(results=[result], errors=[])
    fetcher = StubFetcher(["alpha"], [outcome])

    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    monkeypatch.setattr(garmin_fetch, "GarminDataFetcher", lambda: fetcher)

    exit_code = garmin_fetch.main(
        [
            "--date",
            "2024-01-01",
            "--endpoint",
            "alpha",
            "--output-dir",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    output_path = tmp_path / "2024-01-01" / "alpha.json"

    assert exit_code == 0
    assert summary == [{"date": "2024-01-01", "saved": ["alpha"], "errors": []}]
    assert json.loads(output_path.read_text(encoding="utf-8")) == {"value": 1}
    assert fetcher.credentials[0].username == "user@example.com"
    assert fetcher.requests[0].start_date == date(2024, 1, 1)
    assert fetcher.requests[0].endpoints == ["alpha"]


def test_cli_writes_error_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = EndpointError(
        endpoint="beta",
        scope={},
        message="boom",
        traceback="trace",
    )
    outcome = FetchOutcome(results=[], errors=[error])
    fetcher = StubFetcher(["beta"], [outcome])

    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    monkeypatch.setattr(garmin_fetch, "GarminDataFetcher", lambda: fetcher)

    garmin_fetch.main(
        [
            "--date",
            "2024-01-02",
            "--endpoint",
            "beta",
            "--output-dir",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    error_path = tmp_path / "2024-01-02" / "beta.error.json"
    payload = json.loads(error_path.read_text(encoding="utf-8"))

    assert summary == [{"date": "2024-01-02", "saved": [], "errors": ["beta"]}]
    assert payload["endpoint"] == "beta"
    assert "boom" in payload["message"]


def test_cli_debug_logs_endpoints(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = EndpointResult(endpoint="gamma", scope={}, payload={"value": 3})
    outcome = FetchOutcome(results=[result], errors=[])
    fetcher = StubFetcher(["gamma"], [outcome])

    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    monkeypatch.setattr(garmin_fetch, "GarminDataFetcher", lambda: fetcher)

    exit_code = garmin_fetch.main(
        [
            "--date",
            "2024-01-03",
            "--endpoint",
            "gamma",
            "--output-dir",
            str(tmp_path),
            "--debug",
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(captured.out)

    assert exit_code == 0
    assert "[garmin] 2024-01-03 -> gamma" in captured.err
    assert summary == [{"date": "2024-01-03", "saved": ["gamma"], "errors": []}]
    assert fetcher.observed == ["gamma"]


def test_cli_rejects_unknown_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    fetcher = StubFetcher(["alpha"], [])
    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    monkeypatch.setattr(garmin_fetch, "GarminDataFetcher", lambda: fetcher)

    with pytest.raises(SystemExit) as excinfo:
        garmin_fetch.main(["--date", "2024-01-01", "--endpoint", "unknown"])

    assert "Unknown endpoint(s)" in str(excinfo.value)
