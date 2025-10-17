from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from agentlab.cli import garmin_fetch
from agentlab.core.garmin import EndpointError, EndpointResult, FetchOutcome


CONFIG_TEMPLATE = """
[defaults]
enabled = ["alpha"]
"""


class StubFetcher:
    """Test double that records correlation IDs."""

    outcome: FetchOutcome

    def __init__(self) -> None:
        self.supported_endpoints = ["alpha"]
        self.correlations: list[str | None] = []
        self.outcome = getattr(self.__class__, "outcome")

    def fetch(
        self,
        credentials,
        request,
        observer=None,
        *,
        correlation_id=None,
    ) -> FetchOutcome:
        self.correlations.append(correlation_id)
        return self.outcome


@pytest.fixture(autouse=True)
def _credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")


def _write_config(path: Path) -> None:
    path.write_text(CONFIG_TEMPLATE.strip(), encoding="utf-8")


def test_main_reports_success_summary(tmp_path, monkeypatch, capsys, caplog):
    outcome = FetchOutcome(
        results=[
            EndpointResult(endpoint="alpha", scope={}, payload={"value": 1}),
        ],
        errors=[],
    )
    StubFetcher.outcome = outcome
    instances: list[StubFetcher] = []

    def factory() -> StubFetcher:
        instance = StubFetcher()
        instances.append(instance)
        return instance

    monkeypatch.setattr(garmin_fetch, "GarminDataFetcher", factory)

    config_path = tmp_path / "config.toml"
    _write_config(config_path)

    caplog.set_level(logging.INFO, logger="agentlab.cli.garmin_fetch")

    exit_code = garmin_fetch.main(
        [
            "--date",
            "2024-01-01",
            "--config",
            str(config_path),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary == [
        {
            "date": "2024-01-01",
            "successes": ["alpha"],
            "failures": [],
            "retry_outcomes": {"scheduled": 0, "succeeded": 0, "failed": 0},
        }
    ]
    assert exit_code == 0

    fetcher_instance = instances[0]
    assert fetcher_instance.correlations[0].endswith(":2024-01-01")

    events = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "agentlab.cli.garmin_fetch"
    ]
    assert any(event["event"] == "garmin.cli.run.completed" for event in events)


def test_main_reports_failures_and_non_zero_exit(tmp_path, monkeypatch, capsys, caplog):
    outcome = FetchOutcome(
        results=[],
        errors=[
            EndpointError(
                endpoint="alpha",
                scope={},
                message="boom",
                traceback="traceback",
            )
        ],
    )
    StubFetcher.outcome = outcome
    instances: list[StubFetcher] = []

    def factory() -> StubFetcher:
        instance = StubFetcher()
        instances.append(instance)
        return instance

    monkeypatch.setattr(garmin_fetch, "GarminDataFetcher", factory)

    config_path = tmp_path / "config.toml"
    _write_config(config_path)

    caplog.set_level(logging.INFO, logger="agentlab.cli.garmin_fetch")

    exit_code = garmin_fetch.main(
        [
            "--date",
            "2024-01-02",
            "--config",
            str(config_path),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary == [
        {
            "date": "2024-01-02",
            "successes": [],
            "failures": [{"endpoint": "alpha", "message": "boom"}],
            "retry_outcomes": {"scheduled": 0, "succeeded": 0, "failed": 0},
        }
    ]
    assert exit_code == 1

    fetcher_instance = instances[0]
    assert fetcher_instance.correlations[0].endswith(":2024-01-02")

    events = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "agentlab.cli.garmin_fetch"
    ]
    failure_events = [event for event in events if event["event"] == "garmin.cli.run.failed"]
    assert failure_events, "Expected garmin.cli.run.failed log entry"
