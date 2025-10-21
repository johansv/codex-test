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
    RateLimitExceeded,
    _fetch_activities,
    _fetch_activities_by_date,
    _fetch_activities_for_date,
    _fetch_activity_detail,
    _fetch_activity_details,
    _fetch_activity_download,
    _fetch_body_composition,
    _fetch_gear,
    _fetch_gear_activities,
    _fetch_gear_stats,
    _fetch_in_progress_virtual_challenges,
    _fetch_race_predictions,
    _fetch_progress_summary,
    _fetch_workout_detail,
    _fetch_device_settings,
    _fetch_device_last_used,
    _fetch_device_solar,
    _fetch_device_alarms,
    _fetch_primary_training_device,

    _fetch_workout_download,
    GarminFetchContext,
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
        "activity-details",
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


def test_fetch_raises_rate_limit_on_login(caplog):
    class RateLimitedLogin(DummyGarmin):
        def login(self) -> None:
            raise RuntimeError("429 Too Many Requests")

    fetcher = GarminDataFetcher(
        client_factory=RateLimitedLogin,
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

    with pytest.raises(RateLimitExceeded):
        fetcher.fetch(credentials, request, correlation_id="rate-limit-login")

    events = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "agentlab.runners.garmin_fetcher"
    ]
    rate_events = [event for event in events if event["event"] == "garmin.rate-limit"]
    assert rate_events
    assert rate_events[0]["phase"] == "login"
    assert rate_events[0]["wait_minutes"] == 10


def test_fetch_reuses_session_across_calls(caplog):
    class SessionClient(DummyGarmin):
        created_count = 0
        login_count = 0
        last_instance: "SessionClient | None" = None

        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            SessionClient.created_count += 1
            SessionClient.last_instance = self

        def login(self) -> None:
            SessionClient.login_count += 1
            super().login()

    handlers = [
        _dummy_handler("alpha", {"value": 1}),
    ]
    pacing = GarminPacingConfig(
        post_login_delay=0.0,
        between_endpoints_delay=0.0,
        pagination_delay=0.0,
        jitter_ratio=0.0,
        retry_limit=0,
    )
    fetcher = GarminDataFetcher(
        client_factory=SessionClient,
        handlers=handlers,
        pacing=pacing,
        sleep=lambda _: None,
        random_source=random.Random(0),
    )
    request = GarminFetchRequest(start_date=date(2024, 1, 1), end_date=date(2024, 1, 1))
    credentials = GarminCredentials(username="user", password="pass")

    caplog.set_level(logging.INFO, logger="agentlab.runners.garmin_fetcher")

    first = fetcher.fetch(credentials, request, correlation_id="reuse-1")
    second = fetcher.fetch(credentials, request, correlation_id="reuse-2")

    assert [result.endpoint for result in first.results] == ["alpha"]
    assert [result.endpoint for result in second.results] == ["alpha"]

    assert SessionClient.created_count == 1
    assert SessionClient.login_count == 1
    assert SessionClient.last_instance is not None
    assert SessionClient.last_instance.calls == ["login", "alpha", "alpha"]

    events = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "agentlab.runners.garmin_fetcher"
    ]
    login_events = [event for event in events if event["event"] == "garmin.login.success"]
    assert len(login_events) == 1


def test_fetch_raises_rate_limit_during_endpoint(caplog):
    def rate_limited_handler(client: DummyGarmin, request: GarminFetchRequest, _context):
        raise RuntimeError("HTTP 429 Too Many Requests")

    handlers = [
        EndpointHandler(name="alpha", execute=rate_limited_handler),
    ]
    fetcher = GarminDataFetcher(
        client_factory=DummyGarmin,
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

    caplog.set_level(logging.INFO, logger="agentlab.runners.garmin_fetcher")

    with pytest.raises(RateLimitExceeded):
        fetcher.fetch(credentials, request, correlation_id="rate-limit-endpoint")

    events = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "agentlab.runners.garmin_fetcher"
    ]
    rate_events = [event for event in events if event["event"] == "garmin.rate-limit"]
    assert rate_events
    assert rate_events[0]["phase"] == "endpoint"
    assert rate_events[0]["endpoint"] == "alpha"


def test_fetch_in_progress_virtual_challenges_uses_start_limit():
    class VirtualChallengeClient(DummyGarmin):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            self.calls: list[tuple[int, int]] = []

        def get_inprogress_virtual_challenges(self, start: int, limit: int) -> list[dict[str, str]]:
            self.calls.append((start, limit))
            return [{"challenge": "c1"}]

    client = VirtualChallengeClient()
    request = GarminFetchRequest(start_date=date(2024, 1, 1), end_date=date(2024, 1, 1))
    context = GarminFetchContext()

    results = _fetch_in_progress_virtual_challenges(client, request, context)

    assert client.calls == [(0, 100)]
    assert len(results) == 1
    challenge_result = results[0]
    assert challenge_result.endpoint == "in-progress-virtual-challenges"
    assert challenge_result.scope == {}
    assert challenge_result.payload == [{"challenge": "c1"}]
    assert challenge_result.metadata is not None



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
            self.activity_details_calls: list[str] = []
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

        def get_activity_details(self, activity_id: str, *args: object, **kwargs: object) -> dict[str, str]:
            self.activity_details_calls.append(activity_id)
            return {"activityId": activity_id, "details": "chart"}

    handlers = [
        EndpointHandler(name="activities", execute=_fetch_activities),
        EndpointHandler(name="activity-detail", execute=_fetch_activity_detail),
        EndpointHandler(name="activity-details", execute=_fetch_activity_details),
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

    assert len(outcome.results) == 5  # activities + detail + details for each activity
    detail_results = [result for result in outcome.results if result.endpoint == "activity-detail"]
    assert [result.scope["activityId"] for result in detail_results] == ["101", "202"]
    detailed_results = [result for result in outcome.results if result.endpoint == "activity-details"]
    assert [result.scope["activityId"] for result in detailed_results] == ["101", "202"]

    client = ActivityClient.created
    assert client is not None
    assert client.activities_by_date_calls == [("2024-01-01", "2024-01-01")]
    assert client.activities_for_date_calls == []
    assert client.activity_calls == ["101", "202"]
    assert client.activity_details_calls == ["101", "202"]


def test_activity_details_fallback_to_for_date():
    class ActivityFallbackClient(DummyGarmin):
        created: "ActivityFallbackClient | None" = None

        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            self.by_date_calls: list[tuple[str, str]] = []
            self.for_date_calls: list[str] = []
            self.activity_calls: list[str] = []
            ActivityFallbackClient.created = self

        def get_activities_by_date(self, start: str, end: str) -> list[dict[str, str]]:
            self.by_date_calls.append((start, end))
            return []

        def get_activities_fordate(self, day: str) -> list[dict[str, str]]:
            self.for_date_calls.append(day)
            return [{"activityId": "999"}]

        def get_activity(self, activity_id: str) -> dict[str, str]:
            self.activity_calls.append(activity_id)
            return {"activityId": activity_id}

    handlers = [
        EndpointHandler(name="activities-by-date", execute=_fetch_activities_by_date),
        EndpointHandler(name="activities-for-date", execute=_fetch_activities_for_date),
        EndpointHandler(name="activity-detail", execute=_fetch_activity_detail),
    ]
    fetcher = GarminDataFetcher(
        client_factory=ActivityFallbackClient,
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

    detail_results = [result for result in outcome.results if result.endpoint == "activity-detail"]
    assert [result.scope["activityId"] for result in detail_results] == ["999"]

    client = ActivityFallbackClient.created
    assert client is not None
    assert client.by_date_calls == [("2024-01-01", "2024-01-01")]
    assert client.for_date_calls == ["2024-01-01"]
    assert client.activity_calls == ["999"]


def test_race_predictions_single_day_calls_daily_with_range():
    class RacePredictionClient(DummyGarmin):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

        def get_race_predictions(self, *args: object, **kwargs: object) -> dict[str, object]:
            self.calls.append((args, kwargs))
            if kwargs.get("_type") == "daily":
                return {"daily": list(args)}
            raise AssertionError(f"Unexpected call args={args} kwargs={kwargs}")

    client = RacePredictionClient()
    request = GarminFetchRequest(start_date=date(2024, 1, 1), end_date=date(2024, 1, 1))
    context = GarminFetchContext()

    results = _fetch_race_predictions(client, request, context)

    assert [result.endpoint for result in results] == ["race-predictions"]
    assert client.calls == [
        (("2024-01-01", "2024-01-01"), {"_type": "daily"}),
    ]
    assert results[0].scope == {"start": "2024-01-01", "end": "2024-01-01"}
def test_fetch_gear_uses_profile_id_when_only_id_present():
    class GearClient(DummyGarmin):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            self.received: list[str] = []

        def get_gear(self, user_profile_number: str) -> list[dict[str, str]]:
            self.received.append(user_profile_number)
            return [{"gearUuid": "g-1"}]

    context = GarminFetchContext()
    context.user_profile = {"id": 98765}
    request = GarminFetchRequest(start_date=date(2024, 1, 1), end_date=date(2024, 1, 1))

    results = _fetch_gear(GearClient(), request, context)

    assert context.gear == [{"gearUuid": "g-1"}]
    assert len(results) == 1
    gear_result = results[0]
    assert gear_result.endpoint == "gear"
    assert gear_result.scope == {"userProfileNumber": "98765"}
    assert gear_result.payload == [{"gearUuid": "g-1"}]
    assert gear_result.metadata is not None


def test_fetch_gear_stats_loads_catalog_on_demand():
    class GearStatsClient(DummyGarmin):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            self.profile_calls = 0
            self.gear_calls: list[str] = []
            self.stats_calls: list[str] = []

        def get_user_profile(self) -> dict[str, str]:
            self.profile_calls += 1
            return {"id": "123"}

        def get_gear(self, user_profile_number: str) -> list[dict[str, str]]:
            self.gear_calls.append(user_profile_number)
            return [{"uuid": "gear-1"}]

        def get_gear_stats(self, gear_uuid: str) -> dict[str, str]:
            self.stats_calls.append(gear_uuid)
            return {"uuid": gear_uuid, "distance": "42"}

    context = GarminFetchContext()
    request = GarminFetchRequest(start_date=date(2024, 1, 1), end_date=date(2024, 1, 1))

    client = GearStatsClient()
    results = _fetch_gear_stats(client, request, context)

    assert client.profile_calls == 1
    assert client.gear_calls == ["123"]
    assert client.stats_calls == ["gear-1"]
    assert context.gear == [{"uuid": "gear-1"}]
    assert context.gear_stats == {"gear-1": {"uuid": "gear-1", "distance": "42"}}
    assert len(results) == 1
    stats_result = results[0]
    assert stats_result.endpoint == "gear-stats"
    assert stats_result.scope == {"gearUuid": "gear-1"}
    assert stats_result.payload == {"uuid": "gear-1", "distance": "42"}
    assert stats_result.metadata is not None


def test_fetch_gear_activities_uses_cached_catalog():
    class GearActivitiesClient(DummyGarmin):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            self.activities_calls: list[str] = []

        def get_gear_activities(self, gear_uuid: str):
            self.activities_calls.append(gear_uuid)
            return [{"gearUuid": gear_uuid, "activityId": 99}]

    context = GarminFetchContext()
    context.gear = [{"uuid": "gear-1"}]
    request = GarminFetchRequest(start_date=date(2024, 1, 1), end_date=date(2024, 1, 1))

    client = GearActivitiesClient()
    results = _fetch_gear_activities(client, request, context)

    assert client.activities_calls == ["gear-1"]
    assert len(results) == 1
    activities_result = results[0]
    assert activities_result.endpoint == "gear-activities"
    assert activities_result.scope == {"gearUuid": "gear-1"}
    assert activities_result.payload == [{"gearUuid": "gear-1", "activityId": 99}]
    assert activities_result.metadata is not None


def test_fetch_gear_activities_supports_legacy_method():
    class LegacyGearActivitiesClient(DummyGarmin):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            self.activities_calls: list[str] = []

        def get_gear_ativities(self, gear_uuid: str):
            self.activities_calls.append(gear_uuid)
            return [{"gearUuid": gear_uuid, "activityId": 123}]

    context = GarminFetchContext()
    context.gear = [{"gearUuid": "legacy-gear"}]
    request = GarminFetchRequest(start_date=date(2024, 1, 1), end_date=date(2024, 1, 1))

    client = LegacyGearActivitiesClient()
    results = _fetch_gear_activities(client, request, context)

    assert client.activities_calls == ["legacy-gear"]
    assert len(results) == 1
    legacy_result = results[0]
    assert legacy_result.endpoint == "gear-activities"
    assert legacy_result.scope == {"gearUuid": "legacy-gear"}
    assert legacy_result.payload == [{"gearUuid": "legacy-gear", "activityId": 123}]
    assert legacy_result.metadata is not None


def test_activity_download_fetches_tcx_and_original():
    class ActivityDownloadClient(DummyGarmin):
        captured: list[tuple[str, str]] = []

        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            ActivityDownloadClient.captured = []

        def download_activity(self, activity_id: str, fmt: object) -> bytes:
            ActivityDownloadClient.captured.append((activity_id, getattr(fmt, "name", str(fmt))))
            if getattr(fmt, "name", "") == "TCX":
                return b"tcx-bytes"
            return b"fit-bytes"

    def seed_activities(
        client: ActivityDownloadClient,
        request: GarminFetchRequest,
        context: GarminFetchContext,
    ) -> list[EndpointResult]:
        context.activities = [{"activityId": "42"}]
        return [EndpointResult(endpoint="activities", scope={}, payload={})]

    handlers = [
        EndpointHandler(name="activities", execute=seed_activities),
        EndpointHandler(name="activity-download", execute=_fetch_activity_download),
    ]
    fetcher = GarminDataFetcher(
        client_factory=ActivityDownloadClient,
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

    download_results = [r for r in outcome.results if r.endpoint == "activity-download"]
    formats = sorted(result.scope["format"] for result in download_results)
    assert formats == ["ORIGINAL", "TCX"]
    assert ActivityDownloadClient.captured == [("42", "TCX"), ("42", "ORIGINAL")]

def test_body_composition_respects_request_range():
    class BodyClient(DummyGarmin):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            self.calls: list[tuple[str, str]] = []

        def get_body_composition(self, start: str, end: str) -> dict[str, str]:
            self.calls.append((start, end))
            return {"start": start, "end": end}

    client = BodyClient()
    request = GarminFetchRequest(start_date=date(2024, 1, 1), end_date=date(2024, 1, 3))
    context = GarminFetchContext()

    results = _fetch_body_composition(client, request, context)

    assert client.calls == [("2024-01-01", "2024-01-03")]
    assert [result.scope["start"] for result in results] == ["2024-01-01"]
    assert [result.scope["end"] for result in results] == ["2024-01-03"]
    assert context.activities == []


def test_progress_summary_respects_request_range():
    class ProgressClient(DummyGarmin):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            self.calls: list[tuple[str, str]] = []

        def get_progress_summary_between_dates(self, start: str, end: str) -> dict[str, str]:
            self.calls.append((start, end))
            return {"start": start, "end": end}

    client = ProgressClient()
    request = GarminFetchRequest(start_date=date(2024, 1, 1), end_date=date(2024, 1, 2))
    context = GarminFetchContext()

    results = _fetch_progress_summary(client, request, context)

    assert client.calls == [("2024-01-01", "2024-01-02")]
    assert [result.scope["start"] for result in results] == ["2024-01-01"]
    assert [result.scope["end"] for result in results] == ["2024-01-02"]


def test_activity_detail_skips_when_no_activities():
    class NoActivityClient(DummyGarmin):
        def get_activity(self, *_: object, **__: object) -> None:
            raise AssertionError("get_activity should not be called")

    client = NoActivityClient()
    request = GarminFetchRequest(start_date=date(2024, 1, 1), end_date=date(2024, 1, 1))
    context = GarminFetchContext()

    assert _fetch_activity_detail(client, request, context) == []


def test_workout_detail_skips_when_no_workouts():
    class NoWorkoutClient(DummyGarmin):
        def get_workout_by_id(self, *_: object, **__: object) -> None:
            raise AssertionError("get_workout_by_id should not be called")

        def download_workout(self, *_: object, **__: object) -> None:
            raise AssertionError("download_workout should not be called")

    client = NoWorkoutClient()
    request = GarminFetchRequest(start_date=date(2024, 1, 1), end_date=date(2024, 1, 1))
    context = GarminFetchContext()

    assert _fetch_workout_detail(client, request, context) == []
    assert _fetch_workout_download(client, request, context) == []
    assert _fetch_device_settings(client, request, context) == []
    assert _fetch_device_last_used(client, request, context) == []
    assert _fetch_device_solar(client, request, context) == []
    assert _fetch_device_alarms(client, request, context) == []
    assert _fetch_primary_training_device(client, request, context) == []


def test_gear_detail_skips_when_no_gear():
    class NoGearClient(DummyGarmin):
        def get_user_profile(self, *_: object, **__: object) -> dict[str, str]:
            return {}

        def get_user_profile(self, *_: object, **__: object) -> dict[str, str]:
            return {}

        def get_gear(self, *_: object, **__: object) -> list[dict[str, str]]:
            return []

        def get_gear_stats(self, *_: object, **__: object) -> None:
            raise AssertionError("get_gear_stats should not be called")

        def get_gear_activities(self, *_: object, **__: object):
            raise AssertionError("get_gear_activities should not be called")

        def get_device_last_used(self, *_: object, **__: object) -> None:
            raise AssertionError("get_device_last_used should not be called")

        def get_device_solar_data(self, *_: object, **__: object):
            raise AssertionError("get_device_solar_data should not be called")

        def get_device_alarms(self, *_: object, **__: object):
            raise AssertionError("get_device_alarms should not be called")

        def get_primary_training_device(self, *_: object, **__: object):
            raise AssertionError("get_primary_training_device should not be called")

    client = NoGearClient()
    request = GarminFetchRequest(start_date=date(2024, 1, 1), end_date=date(2024, 1, 1))
    context = GarminFetchContext()

    assert _fetch_gear_stats(client, request, context) == []
    assert _fetch_gear_activities(client, request, context) == []


def test_device_detail_iterates_per_device():
    class DeviceClient(DummyGarmin):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            self.settings_calls: list[str] = []
            self.solar_calls: list[str] = []

        def get_devices(self) -> list[dict[str, str]]:
            return [{"deviceId": "101"}, {"deviceId": "202"}]

        def get_device_settings(self, device_id: str) -> dict[str, str]:
            self.settings_calls.append(device_id)
            return {"id": device_id}

        def get_device_solar_data(self, device_id: str, *_: object) -> dict[str, str]:
            self.solar_calls.append(device_id)
            return {"deviceId": device_id}

    client = DeviceClient()
    request = GarminFetchRequest(start_date=date(2024, 1, 1), end_date=date(2024, 1, 1))
    context = GarminFetchContext()
    context.devices = client.get_devices()

    settings = _fetch_device_settings(client, request, context)
    solar = _fetch_device_solar(client, request, context)

    assert [result.scope["deviceId"] for result in settings] == ["101", "202"]
    assert [result.scope["deviceId"] for result in solar] == ["101", "202"]
    assert client.settings_calls == ["101", "202"]
    assert client.solar_calls == ["101", "202"]
