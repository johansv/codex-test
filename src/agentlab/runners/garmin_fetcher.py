"""Runtime helpers for collecting Garmin Connect data."""
from __future__ import annotations

import json
import logging
import random
import time
import traceback
from dataclasses import dataclass, field
from datetime import date
from functools import wraps
from typing import Any, Callable, Sequence

from garminconnect import Garmin

from agentlab.core.garmin import (
    EndpointError,
    EndpointResult,
    FetchOutcome,
    GarminCredentials,
    GarminFetchRequest,
    RetrySummary,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GarminFetchContext:
    """Hold intermediate data reused across endpoint calls."""

    activities: list[dict[str, Any]] = field(default_factory=list)
    activity_downloads: dict[str, bytes] = field(default_factory=dict)
    devices: list[dict[str, Any]] = field(default_factory=list)
    device_settings: dict[str, dict[str, Any]] = field(default_factory=dict)
    gear: list[dict[str, Any]] = field(default_factory=list)
    gear_stats: dict[str, dict[str, Any]] = field(default_factory=dict)
    workouts: list[dict[str, Any]] = field(default_factory=list)
    workout_downloads: dict[str, bytes] = field(default_factory=dict)
    user_profile: dict[str, Any] | None = None
    user_profile_settings: dict[str, Any] | None = None


@dataclass(slots=True, frozen=True)
class EndpointHandler:
    """Describe how a given endpoint is collected."""

    name: str
    execute: callable


@dataclass(slots=True, frozen=True)
class GarminPacingConfig:
    """Pacing knobs applied to Garmin API calls."""

    post_login_delay: float = 5.0
    between_endpoints_delay: float = 2.0
    pagination_delay: float = 1.0
    jitter_ratio: float = 0.2
    retry_limit: int = 1

    def __post_init__(self) -> None:
        for label, value in (
            ("post_login_delay", self.post_login_delay),
            ("between_endpoints_delay", self.between_endpoints_delay),
            ("pagination_delay", self.pagination_delay),
        ):
            if value < 0:
                raise ValueError(f"{label} must be non-negative")
        if self.jitter_ratio < 0:
            raise ValueError("jitter_ratio must be non-negative")
        if self.retry_limit < 0:
            raise ValueError("retry_limit must be non-negative")


class _PacingController:
    """Apply jittered sleeps aligned with pacing configuration."""

    def __init__(
        self,
        config: GarminPacingConfig,
        sleep_fn: Callable[[float], None],
        random_source: random.Random,
    ) -> None:
        self._config = config
        self._sleep = sleep_fn
        self._random = random_source
        self._call_counter = 0
        self._first_endpoint = True

    def after_login(self) -> None:
        self._sleep_with_jitter(self._config.post_login_delay)
        self.reset_between_endpoints()

    def reset_between_endpoints(self) -> None:
        self._first_endpoint = True

    def prepare_endpoint(self) -> None:
        if not self._first_endpoint:
            self._sleep_with_jitter(self._config.between_endpoints_delay)
        self._first_endpoint = False
        self._call_counter = 0

    def before_api_call(self) -> None:
        if self._call_counter > 0:
            self._sleep_with_jitter(self._config.pagination_delay)
        self._call_counter += 1

    def _sleep_with_jitter(self, base_delay: float) -> None:
        if base_delay <= 0:
            return
        jitter = self._config.jitter_ratio
        lower = max(0.0, 1.0 - jitter)
        upper = 1.0 + jitter
        factor = self._random.uniform(lower, upper)
        delay = base_delay * factor
        if delay > 0:
            self._sleep(delay)


class _PacedGarminClient:
    """Proxy that enforces pacing before Garmin API calls."""

    def __init__(self, client: Garmin, controller: _PacingController) -> None:
        self._client = client
        self._controller = controller

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._client, name)
        if not callable(attribute):
            return attribute

        @wraps(attribute)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            self._controller.before_api_call()
            return attribute(*args, **kwargs)

        return wrapper


class GarminDataFetcher:
    """Coordinate sequential retrieval of Garmin Connect endpoints."""

    def __init__(
        self,
        client_factory: type[Garmin] = Garmin,
        handlers: Sequence[EndpointHandler] | None = None,
        pacing: GarminPacingConfig | None = None,
        sleep: Callable[[float], None] | None = None,
        random_source: random.Random | None = None,
    ) -> None:
        self._client_factory = client_factory
        self._handlers = list(handlers) if handlers is not None else _build_default_handlers()
        self._pacing = pacing or GarminPacingConfig()
        self._sleep = sleep or time.sleep
        self._random = random_source or random.Random()

    @property
    def supported_endpoints(self) -> list[str]:
        """Return the list of endpoint identifiers."""

        return [handler.name for handler in self._handlers]

    def fetch(
        self,
        credentials: GarminCredentials,
        request: GarminFetchRequest,
        observer: Callable[[str], None] | None = None,
        *,
        correlation_id: str | None = None,
    ) -> FetchOutcome:
        """Authenticate and pull data for the requested endpoints."""

        client = self._client_factory(
            credentials.username,
            credentials.password,
            prompt_mfa=None,
            return_on_mfa=False,
        )

        login_payload = {
            "username": credentials.username,
            "method": "resume_login" if credentials.mfa_code else "login",
            "mfa_provided": bool(credentials.mfa_code),
        }
        try:
            if credentials.mfa_code:
                client.resume_login(client_state=None, mfa_code=credentials.mfa_code)
            else:
                client.login()
        except Exception as exc:  # pragma: no cover - reliance on API stability
            _log_event(
                logging.ERROR,
                "garmin.login.failed",
                correlation_id,
                error_message=str(exc),
                **login_payload,
            )
            raise
        else:
            _log_event(
                logging.INFO,
                "garmin.login.success",
                correlation_id,
                **login_payload,
            )

        controller = _PacingController(self._pacing, self._sleep, self._random)
        controller.after_login()
        paced_client = _PacedGarminClient(client, controller)

        context = GarminFetchContext()
        results: list[EndpointResult] = []
        retry_summary = RetrySummary()
        error_map: dict[str, EndpointError] = {}
        request_metadata = _request_metadata(request)

        _log_event(
            logging.INFO,
            "garmin.fetch.start",
            correlation_id,
            request=request_metadata,
        )

        def run_pass(pass_index: int, permitted: set[str] | None) -> tuple[list[EndpointResult], dict[str, EndpointError], list[str]]:
            controller.reset_between_endpoints()
            pass_results: list[EndpointResult] = []
            pass_errors: dict[str, EndpointError] = {}
            pass_successes: list[str] = []

            for handler in self._handlers:
                if permitted is not None and handler.name not in permitted:
                    continue
                if not request.includes(handler.name):
                    continue

                controller.prepare_endpoint()

                if observer:
                    observer(handler.name)

                _log_event(
                    logging.INFO,
                    "garmin.endpoint.start",
                    correlation_id,
                    request=request_metadata,
                    endpoint=handler.name,
                    attempt=pass_index,
                )
                try:
                    handler_results = handler.execute(paced_client, request, context)
                except Exception as exc:  # pragma: no cover - reliance on API stability
                    error = EndpointError(
                        endpoint=handler.name,
                        scope={},
                        message=str(exc),
                        traceback="".join(
                            traceback.format_exception(type(exc), exc, exc.__traceback__)
                        ),
                    )
                    pass_errors[handler.name] = error
                    _log_event(
                        logging.ERROR,
                        "garmin.endpoint.error",
                        correlation_id,
                        request=request_metadata,
                        endpoint=handler.name,
                        error_message=error.message,
                        attempt=pass_index,
                    )
                else:
                    pass_results.extend(handler_results)
                    pass_successes.append(handler.name)
                    _log_event(
                        logging.INFO,
                        "garmin.endpoint.success",
                        correlation_id,
                        request=request_metadata,
                        endpoint=handler.name,
                        result_count=len(handler_results),
                        scopes=[result.scope for result in handler_results],
                        attempt=pass_index,
                    )

            return pass_results, pass_errors, pass_successes

        initial_results, initial_errors, _ = run_pass(0, None)
        results.extend(initial_results)
        error_map.update(initial_errors)

        remaining = set(error_map.keys())
        attempt_index = 1

        while remaining and attempt_index <= self._pacing.retry_limit:
            retry_targets = set(remaining)
            retry_summary.scheduled += len(retry_targets)
            _log_event(
                logging.INFO,
                "garmin.fetch.retry.start",
                correlation_id,
                request=request_metadata,
                attempt=attempt_index,
                endpoints=sorted(retry_targets),
            )

            pass_results, pass_errors, pass_successes = run_pass(attempt_index, retry_targets)
            results.extend(pass_results)

            for endpoint in pass_successes:
                if endpoint in error_map:
                    del error_map[endpoint]
            retry_summary.succeeded += len(pass_successes)

            for endpoint, err in pass_errors.items():
                error_map[endpoint] = err

            remaining = set(error_map.keys())
            failed_this_attempt = len(remaining)
            _log_event(
                logging.INFO if failed_this_attempt == 0 else logging.WARNING,
                "garmin.fetch.retry.completed",
                correlation_id,
                request=request_metadata,
                attempt=attempt_index,
                succeeded=len(pass_successes),
                remaining=failed_this_attempt,
            )
            attempt_index += 1

        retry_summary.failed = len(error_map)

        _log_event(
            logging.INFO,
            "garmin.fetch.completed",
            correlation_id,
            request=request_metadata,
            result_count=len(results),
            error_count=len(error_map),
            retries=_retry_summary_payload(retry_summary),
        )

        return FetchOutcome(
            results=results,
            errors=list(error_map.values()),
            retries=retry_summary,
        )


def _build_default_handlers() -> list[EndpointHandler]:
    """Create handlers for each Garmin endpoint used by the fetcher."""

    return [
        EndpointHandler("user-profile", _fetch_user_profile),
        EndpointHandler("user-profile-settings", _fetch_user_profile_settings),
        EndpointHandler("full-name", _fetch_full_name),
        EndpointHandler("unit-system", _fetch_unit_system),
        EndpointHandler("user-summary", _fetch_user_summary),
        EndpointHandler("stats", _fetch_stats),
        EndpointHandler("stats-and-body", _fetch_stats_and_body),
        EndpointHandler("steps-data", _fetch_steps_data),
        EndpointHandler("floors", _fetch_floors),
        EndpointHandler("daily-steps", _fetch_daily_steps),
        EndpointHandler("heart-rates", _fetch_heart_rates),
        EndpointHandler("body-composition", _fetch_body_composition),
        EndpointHandler("weigh-ins", _fetch_weigh_ins),
        EndpointHandler("daily-weigh-ins", _fetch_daily_weigh_ins),
        EndpointHandler("body-battery", _fetch_body_battery),
        EndpointHandler("body-battery-events", _fetch_body_battery_events),
        EndpointHandler("blood-pressure", _fetch_blood_pressure),
        EndpointHandler("max-metrics", _fetch_max_metrics),
        EndpointHandler("hydration", _fetch_hydration),
        EndpointHandler("respiration", _fetch_respiration),
        EndpointHandler("spo2", _fetch_spo2),
        EndpointHandler("intensity-minutes", _fetch_intensity_minutes),
        EndpointHandler("all-day-stress", _fetch_all_day_stress),
        EndpointHandler("all-day-events", _fetch_all_day_events),
        EndpointHandler("sleep", _fetch_sleep),
        EndpointHandler("stress", _fetch_stress),
        EndpointHandler("resting-heart-rate", _fetch_resting_heart_rate),
        EndpointHandler("hrv", _fetch_hrv),
        EndpointHandler("training-readiness", _fetch_training_readiness),
        EndpointHandler("training-status", _fetch_training_status),
        EndpointHandler("endurance-score", _fetch_endurance_score),
        EndpointHandler("hill-score", _fetch_hill_score),
        EndpointHandler("fitness-age", _fetch_fitness_age),
        EndpointHandler("race-predictions", _fetch_race_predictions),
        EndpointHandler("progress-summary", _fetch_progress_summary),
        EndpointHandler("goals", _fetch_goals),
        EndpointHandler("earned-badges", _fetch_earned_badges),
        EndpointHandler("personal-records", _fetch_personal_records),
        EndpointHandler("adhoc-challenges", _fetch_adhoc_challenges),
        EndpointHandler("badge-challenges", _fetch_badge_challenges),
        EndpointHandler("available-badge-challenges", _fetch_available_badge_challenges),
        EndpointHandler("non-completed-badge-challenges", _fetch_non_completed_badge_challenges),
        EndpointHandler("in-progress-virtual-challenges", _fetch_in_progress_virtual_challenges),
        EndpointHandler("menstrual-dayview", _fetch_menstrual_dayview),
        EndpointHandler("menstrual-calendar", _fetch_menstrual_calendar),
        EndpointHandler("pregnancy-summary", _fetch_pregnancy_summary),
        EndpointHandler("activities", _fetch_activities),
        EndpointHandler("activities-by-date", _fetch_activities_by_date),
        EndpointHandler("activities-for-date", _fetch_activities_for_date),
        EndpointHandler("last-activity", _fetch_last_activity),
        EndpointHandler("activity-types", _fetch_activity_types),
        EndpointHandler("activity-detail", _fetch_activity_detail),
        EndpointHandler("activity-splits", _fetch_activity_splits),
        EndpointHandler("activity-typed-splits", _fetch_activity_typed_splits),
        EndpointHandler("activity-split-summaries", _fetch_activity_split_summaries),
        EndpointHandler("activity-weather", _fetch_activity_weather),
        EndpointHandler("activity-hr-timezones", _fetch_activity_hr_timezones),
        EndpointHandler("activity-exercise-sets", _fetch_activity_exercise_sets),
        EndpointHandler("activity-gear", _fetch_activity_gear),
        EndpointHandler("activity-download", _fetch_activity_download),
        EndpointHandler("gear", _fetch_gear),
        EndpointHandler("gear-stats", _fetch_gear_stats),
        EndpointHandler("gear-defaults", _fetch_gear_defaults),
        EndpointHandler("gear-activities", _fetch_gear_activities),
        EndpointHandler("devices", _fetch_devices),
        EndpointHandler("device-settings", _fetch_device_settings),
        EndpointHandler("device-last-used", _fetch_device_last_used),
        EndpointHandler("device-solar", _fetch_device_solar),
        EndpointHandler("device-alarms", _fetch_device_alarms),
        EndpointHandler("primary-training-device", _fetch_primary_training_device),
        EndpointHandler("workouts", _fetch_workouts),
        EndpointHandler("workout-detail", _fetch_workout_detail),
        EndpointHandler("workout-download", _fetch_workout_download),
    ]


def _iso(day: date) -> str:
    """Convert *day* to an ISO-8601 string."""

    return day.isoformat()


def _endpoint_result(name: str, scope: dict[str, str | int], payload: Any) -> EndpointResult:
    """Helper to construct endpoint results with consistent typing."""

    return EndpointResult(endpoint=name, scope=scope, payload=payload)


def _request_metadata(request: GarminFetchRequest) -> dict[str, Any]:
    """Return a serialisable snapshot of the request for logging."""

    return {
        "start_date": request.start_date.isoformat(),
        "end_date": request.end_date.isoformat(),
        "endpoints": sorted(request.endpoints) if request.endpoints is not None else None,
    }


def _log_event(
    level: int,
    event: str,
    correlation_id: str | None,
    **payload: Any,
) -> None:
    if not logger.isEnabledFor(level):
        return

    record = {
        "event": event,
        "correlation_id": correlation_id,
        **{key: value for key, value in payload.items() if value is not None},
    }
    logger.log(level, json.dumps(record, default=str))


def _retry_summary_payload(summary: RetrySummary) -> dict[str, int]:
    return {
        "scheduled": summary.scheduled,
        "succeeded": summary.succeeded,
        "failed": summary.failed,
    }


def _fetch_user_profile(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_user_profile()
    context.user_profile = payload
    return [_endpoint_result("user-profile", {}, payload)]


def _fetch_user_profile_settings(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_userprofile_settings()
    context.user_profile_settings = payload
    return [_endpoint_result("user-profile-settings", {}, payload)]


def _fetch_full_name(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_full_name()
    return [_endpoint_result("full-name", {}, payload)]


def _fetch_unit_system(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_unit_system()
    return [_endpoint_result("unit-system", {}, payload)]


def _fetch_user_summary(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for day in request.iter_dates():
        payload = client.get_user_summary(_iso(day))
        results.append(_endpoint_result("user-summary", {"date": _iso(day)}, payload))
    return results


def _fetch_stats(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for day in request.iter_dates():
        payload = client.get_stats(_iso(day))
        results.append(_endpoint_result("stats", {"date": _iso(day)}, payload))
    return results


def _fetch_stats_and_body(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for day in request.iter_dates():
        payload = client.get_stats_and_body(_iso(day))
        results.append(_endpoint_result("stats-and-body", {"date": _iso(day)}, payload))
    return results


def _fetch_steps_data(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for day in request.iter_dates():
        payload = client.get_steps_data(_iso(day))
        results.append(_endpoint_result("steps-data", {"date": _iso(day)}, payload))
    return results


def _fetch_floors(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for day in request.iter_dates():
        payload = client.get_floors(_iso(day))
        results.append(_endpoint_result("floors", {"date": _iso(day)}, payload))
    return results


def _fetch_daily_steps(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_daily_steps(_iso(request.start_date), _iso(request.end_date))
    return [
        _endpoint_result(
            "daily-steps",
            {"start": _iso(request.start_date), "end": _iso(request.end_date)},
            payload,
        )
    ]


def _fetch_heart_rates(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for day in request.iter_dates():
        payload = client.get_heart_rates(_iso(day))
        results.append(_endpoint_result("heart-rates", {"date": _iso(day)}, payload))
    return results


def _fetch_body_composition(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_body_composition(_iso(request.start_date), _iso(request.end_date))
    return [
        _endpoint_result(
            "body-composition",
            {"start": _iso(request.start_date), "end": _iso(request.end_date)},
            payload,
        )
    ]


def _fetch_weigh_ins(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_weigh_ins(_iso(request.start_date), _iso(request.end_date))
    return [
        _endpoint_result(
            "weigh-ins",
            {"start": _iso(request.start_date), "end": _iso(request.end_date)},
            payload,
        )
    ]


def _fetch_daily_weigh_ins(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for day in request.iter_dates():
        payload = client.get_daily_weigh_ins(_iso(day))
        results.append(_endpoint_result("daily-weigh-ins", {"date": _iso(day)}, payload))
    return results


def _fetch_body_battery(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_body_battery(_iso(request.start_date), _iso(request.end_date))
    return [
        _endpoint_result(
            "body-battery",
            {"start": _iso(request.start_date), "end": _iso(request.end_date)},
            payload,
        )
    ]


def _fetch_body_battery_events(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for day in request.iter_dates():
        payload = client.get_body_battery_events(_iso(day))
        results.append(_endpoint_result("body-battery-events", {"date": _iso(day)}, payload))
    return results


def _fetch_blood_pressure(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_blood_pressure(_iso(request.start_date), _iso(request.end_date))
    return [
        _endpoint_result(
            "blood-pressure",
            {"start": _iso(request.start_date), "end": _iso(request.end_date)},
            payload,
        )
    ]


def _fetch_max_metrics(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_max_metrics(_iso(request.start_date))
    return [_endpoint_result("max-metrics", {"date": _iso(request.start_date)}, payload)]


def _fetch_hydration(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for day in request.iter_dates():
        payload = client.get_hydration_data(_iso(day))
        results.append(_endpoint_result("hydration", {"date": _iso(day)}, payload))
    return results


def _fetch_respiration(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for day in request.iter_dates():
        payload = client.get_respiration_data(_iso(day))
        results.append(_endpoint_result("respiration", {"date": _iso(day)}, payload))
    return results


def _fetch_spo2(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for day in request.iter_dates():
        payload = client.get_spo2_data(_iso(day))
        results.append(_endpoint_result("spo2", {"date": _iso(day)}, payload))
    return results


def _fetch_intensity_minutes(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for day in request.iter_dates():
        payload = client.get_intensity_minutes_data(_iso(day))
        results.append(_endpoint_result("intensity-minutes", {"date": _iso(day)}, payload))
    return results


def _fetch_all_day_stress(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for day in request.iter_dates():
        payload = client.get_all_day_stress(_iso(day))
        results.append(_endpoint_result("all-day-stress", {"date": _iso(day)}, payload))
    return results


def _fetch_all_day_events(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for day in request.iter_dates():
        payload = client.get_all_day_events(_iso(day))
        results.append(_endpoint_result("all-day-events", {"date": _iso(day)}, payload))
    return results


def _fetch_sleep(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for day in request.iter_dates():
        payload = client.get_sleep_data(_iso(day))
        results.append(_endpoint_result("sleep", {"date": _iso(day)}, payload))
    return results


def _fetch_stress(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for day in request.iter_dates():
        payload = client.get_stress_data(_iso(day))
        results.append(_endpoint_result("stress", {"date": _iso(day)}, payload))
    return results


def _fetch_resting_heart_rate(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for day in request.iter_dates():
        payload = client.get_rhr_day(_iso(day))
        results.append(_endpoint_result("resting-heart-rate", {"date": _iso(day)}, payload))
    return results


def _fetch_hrv(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for day in request.iter_dates():
        payload = client.get_hrv_data(_iso(day))
        results.append(_endpoint_result("hrv", {"date": _iso(day)}, payload))
    return results


def _fetch_training_readiness(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for day in request.iter_dates():
        payload = client.get_training_readiness(_iso(day))
        results.append(_endpoint_result("training-readiness", {"date": _iso(day)}, payload))
    return results


def _fetch_training_status(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for day in request.iter_dates():
        payload = client.get_training_status(_iso(day))
        results.append(_endpoint_result("training-status", {"date": _iso(day)}, payload))
    return results


def _fetch_endurance_score(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for day in request.iter_dates():
        payload = client.get_endurance_score(_iso(day))
        results.append(_endpoint_result("endurance-score-daily", {"date": _iso(day)}, payload))
    if request.start_date != request.end_date:
        payload = client.get_endurance_score(_iso(request.start_date), _iso(request.end_date))
        results.append(
            _endpoint_result(
                "endurance-score-stats",
                {"start": _iso(request.start_date), "end": _iso(request.end_date)},
                payload,
            )
        )
    return results


def _fetch_hill_score(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for day in request.iter_dates():
        payload = client.get_hill_score(_iso(day))
        results.append(_endpoint_result("hill-score-daily", {"date": _iso(day)}, payload))
    if request.start_date != request.end_date:
        payload = client.get_hill_score(_iso(request.start_date), _iso(request.end_date))
        results.append(
            _endpoint_result(
                "hill-score-stats",
                {"start": _iso(request.start_date), "end": _iso(request.end_date)},
                payload,
            )
        )
    return results


def _fetch_fitness_age(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for day in request.iter_dates():
        payload = client.get_fitnessage_data(_iso(day))
        results.append(_endpoint_result("fitness-age", {"date": _iso(day)}, payload))
    return results


def _fetch_race_predictions(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    payload_latest = client.get_race_predictions()
    results.append(_endpoint_result("race-predictions-latest", {}, payload_latest))
    if request.start_date != request.end_date:
        payload_daily = client.get_race_predictions(
            _iso(request.start_date),
            _iso(request.end_date),
            _type="daily",
        )
        results.append(
            _endpoint_result(
                "race-predictions-daily",
                {"start": _iso(request.start_date), "end": _iso(request.end_date)},
                payload_daily,
            )
        )
        payload_monthly = client.get_race_predictions(
            _iso(request.start_date),
            _iso(request.end_date),
            _type="monthly",
        )
        results.append(
            _endpoint_result(
                "race-predictions-monthly",
                {"start": _iso(request.start_date), "end": _iso(request.end_date)},
                payload_monthly,
            )
        )
    return results


def _fetch_progress_summary(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_progress_summary_between_dates(
        _iso(request.start_date),
        _iso(request.end_date),
    )
    return [
        _endpoint_result(
            "progress-summary",
            {"start": _iso(request.start_date), "end": _iso(request.end_date)},
            payload,
        )
    ]


def _fetch_goals(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_goals()
    return [_endpoint_result("goals", {}, payload)]


def _fetch_earned_badges(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_earned_badges()
    return [_endpoint_result("earned-badges", {}, payload)]


def _fetch_personal_records(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_personal_record()
    return [_endpoint_result("personal-records", {}, payload)]


def _fetch_adhoc_challenges(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_adhoc_challenges(0, 100)
    return [_endpoint_result("adhoc-challenges", {}, payload)]


def _fetch_badge_challenges(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_badge_challenges(0, 100)
    return [_endpoint_result("badge-challenges", {}, payload)]


def _fetch_available_badge_challenges(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_available_badge_challenges(0, 100)
    return [_endpoint_result("available-badge-challenges", {}, payload)]


def _fetch_non_completed_badge_challenges(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_non_completed_badge_challenges(0, 100)
    return [_endpoint_result("non-completed-badge-challenges", {}, payload)]


def _fetch_in_progress_virtual_challenges(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_inprogress_virtual_challenges()
    return [_endpoint_result("in-progress-virtual-challenges", {}, payload)]


def _fetch_menstrual_dayview(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for day in request.iter_dates():
        payload = client.get_menstrual_data_for_date(_iso(day))
        results.append(_endpoint_result("menstrual-dayview", {"date": _iso(day)}, payload))
    return results


def _fetch_menstrual_calendar(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_menstrual_calendar_data(_iso(request.start_date), _iso(request.end_date))
    return [
        _endpoint_result(
            "menstrual-calendar",
            {"start": _iso(request.start_date), "end": _iso(request.end_date)},
            payload,
        )
    ]


def _fetch_pregnancy_summary(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_pregnancy_summary()
    return [_endpoint_result("pregnancy-summary", {}, payload)]


def _fetch_activities(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = _load_activities_for_request(client, request)
    context.activities = payload
    return [_endpoint_result("activities", {}, payload)]


def _fetch_activities_by_date(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = _load_activities_for_request(client, request)
    if payload:
        context.activities = payload
    return [
        _endpoint_result(
            "activities-by-date",
            {"start": _iso(request.start_date), "end": _iso(request.end_date)},
            payload,
        )
    ]


def _fetch_activities_for_date(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for day in request.iter_dates():
        payload = client.get_activities_fordate(_iso(day))
        results.append(_endpoint_result("activities-for-date", {"date": _iso(day)}, payload))
    return results


def _fetch_last_activity(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_last_activity()
    return [_endpoint_result("last-activity", {}, payload)]


def _fetch_activity_types(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_activity_types()
    return [_endpoint_result("activity-types", {}, payload)]


def _require_activity_ids(context: GarminFetchContext) -> list[str]:
    ids: list[str] = []
    for activity in context.activities:
        activity_id = activity.get("activityId")
        if activity_id is None:
            activity_id = activity.get("activityIdGps")
        if activity_id is not None:
            ids.append(str(activity_id))
    return ids


def _load_activities_for_request(
    client: Garmin,
    request: GarminFetchRequest,
) -> list[dict[str, Any]]:
    start_iso = _iso(request.start_date)
    end_iso = _iso(request.end_date)
    payload: list[dict[str, Any]] | None = None
    if request.start_date == request.end_date:
        payload = client.get_activities_by_date(start_iso, end_iso)
        if not payload:
            payload = client.get_activities_fordate(start_iso)
    else:
        payload = client.get_activities_by_date(start_iso, end_iso)
    if not payload:
        return []
    return list(payload)


def _fetch_activity_detail(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for activity_id in _require_activity_ids(context):
        payload = client.get_activity(activity_id)
        results.append(_endpoint_result("activity-detail", {"activityId": activity_id}, payload))
    return results


def _fetch_activity_splits(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for activity_id in _require_activity_ids(context):
        payload = client.get_activity_splits(activity_id)
        results.append(_endpoint_result("activity-splits", {"activityId": activity_id}, payload))
    return results


def _fetch_activity_typed_splits(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for activity_id in _require_activity_ids(context):
        payload = client.get_activity_typed_splits(activity_id)
        results.append(
            _endpoint_result(
                "activity-typed-splits",
                {"activityId": activity_id},
                payload,
            )
        )
    return results


def _fetch_activity_split_summaries(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for activity_id in _require_activity_ids(context):
        payload = client.get_activity_split_summaries(activity_id)
        results.append(
            _endpoint_result("activity-split-summaries", {"activityId": activity_id}, payload)
        )
    return results


def _fetch_activity_weather(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for activity_id in _require_activity_ids(context):
        payload = client.get_activity_weather(activity_id)
        results.append(_endpoint_result("activity-weather", {"activityId": activity_id}, payload))
    return results


def _fetch_activity_hr_timezones(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for activity_id in _require_activity_ids(context):
        payload = client.get_activity_hr_in_timezones(activity_id)
        results.append(
            _endpoint_result("activity-hr-timezones", {"activityId": activity_id}, payload)
        )
    return results


def _fetch_activity_exercise_sets(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for activity_id in _require_activity_ids(context):
        payload = client.get_activity_exercise_sets(activity_id)
        results.append(
            _endpoint_result("activity-exercise-sets", {"activityId": activity_id}, payload)
        )
    return results


def _fetch_activity_gear(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for activity_id in _require_activity_ids(context):
        payload = client.get_activity_gear(activity_id)
        results.append(_endpoint_result("activity-gear", {"activityId": activity_id}, payload))
    return results


def _fetch_activity_download(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for activity_id in _require_activity_ids(context):
        fmt = Garmin.ActivityDownloadFormat.TCX
        payload = client.download_activity(activity_id, fmt)
        context.activity_downloads[activity_id] = payload
        results.append(
            _endpoint_result(
                "activity-download",
                {"activityId": activity_id, "format": fmt.name},
                payload,
            )
        )
    return results


def _resolve_user_profile_number(context: GarminFetchContext) -> str | None:
    profile = context.user_profile or {}
    for key in ("userProfileId", "userProfilePk", "profilePk"):
        if key in profile:
            return str(profile[key])
    user_data = profile.get("userData", {}) if isinstance(profile, dict) else {}
    for key in ("userProfileId", "userProfilePk"):
        if key in user_data:
            return str(user_data[key])
    return None


def _fetch_gear(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    user_profile_number = _resolve_user_profile_number(context)
    if user_profile_number is None:
        return []
    payload = client.get_gear(user_profile_number)
    context.gear = payload
    return [_endpoint_result("gear", {"userProfileNumber": user_profile_number}, payload)]


def _fetch_gear_stats(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for item in context.gear:
        gear_uuid = item.get("gearUuid") or item.get("gearUuidPk")
        if gear_uuid is None:
            continue
        payload = client.get_gear_stats(gear_uuid)
        context.gear_stats[str(gear_uuid)] = payload
        results.append(_endpoint_result("gear-stats", {"gearUuid": str(gear_uuid)}, payload))
    return results


def _fetch_gear_defaults(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    user_profile_number = _resolve_user_profile_number(context)
    if user_profile_number is None:
        return []
    payload = client.get_gear_defaults(user_profile_number)
    return [
        _endpoint_result("gear-defaults", {"userProfileNumber": user_profile_number}, payload)
    ]


def _fetch_gear_activities(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for item in context.gear:
        gear_uuid = item.get("gearUuid") or item.get("gearUuidPk")
        if gear_uuid is None:
            continue
        payload = client.get_gear_ativities(gear_uuid)
        results.append(
            _endpoint_result("gear-activities", {"gearUuid": str(gear_uuid)}, payload)
        )
    return results


def _fetch_devices(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_devices()
    context.devices = payload
    return [_endpoint_result("devices", {}, payload)]


def _fetch_device_settings(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for device in context.devices:
        device_id = device.get("deviceId")
        if device_id is None:
            continue
        payload = client.get_device_settings(device_id)
        context.device_settings[str(device_id)] = payload
        results.append(_endpoint_result("device-settings", {"deviceId": str(device_id)}, payload))
    return results


def _fetch_device_last_used(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_device_last_used()
    return [_endpoint_result("device-last-used", {}, payload)]


def _fetch_device_solar(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for device in context.devices:
        device_id = device.get("deviceId")
        if device_id is None:
            continue
        payload = client.get_device_solar_data(
            device_id,
            _iso(request.start_date),
            _iso(request.end_date),
        )
        results.append(
            _endpoint_result(
                "device-solar",
                {
                    "deviceId": str(device_id),
                    "start": _iso(request.start_date),
                    "end": _iso(request.end_date),
                },
                payload,
            )
        )
    return results


def _fetch_device_alarms(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_device_alarms()
    return [_endpoint_result("device-alarms", {}, payload)]


def _fetch_primary_training_device(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_primary_training_device()
    return [_endpoint_result("primary-training-device", {}, payload)]


def _fetch_workouts(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    payload = client.get_workouts()
    context.workouts = payload
    return [_endpoint_result("workouts", {}, payload)]


def _fetch_workout_detail(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for workout in context.workouts:
        workout_id = workout.get("workoutId")
        if workout_id is None:
            continue
        payload = client.get_workout_by_id(workout_id)
        results.append(_endpoint_result("workout-detail", {"workoutId": str(workout_id)}, payload))
    return results


def _fetch_workout_download(
    client: Garmin, request: GarminFetchRequest, context: GarminFetchContext
) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for workout in context.workouts:
        workout_id = workout.get("workoutId")
        if workout_id is None:
            continue
        payload = client.download_workout(workout_id)
        context.workout_downloads[str(workout_id)] = payload
        results.append(
            _endpoint_result(
                "workout-download",
                {"workoutId": str(workout_id)},
                payload,
            )
        )
    return results
