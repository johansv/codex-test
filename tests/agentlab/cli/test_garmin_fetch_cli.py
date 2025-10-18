from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pytest

from agentlab.cli import garmin_fetch
from agentlab.core.garmin import EndpointError, EndpointResult, FetchOutcome, RetrySummary


CONFIG_TEMPLATE = """
[defaults]
enabled = ["alpha"]
"""


class StubFetcher:
    """Test double that records correlation IDs."""

    outcome: FetchOutcome

    def __init__(self, *args, **kwargs) -> None:
        self.supported_endpoints = ["alpha"]
        self.correlations: list[str | None] = []
        self.outcome = getattr(self.__class__, "outcome")
        self.pacing = kwargs.get("pacing")

    def fetch(
        self,
        credentials,
        request,
        observer=None,
        *,
        correlation_id=None,
        result_callback=None,
        error_callback=None,
    ) -> FetchOutcome:
        self.correlations.append(correlation_id)
        results: list[EndpointResult] = []
        if result_callback:
            for result in self.outcome.results:
                result_callback(result)
                results.append(
                    EndpointResult(
                        endpoint=result.endpoint,
                        scope=result.scope,
                        payload=None,
                    )
                )
        else:
            results = list(self.outcome.results)

        if error_callback:
            for error in self.outcome.errors:
                error_callback(error)
        errors = list(self.outcome.errors)

        return FetchOutcome(results=results, errors=errors, retries=self.outcome.retries)


@pytest.fixture(autouse=True)
def _credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")


def _write_config(path: Path) -> None:
    path.write_text(CONFIG_TEMPLATE.strip(), encoding="utf-8")


def _install_stub_fetcher(monkeypatch, instances: list[StubFetcher]) -> None:
    def factory(*args, **kwargs) -> StubFetcher:
        instance = StubFetcher(*args, **kwargs)
        instances.append(instance)
        return instance

    monkeypatch.setattr(garmin_fetch, "GarminDataFetcher", factory)


def test_main_reports_success_summary(tmp_path, monkeypatch, capsys, caplog):
    outcome = FetchOutcome(
        results=[
            EndpointResult(endpoint="alpha", scope={}, payload={"value": 1}),
        ],
        errors=[],
        retries=RetrySummary(),
    )
    StubFetcher.outcome = outcome
    instances: list[StubFetcher] = []
    _install_stub_fetcher(monkeypatch, instances)

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
    assert fetcher_instance.pacing is not None
    assert fetcher_instance.pacing.post_login_delay == 5.0
    assert fetcher_instance.pacing.between_endpoints_delay == 2.0
    assert fetcher_instance.pacing.pagination_delay == 1.0
    assert fetcher_instance.pacing.jitter_ratio == 0.2
    assert fetcher_instance.pacing.retry_limit == 1

    events = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "agentlab.cli.garmin_fetch"
    ]
    assert any(event["event"] == "garmin.cli.run.completed" for event in events)
    assert not any(event["event"] == "garmin.cli.config" for event in events)


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
        retries=RetrySummary(scheduled=1, succeeded=0, failed=1),
    )
    StubFetcher.outcome = outcome
    instances: list[StubFetcher] = []
    _install_stub_fetcher(monkeypatch, instances)

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
            "retry_outcomes": {"scheduled": 1, "succeeded": 0, "failed": 1},
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


def test_main_debug_logs_configuration_snapshot(tmp_path, monkeypatch, capsys, caplog):
    outcome = FetchOutcome(
        results=[EndpointResult(endpoint="alpha", scope={}, payload={"value": 1})],
        errors=[],
        retries=RetrySummary(),
    )
    StubFetcher.outcome = outcome
    instances: list[StubFetcher] = []
    _install_stub_fetcher(monkeypatch, instances)

    config_path = tmp_path / "config.toml"
    _write_config(config_path)

    caplog.set_level(logging.INFO, logger="agentlab.cli.garmin_fetch")

    exit_code = garmin_fetch.main(
        [
            "--date",
            "2024-01-04",
            "--config",
            str(config_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--debug",
        ]
    )

    assert exit_code == 0

    events = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "agentlab.cli.garmin_fetch"
    ]
    config_events = [event for event in events if event["event"] == "garmin.cli.config"]
    assert config_events, "Expected configuration snapshot event when debug is enabled"
    settings = config_events[0]["settings"]
    assert settings["username"] == "user@example.com"
    assert settings["debug"] is True
    assert settings["pacing"]["retry_limit"] == 1
    assert "password" not in {key.lower() for key in settings.keys()}


def test_main_loads_credentials_from_dotenv(tmp_path, monkeypatch, capsys):
    StubFetcher.outcome = FetchOutcome(
        results=[EndpointResult(endpoint="alpha", scope={}, payload={"value": 1})],
        errors=[],
        retries=RetrySummary(),
    )
    instances: list[StubFetcher] = []
    _install_stub_fetcher(monkeypatch, instances)

    config_path = tmp_path / "config.toml"
    _write_config(config_path)

    env_path = tmp_path / ".env"
    env_path.write_text(
        "GARMIN_EMAIL=dotenv@example.com\nGARMIN_PASSWORD=from-dotenv\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GARMIN_EMAIL", raising=False)
    monkeypatch.delenv("GARMIN_PASSWORD", raising=False)

    exit_code = garmin_fetch.main(
        [
            "--date",
            "2024-01-03",
            "--config",
            str(config_path),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary[0]["successes"] == ["alpha"]
    assert exit_code == 0
    assert os.getenv("GARMIN_EMAIL") == "dotenv@example.com"
    assert os.getenv("GARMIN_PASSWORD") == "from-dotenv"
    monkeypatch.delenv("GARMIN_EMAIL", raising=False)
    monkeypatch.delenv("GARMIN_PASSWORD", raising=False)
