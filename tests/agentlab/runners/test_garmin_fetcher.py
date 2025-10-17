from __future__ import annotations

from datetime import date

from agentlab.core.garmin import EndpointResult, GarminCredentials, GarminFetchRequest
from agentlab.runners.garmin_fetcher import EndpointHandler, GarminDataFetcher


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

    fetcher = GarminDataFetcher(client_factory=Factory, handlers=handlers)
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


def test_fetch_collects_errors():
    def failing_handler(client: DummyGarmin, request: GarminFetchRequest, _context):
        raise RuntimeError("boom")

    handlers = [
        EndpointHandler(name="alpha", execute=failing_handler),
    ]

    fetcher = GarminDataFetcher(client_factory=DummyGarmin, handlers=handlers)
    request = GarminFetchRequest(start_date=date(2024, 1, 1), end_date=date(2024, 1, 1))
    credentials = GarminCredentials(username="user", password="pass")

    outcome = fetcher.fetch(credentials, request)

    assert outcome.results == []
    assert len(outcome.errors) == 1
    error = outcome.errors[0]
    assert error.endpoint == "alpha"
    assert "boom" in error.message
    assert "RuntimeError" in error.traceback
