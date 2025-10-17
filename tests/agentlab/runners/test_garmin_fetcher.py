from __future__ import annotations

import json
import logging
import random
from datetime import date

import pytest

from agentlab.core.garmin import EndpointResult, GarminCredentials, GarminFetchRequest
from agentlab.runners.garmin_fetcher import (
    EndpointHandler,
    GarminDataFetcher,
    GarminPacingConfig,
    _fetch_activities,
    _fetch_activity_detail,
)


def test_supported_endpoints_matches_registry():
    fetcher = GarminDataFetcher()
    assert fetcher.supported_endpoints == [
        "user-profile",
        "user-profile-settings",
        "full-name",
        "unit-system",
        "user-summary",
        "stats",
        "stats-and-body",
        "steps-data",
        "floors",
        "daily-steps",
        "heart-rates",
        "body-composition",
        "weigh-ins",
        "daily-weigh-ins",
        "body-battery",
        "body-battery-events",
        "blood-pressure",
        "max-metrics",
        "hydration",
        "respiration",
        "spo2",
        "intensity-minutes",
        "all-day-stress",
        "all-day-events",
        "sleep",
        "stress",
        "resting-heart-rate",
        "hrv",
        "training-readiness",
        "training-status",
        "endurance-score",
        "hill-score",
        "fitness-age",
        "race-predictions",
        "progress-summary",
        "goals",
        "earned-badges",
        "personal-records",
        "adhoc-challenges",
        "badge-challenges",
        "available-badge-challenges",
        "non-completed-badge-challenges",
        "in-progress-virtual-challenges",
        "menstrual-dayview",
        "menstrual-calendar",
        "pregnancy-summary",
        "activities",
        "activities-by-date",
        "activities-for-date",
        "last-activity",
        "activity-types",
        "activity-detail",
        "activity-splits",
        "activity-typed-splits",
        "activity-split-summaries",
        "activity-weather",
        "activity-hr-timezones",
        "activity-exercise-sets",
        "activity-gear",
        "activity-download",
        "gear",
        "gear-stats",
        "gear-defaults",
        "gear-activities",
        "devices",
        "device-settings",
        "device-last-used",
        "device-solar",
        "device-alarms",
        "primary-training-device",
        "workouts",
        "workout-detail",
        "workout-download",
    ]


class DummyGarmin:
    def __init__(self, *args: object, **kwargs: object) -> None:
        self.calls: list[str] = []

    def login(self) -> None:
        self.calls.append("login")


def _dummy_handler(name: str, response: object):
    def execute(
        client: DummyGarmin,
        request: GarminFetchRequest,
        _context,
    ) -> list[EndpointResult]:
        client.calls.append(name)
        return [
            EndpointResult(
                endpoint=name,
                scope={"start": request.start_date.isoformat()},
                payload=response,
            )
        ]

    return EndpointHandler(name=name, execute=execute)


def test_fetch_invokes_requested_endpoints_in_order():
    handlers = [
        _dummy_handler("alpha", {"value": 1}),
        _dummy_handler("beta", {"value": 2}),
        _dummy_handler("gamma", {"value": 3}),
    ]

    class Factory(DummyGarmin):
        created: DummyGarmin | None = None

        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            Factory.created = self

    pacing = GarminPacingConfig(
        post_login_delay=0.0,
        between_endpoints_delay=0.0,
        pagination_delay=0.0,
        jitter_ratio=0.0,
        retry_limit=0,
    )
    fetcher = GarminDataFetcher(
        client_factory=Factory,
        handlers=handlers,
        pacing=pacing,
        sleep=lambda _: None,
        random_source=random.Random(0),
    )
    request = GarminFetchRequest(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 1),
        endpoints=["beta", "gamma"],
    )
    credentials = GarminCredentials(username="user", password="pass")

    observed: list[str] = []
    outcome = fetcher.fetch(credentials, request, observer=observed.append)

    assert [result.endpoint for result in outcome.results] == ["beta", "gamma"]
    assert outcome.results[0].payload == {"value": 2}
    assert outcome.results[1].payload == {"value": 3}
    assert outcome.errors == []
    assert observed == ["beta", "gamma"]

    assert Factory.created is not None
    assert Factory.created.calls == ["login", "beta", "gamma"]


def test_fetch_collects_errors(caplog):
    def failing_handler(client: DummyGarmin, request: GarminFetchRequest, _context):
        raise RuntimeError("boom")

    handlers = [
        EndpointHandler(name="alpha", execute=failing_handler),
    ]

    pacing = GarminPacingConfig(
        post_login_delay=0.0,
        between_endpoints_delay=0.0,
        pagination_delay=0.0,
        jitter_ratio=0.0,
        retry_limit=1,
    )
    fetcher = GarminDataFetcher(
        client_factory=DummyGarmin,
        handlers=handlers,
        pacing=pacing,
        sleep=lambda _: None,
        random_source=random.Random(0),
    )
    request = GarminFetchRequest(start_date=date(2024, 1, 1), end_date=date(2024, 1, 1))
    credentials = GarminCredentials(username="user", password="pass")

    caplog.set_level(logging.INFO, logger="agentlab.runners.garmin_fetcher")

    outcome = fetcher.fetch(
        credentials,
        request,
        correlation_id="run-123",
    )

    assert outcome.results == []
    assert len(outcome.errors) == 1
    error = outcome.errors[0]
    assert error.endpoint == "alpha"
    assert "boom" in error.message
    assert "RuntimeError" in error.traceback

    events = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "agentlab.runners.garmin_fetcher"
    ]
    error_events = [event for event in events if event["event"] == "garmin.endpoint.error"]
    assert error_events, "Expected garmin.endpoint.error log entry"
    assert len(error_events) == 2  # initial attempt + retry
    for error_event in error_events:
        assert error_event["correlation_id"] == "run-123"
        assert error_event["endpoint"] == "alpha"
    assert outcome.retries.scheduled == 1
    assert outcome.retries.succeeded == 0
    assert outcome.retries.failed == 1


def test_fetch_retries_failed_endpoint_once():
    attempt_counter = 0

    def flaky_handler(client: DummyGarmin, request: GarminFetchRequest, _context):
        nonlocal attempt_counter
        attempt_counter += 1
        if attempt_counter == 1:
            raise RuntimeError("temp failure")
        return [
            EndpointResult(
                endpoint="alpha",
                scope={"start": request.start_date.isoformat()},
                payload={"value": 42},
            )
        ]

    handlers = [EndpointHandler(name="alpha", execute=flaky_handler)]
    pacing = GarminPacingConfig(
        post_login_delay=0.0,
        between_endpoints_delay=0.0,
        pagination_delay=0.0,
        jitter_ratio=0.0,
        retry_limit=1,
    )
    fetcher = GarminDataFetcher(
        client_factory=DummyGarmin,
        handlers=handlers,
        pacing=pacing,
        sleep=lambda _: None,
        random_source=random.Random(0),
    )
    request = GarminFetchRequest(start_date=date(2024, 1, 1), end_date=date(2024, 1, 1))
    credentials = GarminCredentials(username="user", password="pass")

    outcome = fetcher.fetch(credentials, request)

    assert attempt_counter == 2
    assert [result.endpoint for result in outcome.results] == ["alpha"]
    assert outcome.errors == []
    assert outcome.retries.scheduled == 1
    assert outcome.retries.succeeded == 1
    assert outcome.retries.failed == 0


def test_fetch_applies_configured_delays():
    sleep_calls: list[float] = []

    def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    class PacingDummy(DummyGarmin):
        def call_alpha(self) -> None:
            self.calls.append("call_alpha")

        def fetch_page(self) -> dict[str, int]:
            self.calls.append("fetch_page")
            return {"page": len([name for name in self.calls if name == "fetch_page"])}

    def alpha_handler(client: PacingDummy, request: GarminFetchRequest, _context):
        client.call_alpha()
        return [
            EndpointResult(endpoint="alpha", scope={}, payload={"value": 1}),
        ]

    def beta_handler(client: PacingDummy, request: GarminFetchRequest, _context):
        client.fetch_page()
        client.fetch_page()
        return [
            EndpointResult(endpoint="beta", scope={}, payload={"value": 2}),
        ]

    handlers = [
        EndpointHandler(name="alpha", execute=alpha_handler),
        EndpointHandler(name="beta", execute=beta_handler),
    ]
    pacing = GarminPacingConfig(
        post_login_delay=0.5,
        between_endpoints_delay=0.2,
        pagination_delay=0.1,
        jitter_ratio=0.0,
        retry_limit=0,
    )
    fetcher = GarminDataFetcher(
        client_factory=PacingDummy,
        handlers=handlers,
        pacing=pacing,
        sleep=fake_sleep,
        random_source=random.Random(0),
    )
    request = GarminFetchRequest(start_date=date(2024, 1, 1), end_date=date(2024, 1, 1))
    credentials = GarminCredentials(username="user", password="pass")

    outcome = fetcher.fetch(credentials, request)

    assert sleep_calls == [0.5, 0.2, 0.1]
    assert [result.endpoint for result in outcome.results] == ["alpha", "beta"]


def test_fetch_logs_login_success(caplog):
    class LoginDummy(DummyGarmin):
        def login(self) -> None:
            super().login()

    fetcher = GarminDataFetcher(
        client_factory=LoginDummy,
        handlers=[],
        pacing=GarminPacingConfig(
            post_login_delay=0.0,
            between_endpoints_delay=0.0,
            pagination_delay=0.0,
            jitter_ratio=0.0,
            retry_limit=0,
        ),
        sleep=lambda _: None,
        random_source=random.Random(0),
    )
    request = GarminFetchRequest(start_date=date(2024, 1, 1), end_date=date(2024, 1, 1))
    credentials = GarminCredentials(username="user", password="pass")

    caplog.set_level(logging.INFO, logger="agentlab.runners.garmin_fetcher")

    fetcher.fetch(credentials, request, correlation_id="run-login")

    events = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "agentlab.runners.garmin_fetcher"
    ]
    login_events = [event for event in events if event["event"] == "garmin.login.success"]
    assert login_events
    assert login_events[0]["username"] == "user"
    assert login_events[0]["method"] == "login"


def test_fetch_logs_login_failure(caplog):
    class FailingLogin(DummyGarmin):
        def login(self) -> None:
            raise RuntimeError("bad credentials")

    fetcher = GarminDataFetcher(
        client_factory=FailingLogin,
        handlers=[],
        pacing=GarminPacingConfig(
            post_login_delay=0.0,
            between_endpoints_delay=0.0,
            pagination_delay=0.0,
            jitter_ratio=0.0,
            retry_limit=0,
        ),
        sleep=lambda _: None,
        random_source=random.Random(0),
    )
    request = GarminFetchRequest(start_date=date(2024, 1, 1), end_date=date(2024, 1, 1))
    credentials = GarminCredentials(username="user", password="pass")

    caplog.set_level(logging.INFO, logger="agentlab.runners.garmin_fetcher")

    with pytest.raises(RuntimeError):
        fetcher.fetch(credentials, request, correlation_id="run-login-fail")

    events = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "agentlab.runners.garmin_fetcher"
    ]
    failure_events = [event for event in events if event["event"] == "garmin.login.failed"]
    assert failure_events
    assert failure_events[0]["error_message"] == "bad credentials"
    assert failure_events[0]["method"] == "login"


def test_activity_detail_handlers_emit_activity_id():
    class ActivityClient(DummyGarmin):
        created: "ActivityClient | None" = None

        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            self.activities_payload = [
                {"activityId": "101"},
                {"activityId": "202"},
            ]
            self.activities_by_date_calls: list[tuple[str, str]] = []
            self.activities_for_date_calls: list[str] = []
            self.activity_calls: list[str] = []
            ActivityClient.created = self

        def get_activities(self, *_args: object, **_kwargs: object) -> list[dict[str, str]]:
            raise AssertionError("get_activities should not be called for per-day requests")

        def get_activities_by_date(self, start: str, end: str) -> list[dict[str, str]]:
            self.activities_by_date_calls.append((start, end))
            return self.activities_payload

        def get_activities_fordate(self, day: str) -> list[dict[str, str]]:
            self.activities_for_date_calls.append(day)
            return []

        def get_activity(self, activity_id: str) -> dict[str, str]:
            self.activity_calls.append(activity_id)
            return {"activityId": activity_id, "detail": "ok"}

    handlers = [
        EndpointHandler(name="activities", execute=_fetch_activities),
        EndpointHandler(name="activity-detail", execute=_fetch_activity_detail),
    ]
    fetcher = GarminDataFetcher(
        client_factory=ActivityClient,
        handlers=handlers,
        pacing=GarminPacingConfig(
            post_login_delay=0.0,
            between_endpoints_delay=0.0,
            pagination_delay=0.0,
            jitter_ratio=0.0,
            retry_limit=0,
        ),
        sleep=lambda _: None,
        random_source=random.Random(0),
    )
    request = GarminFetchRequest(start_date=date(2024, 1, 1), end_date=date(2024, 1, 1))
    credentials = GarminCredentials(username="user", password="pass")

    outcome = fetcher.fetch(credentials, request)

    assert len(outcome.results) == 3  # 1 activities + 2 detail entries
    detail_results = [result for result in outcome.results if result.endpoint == "activity-detail"]
    assert [result.scope["activityId"] for result in detail_results] == ["101", "202"]

    client = ActivityClient.created
    assert client is not None
    assert client.activities_by_date_calls == [("2024-01-01", "2024-01-01")]
    assert client.activities_for_date_calls == []
    assert client.activity_calls == ["101", "202"]
