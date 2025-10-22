from __future__ import annotations

import json
import logging
import os
from datetime import date
from pathlib import Path

import pytest

from agentlab.cli import garmin_fetch
from agentlab.runners.garmin_fetcher import RateLimitExceeded
from agentlab.core.garmin import EndpointError, EndpointResult, FetchOutcome, RetrySummary


CONFIG_TEMPLATE = """
[defaults]
enabled = ["alpha"]
"""


class StubFetcher:
    """Test double that records correlation IDs."""

    outcome: FetchOutcome
    outcomes: list[FetchOutcome] | None = None
    run_date_endpoints: list[str] = []
    per_day_subset: list[str] | None = None

    def __init__(self, *args, **kwargs) -> None:
        self.supported_endpoints = ["alpha", "beta"]
        self.correlations: list[str | None] = []
        self.outcome = getattr(self.__class__, "outcome")
        self.pacing = kwargs.get("pacing")
        self.requests = []
        self._queued_outcomes = list(self.__class__.outcomes or [])

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
        self.requests.append(request)
        current_outcome = (
            self._queued_outcomes.pop(0) if self._queued_outcomes else self.outcome
        )
        results: list[EndpointResult] = []
        if result_callback:
            for result in current_outcome.results:
                result_callback(result)
                results.append(
                    EndpointResult(
                        endpoint=result.endpoint,
                        scope=result.scope,
                        payload=None,
                    )
                )
        else:
            results = list(current_outcome.results)

        if error_callback:
            for error in current_outcome.errors:
                error_callback(error)
        errors = list(current_outcome.errors)

        return FetchOutcome(results=results, errors=errors, retries=current_outcome.retries)

    def partition_endpoints(self, endpoints):
        run_set = set(self.__class__.run_date_endpoints or [])
        run_group = [name for name in endpoints if name in run_set]
        subset = self.__class__.per_day_subset
        if subset is None:
            per_day_group = [name for name in endpoints if name not in run_set]
        else:
            allowed = set(subset)
            per_day_group = [name for name in endpoints if name in allowed]
        return run_group, per_day_group


@pytest.fixture(autouse=True)
def _reset_stub_fetcher_state():
    StubFetcher.run_date_endpoints = []
    StubFetcher.per_day_subset = None
    StubFetcher.outcomes = None
    yield
    StubFetcher.run_date_endpoints = []
    StubFetcher.per_day_subset = None
    StubFetcher.outcomes = None


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


def test_main_handles_rate_limit(tmp_path, monkeypatch, capsys, caplog):
    class RateLimitFetcher:
        def __init__(self, *args, **kwargs) -> None:
            self.supported_endpoints = ["alpha"]
            self.correlations: list[str | None] = []
            self.requests = []
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
            self.requests.append(request)
            raise RateLimitExceeded("429 Too Many Requests", wait_minutes=10)

    def factory(*args, **kwargs) -> RateLimitFetcher:
        return RateLimitFetcher(*args, **kwargs)

    monkeypatch.setattr(garmin_fetch, "GarminDataFetcher", factory)

    config_path = tmp_path / "config.toml"
    _write_config(config_path)

    caplog.set_level(logging.INFO, logger="agentlab.cli.garmin_fetch")

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
    assert summary == [
        {
            "date": "2024-01-03",
            "successes": [],
            "failures": [{"endpoint": "rate-limit", "message": "429 Too Many Requests"}],
            "retry_outcomes": {"scheduled": 0, "succeeded": 0, "failed": 0},
            "rate_limited": True,
        }
    ]
    assert exit_code == 1
    assert "Wait at least 10 minutes" in captured.err

    events = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "agentlab.cli.garmin_fetch"
    ]
    rate_events = [event for event in events if event["event"] == "garmin.cli.rate_limit"]
    assert rate_events
    assert rate_events[0]["wait_minutes"] == 10


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


def test_main_runs_run_date_endpoints_once(tmp_path, monkeypatch, capsys):
    run_date = date(2024, 1, 5)

    class FixedDate(date):
        @classmethod
        def today(cls) -> "FixedDate":
            return cls(run_date.year, run_date.month, run_date.day)

    StubFetcher.outcome = FetchOutcome(results=[], errors=[], retries=RetrySummary())
    StubFetcher.outcomes = [
        FetchOutcome(
            results=[EndpointResult(endpoint="beta", scope={}, payload={"value": 2})],
            errors=[],
            retries=RetrySummary(),
        ),
        FetchOutcome(
            results=[EndpointResult(endpoint="alpha", scope={}, payload={"value": 1})],
            errors=[],
            retries=RetrySummary(),
        ),
    ]
    StubFetcher.run_date_endpoints = ["beta"]

    instances: list[StubFetcher] = []
    _install_stub_fetcher(monkeypatch, instances)
    monkeypatch.setattr(garmin_fetch, "date", FixedDate)

    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[defaults]
enabled = ["alpha", "beta"]
        """.strip(),
        encoding="utf-8",
    )

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
            "date": run_date.isoformat(),
            "successes": ["beta"],
            "failures": [],
            "retry_outcomes": {"scheduled": 0, "succeeded": 0, "failed": 0},
            "run_date": True,
        },
        {
            "date": "2024-01-01",
            "successes": ["alpha"],
            "failures": [],
            "retry_outcomes": {"scheduled": 0, "succeeded": 0, "failed": 0},
        },
    ]
    assert exit_code == 0

    fetcher_instance = instances[0]
    assert len(fetcher_instance.requests) == 2
    run_request, day_request = fetcher_instance.requests
    assert run_request.start_date == run_date
    assert run_request.end_date == run_date
    assert list(run_request.endpoints) == ["beta"]
    assert day_request.start_date.isoformat() == "2024-01-01"
    assert list(day_request.endpoints) == ["alpha"]

    out_dir = tmp_path / "out"
    run_date_dir = out_dir / run_date.isoformat()
    per_day_dir = out_dir / "2024-01-01"
    assert (run_date_dir / "beta.json").exists()
    assert (per_day_dir / "alpha.json").exists()


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


def test_main_supports_named_preset(tmp_path, monkeypatch):
    StubFetcher.outcome = FetchOutcome(
        results=[EndpointResult(endpoint="beta", scope={}, payload={"value": 1})],
        errors=[],
        retries=RetrySummary(),
    )
    instances: list[StubFetcher] = []
    _install_stub_fetcher(monkeypatch, instances)

    config_text = """
[presets.one]
enabled = ["alpha"]
disabled = []

[presets.two]
enabled = ["beta"]
disabled = []

[defaults]
preset = "one"
"""
    config_path = tmp_path / "config.toml"
    config_path.write_text(config_text.strip(), encoding="utf-8")

    exit_code = garmin_fetch.main(
        [
            "--date",
            "2024-01-06",
            "--config",
            str(config_path),
            "--preset",
            "two",
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )

    assert exit_code == 0
    fetcher_instance = instances[0]
    assert fetcher_instance.requests
    assert fetcher_instance.requests[0].endpoints == ["beta"]


def test_main_supports_multiple_presets_union(tmp_path, monkeypatch):
    StubFetcher.outcome = FetchOutcome(
        results=[EndpointResult(endpoint="beta", scope={}, payload={"value": 1})],
        errors=[],
        retries=RetrySummary(),
    )
    instances: list[StubFetcher] = []
    _install_stub_fetcher(monkeypatch, instances)

    config_text = """
[presets.alpha]
enabled = ["alpha"]
disabled = []

[presets.beta]
enabled = ["beta"]
disabled = []

[defaults]
preset = "alpha"
"""
    config_path = tmp_path / "config.toml"
    config_path.write_text(config_text.strip(), encoding="utf-8")

    exit_code = garmin_fetch.main(
        [
            "--date",
            "2024-01-06",
            "--config",
            str(config_path),
            "--preset",
            "alpha,beta",
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )

    assert exit_code == 0
    fetcher_instance = instances[0]
    assert fetcher_instance.requests
    assert fetcher_instance.requests[0].endpoints == ["alpha", "beta"]


def test_main_multiple_presets_enforces_disabled_union(tmp_path, monkeypatch):
    StubFetcher.outcome = FetchOutcome(
        results=[EndpointResult(endpoint="alpha", scope={}, payload={"value": 1})],
        errors=[],
        retries=RetrySummary(),
    )
    instances: list[StubFetcher] = []
    _install_stub_fetcher(monkeypatch, instances)

    config_text = """
[presets.alpha]
enabled = ["alpha"]
disabled = ["beta"]

[presets.extra]
enabled = ["alpha"]
disabled = []

[defaults]
preset = "alpha"
"""
    config_path = tmp_path / "config.toml"
    config_path.write_text(config_text.strip(), encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        garmin_fetch.main(
            [
                "--date",
                "2024-01-06",
                "--config",
                str(config_path),
                "--preset",
                "alpha,extra",
                "--include",
                "beta",
                "--output-dir",
                str(tmp_path / "out"),
            ]
        )

    assert str(excinfo.value) == "Endpoint(s) disabled via configuration: beta"


def test_main_multiple_presets_rejects_unknown_name(tmp_path, monkeypatch):
    StubFetcher.outcome = FetchOutcome(
        results=[EndpointResult(endpoint="alpha", scope={}, payload={"value": 1})],
        errors=[],
        retries=RetrySummary(),
    )
    instances: list[StubFetcher] = []
    _install_stub_fetcher(monkeypatch, instances)

    config_text = """
[presets.alpha]
enabled = ["alpha"]
disabled = []

[defaults]
preset = "alpha"
"""
    config_path = tmp_path / "config.toml"
    config_path.write_text(config_text.strip(), encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        garmin_fetch.main(
            [
                "--date",
                "2024-01-06",
                "--config",
                str(config_path),
                "--preset",
                "alpha,missing",
                "--output-dir",
                str(tmp_path / "out"),
            ]
        )

    assert (
        str(excinfo.value)
        == "Unknown endpoint preset(s) missing. Available presets: alpha"
    )
