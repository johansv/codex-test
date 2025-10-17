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


def write_config(tmp_path: Path, *, enabled: list[str], disabled: list[str] | None = None) -> Path:
    config_path = tmp_path / "endpoints.toml"
    disabled = disabled or []
    lines = [
        "[defaults]",
        f"enabled = {json.dumps(enabled)}",
    ]
    if disabled:
        lines.append(f"disabled = {json.dumps(disabled)}")
    lines.append("")
    config_path.write_text("\n".join(lines), encoding="utf-8")
    return config_path


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
            for name in list(request.endpoints or self._names):
                observer(name)
                self.observed.append(name)
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
    config_path = write_config(tmp_path, enabled=["alpha"])
    output_dir = tmp_path / "out"

    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    monkeypatch.setattr(garmin_fetch, "GarminDataFetcher", lambda: fetcher)

    exit_code = garmin_fetch.main(
        [
            "--date",
            "2024-01-01",
            "--output-dir",
            str(output_dir),
            "--config",
            str(config_path),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    output_path = output_dir / "2024-01-01" / "alpha.json"

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
    error = EndpointError(endpoint="beta", scope={}, message="boom", traceback="trace")
    outcome = FetchOutcome(results=[], errors=[error])
    fetcher = StubFetcher(["beta"], [outcome])
    config_path = write_config(tmp_path, enabled=["beta"])
    output_dir = tmp_path / "out"

    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    monkeypatch.setattr(garmin_fetch, "GarminDataFetcher", lambda: fetcher)

    garmin_fetch.main(
        [
            "--date",
            "2024-01-02",
            "--output-dir",
            str(output_dir),
            "--config",
            str(config_path),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    error_path = output_dir / "2024-01-02" / "beta.error.json"
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
    fetcher = StubFetcher(["alpha", "gamma"], [outcome])
    config_path = write_config(tmp_path, enabled=["alpha"])
    output_dir = tmp_path / "out"

    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    monkeypatch.setattr(garmin_fetch, "GarminDataFetcher", lambda: fetcher)

    exit_code = garmin_fetch.main(
        [
            "--date",
            "2024-01-03",
            "--output-dir",
            str(output_dir),
            "--config",
            str(config_path),
            "--include",
            "gamma",
            "--debug",
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(captured.out)

    assert exit_code == 0
    assert "[garmin] 2024-01-03 -> alpha" in captured.err
    assert "[garmin] 2024-01-03 -> gamma" in captured.err
    assert summary == [{"date": "2024-01-03", "saved": ["gamma"], "errors": []}]
    assert fetcher.observed == ["alpha", "gamma"]


def test_cli_rejects_unknown_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fetcher = StubFetcher(["alpha"], [])
    config_path = write_config(tmp_path, enabled=["alpha"])

    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    monkeypatch.setattr(garmin_fetch, "GarminDataFetcher", lambda: fetcher)

    with pytest.raises(SystemExit) as excinfo:
        garmin_fetch.main(
            [
                "--date",
                "2024-01-01",
                "--config",
                str(config_path),
                "--include",
                "unknown",
            ]
        )

    assert "Unknown endpoint(s)" in str(excinfo.value)


def test_cli_blocks_disabled_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fetcher = StubFetcher(["alpha", "beta"], [])
    config_path = write_config(tmp_path, enabled=["alpha"], disabled=["beta"])

    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    monkeypatch.setattr(garmin_fetch, "GarminDataFetcher", lambda: fetcher)

    with pytest.raises(SystemExit) as excinfo:
        garmin_fetch.main(
            [
                "--date",
                "2024-01-01",
                "--config",
                str(config_path),
                "--include",
                "beta",
            ]
        )

    assert "disabled via configuration" in str(excinfo.value)


def test_cli_exclude_removes_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    outcome = FetchOutcome(results=[], errors=[])
    fetcher = StubFetcher(["alpha", "beta"], [outcome])
    config_path = write_config(tmp_path, enabled=["alpha", "beta"])
    output_dir = tmp_path / "out"

    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    monkeypatch.setattr(garmin_fetch, "GarminDataFetcher", lambda: fetcher)

    garmin_fetch.main(
        [
            "--date",
            "2024-01-01",
            "--config",
            str(config_path),
            "--output-dir",
            str(output_dir),
            "--exclude",
            "alpha",
        ]
    )

    assert fetcher.requests[0].endpoints == ["beta"]
