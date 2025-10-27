"""CLI for computing personalized sleep need summaries from Garmin exports."""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import dataclass, field, asdict
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Optional

MIN_VALID_SLEEP_SECONDS = 2 * 3600  # ignore nights shorter than 2 hours
MAX_HISTORY_DAYS = 56  # keep ~8 weeks of history in saved state
ROLLING_WINDOWS = (7, 14, 28)
MIN_BASELINE_HISTORY = 21
BASELINE_SMOOTHING_ALPHA = 0.05
MAX_BASELINE_DELTA = 0.05
LONG_WINDOW_DAYS = 42
FOCUS_WINDOW_DAYS = 14


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Calculate nightly sleep needs from Garmin per-day exports, "
            "writing summaries under out/<date>/ai/."
        )
    )
    parser.add_argument(
        "--start",
        required=True,
        help="Inclusive start date (YYYY-MM-DD) of the processing window.",
    )
    parser.add_argument(
        "--end",
        required=True,
        help="Inclusive end date (YYYY-MM-DD) of the processing window.",
    )
    parser.add_argument(
        "--out-root",
        type=Path,
        default=Path("out"),
        help="Root directory containing per-date Garmin exports (default: ./out).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute summaries but do not write files.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-day summary details to stdout.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Emit detailed processing logs (implies --verbose).",
    )
    return parser.parse_args(argv)


def _parse_date(value: str) -> datetime.date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise SystemExit(f"Invalid date '{value}'; expected YYYY-MM-DD.") from exc


def _read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - user data issue
        raise SystemExit(f"Failed to parse JSON from {path}: {exc}") from exc


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        raw = float(value)
        if raw > 10**12:
            raw /= 1000.0
        return datetime.fromtimestamp(raw, tz=UTC)
    if isinstance(value, str) and value.isdigit():
        raw = float(value)
        if raw > 10**12:
            raw /= 1000.0
        return datetime.fromtimestamp(raw, tz=UTC)
    try:
        if isinstance(value, str) and value.endswith("Z"):
            return datetime.fromisoformat(value.removesuffix("Z")).replace(tzinfo=UTC)
        if isinstance(value, str):
            return datetime.fromisoformat(value)
    except ValueError:
        return None
    return None


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    parsed = _parse_timestamp(value)
    if parsed:
        return parsed
    return None


def _sum_stage_durations(entries: Iterable[dict[str, Any]], asleep_labels: set[str]) -> tuple[int, int]:
    asleep = 0
    awake = 0
    for entry in entries:
        label = str(entry.get("stage") or entry.get("level") or "").upper()
        duration = entry.get("duration") or entry.get("durationInSeconds")
        if not isinstance(duration, (int, float)):
            continue
        duration = int(duration)
        if label in asleep_labels:
            asleep += duration
        else:
            awake += duration
    return asleep, awake


@dataclass(slots=True)
class SleepMetrics:
    date: str
    start: datetime
    end: datetime
    sleep_seconds: int
    asleep_seconds: int
    awake_seconds: int

    @property
    def sleep_hours(self) -> float:
        return self.sleep_seconds / 3600.0

    @property
    def asleep_hours(self) -> float:
        return self.asleep_seconds / 3600.0

    @property
    def awake_hours(self) -> float:
        return self.awake_seconds / 3600.0

    @property
    def efficiency(self) -> float:
        if self.sleep_seconds == 0:
            return 0.0
        return self.asleep_seconds / self.sleep_seconds


def _load_sleep_metrics(date_str: str, date_dir: Path) -> Optional[SleepMetrics]:
    path = date_dir / "sleep.json"
    data = _read_json(path)
    if not data:
        return None

    sessions: list[dict[str, Any]] = []
    best_metrics: Optional[SleepMetrics] = None

    if isinstance(data, dict):
        if isinstance(data.get("sessions"), list):
            sessions = data["sessions"]
        elif isinstance(data.get("sleep"), list):
            sessions = data["sleep"]
        elif isinstance(data.get("sleepDTOs"), list):
            sessions = data["sleepDTOs"]
        elif isinstance(data.get("dailySleepDTO"), dict):
            dto = data["dailySleepDTO"]
            metrics = _metrics_from_daily_sleep(dto, date_str)
            if metrics:
                best_metrics = metrics
            # Some files also have detailed levels we can fall back to.
            entries = dto.get("sleepEntries") or dto.get("sleepLevelsV2")
            if isinstance(entries, list):
                sessions = entries
        elif isinstance(data.get("sleepList"), list):
            sessions = data["sleepList"]
    elif isinstance(data, list):
        sessions = data

    # Select the longest session as the primary overnight sleep.
    asleep_labels = {"DEEP", "LIGHT", "REM", "ASLEEP"}
    for entry in sessions:
        start = (
            _parse_iso_datetime(entry.get("start"))
            or _parse_iso_datetime(entry.get("startTimeLocal"))
            or _parse_iso_datetime(entry.get("startTime"))
            or _parse_iso_datetime(entry.get("sleepStartTimestampGMT"))
        )
        end = (
            _parse_iso_datetime(entry.get("end"))
            or _parse_iso_datetime(entry.get("endTimeLocal"))
            or _parse_iso_datetime(entry.get("endTime"))
            or _parse_iso_datetime(entry.get("sleepEndTimestampGMT"))
        )

        duration = entry.get("duration")
        if not isinstance(duration, (int, float)):
            duration = entry.get("durationInSeconds")
        if not isinstance(duration, (int, float)) and start and end:
            duration = (end - start).total_seconds()
        if not isinstance(duration, (int, float)):
            duration = 0
        sleep_seconds = max(0, int(duration))

        stages = []
        if isinstance(entry.get("stages"), list):
            stages = entry["stages"]
        elif isinstance(entry.get("levels"), list):
            stages = entry["levels"]
        elif isinstance(entry.get("sleepLevels"), dict):
            maybe_levels = entry["sleepLevels"].get("levels") or entry["sleepLevels"].get("shorter")
            if isinstance(maybe_levels, list):
                stages = maybe_levels

        asleep_seconds, awake_seconds = _sum_stage_durations(stages, asleep_labels)
        if asleep_seconds == 0 and sleep_seconds:
            # fallback: treat entire duration as asleep
            asleep_seconds = sleep_seconds
            awake_seconds = 0

        if sleep_seconds <= 0:
            sleep_seconds = asleep_seconds + awake_seconds

        if sleep_seconds < MIN_VALID_SLEEP_SECONDS:
            continue

        metrics = SleepMetrics(
            date=date_str,
            start=start or datetime.fromisoformat(f"{date_str}T00:00:00"),
            end=end or datetime.fromisoformat(f"{date_str}T00:00:00") + timedelta(seconds=sleep_seconds),
            sleep_seconds=sleep_seconds,
            asleep_seconds=asleep_seconds,
            awake_seconds=awake_seconds,
        )

        if not best_metrics or metrics.asleep_seconds > best_metrics.asleep_seconds:
            best_metrics = metrics

    return best_metrics


def _metrics_from_daily_sleep(dto: dict[str, Any], date_str: str) -> Optional[SleepMetrics]:
    sleep_seconds = dto.get("sleepTimeSeconds")
    if not isinstance(sleep_seconds, (int, float)) or sleep_seconds <= 0:
        return None

    start = (
        _parse_timestamp(dto.get("sleepStartTimestampGMT"))
        or _parse_timestamp(dto.get("sleepStartTimestampLocal"))
        or _parse_iso_datetime(dto.get("sleepStart"))
    )
    end = (
        _parse_timestamp(dto.get("sleepEndTimestampGMT"))
        or _parse_timestamp(dto.get("sleepEndTimestampLocal"))
        or _parse_iso_datetime(dto.get("sleepEnd"))
    )

    deep = dto.get("deepSleepSeconds") or 0
    light = dto.get("lightSleepSeconds") or 0
    rem = dto.get("remSleepSeconds") or 0
    awake = dto.get("awakeSleepSeconds") or dto.get("awakeSeconds") or 0

    asleep_seconds = int(sum(value for value in (deep, light, rem) if isinstance(value, (int, float))))
    awake_seconds = int(awake) if isinstance(awake, (int, float)) else 0

    if asleep_seconds == 0:
        asleep_seconds = int(sleep_seconds) - awake_seconds
    if asleep_seconds < 0:
        asleep_seconds = int(sleep_seconds)

    if sleep_seconds < MIN_VALID_SLEEP_SECONDS:
        return None

    if start is None:
        # Fallback to calendar date at midnight local time.
        start = datetime.fromisoformat(f"{date_str}T00:00:00")
    if end is None:
        end = start + timedelta(seconds=float(sleep_seconds))

    return SleepMetrics(
        date=date_str,
        start=start,
        end=end,
        sleep_seconds=int(sleep_seconds),
        asleep_seconds=int(asleep_seconds),
        awake_seconds=awake_seconds,
    )


def _first_numeric(values: Iterable[Any]) -> Optional[float]:
    for value in values:
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _load_resting_hr(date_dir: Path) -> Optional[float]:
    data = _read_json(date_dir / "resting-heart-rate.json")
    if not isinstance(data, dict):
        return None
    metrics_map = data.get("allMetrics", {}).get("metricsMap")
    if isinstance(metrics_map, dict):
        entries = metrics_map.get("WELLNESS_RESTING_HEART_RATE")
        if isinstance(entries, list):
            return _first_numeric(item.get("value") for item in entries if isinstance(item, dict))
    value = data.get("restingHeartRate")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _load_single_value(date_dir: Path, filename: str, keys: list[str]) -> Optional[float]:
    data = _read_json(date_dir / filename)
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    if isinstance(current, (int, float)):
        return float(current)
    if isinstance(current, list):
        return _first_numeric(current)
    return None


def _load_training_load(date_dir: Path) -> float:
    # Try progress-summary.json first
    data = _read_json(date_dir / "progress-summary.json")
    if isinstance(data, dict):
        summary = data.get("summary") or data.get("summaries")
        if isinstance(summary, dict):
            if isinstance(summary.get("trainingLoad"), (int, float)):
                return float(summary["trainingLoad"])
            intensity = summary.get("intensityMinutes")
            if isinstance(intensity, dict):
                moderate = intensity.get("totalIntensityMinutes") or (
                    intensity.get("moderateIntensityMinutes", 0) + 2 * intensity.get("vigorousIntensityMinutes", 0)
                )
                if isinstance(moderate, (int, float)):
                    return float(moderate)
        if isinstance(summary, list):
            for item in summary:
                if isinstance(item, dict) and isinstance(item.get("trainingLoad"), (int, float)):
                    return float(item["trainingLoad"])

    activities = _read_json(date_dir / "activities-by-date.json")
    if isinstance(activities, list):
        load = 0.0
        for item in activities:
            if not isinstance(item, dict):
                continue
            details = item.get("summary") or item
            if isinstance(details.get("trainingEffect"), (int, float)):
                load += float(details["trainingEffect"]) * 100.0
            elif isinstance(details.get("distance"), (int, float)):
                load += float(details["distance"])
        if load:
            return load
    status = _read_json(date_dir / "training-status.json")
    if isinstance(status, dict):
        latest = status.get("mostRecentTrainingStatus", {}).get("latestTrainingStatusData", {})
        if isinstance(latest, dict):
            for value in latest.values():
                if not isinstance(value, dict):
                    continue
                acute = value.get("acuteTrainingLoadDTO")
                if isinstance(acute, dict) and isinstance(acute.get("dailyTrainingLoadAcute"), (int, float)):
                    return float(acute["dailyTrainingLoadAcute"])

    stats = _read_json(date_dir / "stats.json")
    if isinstance(stats, dict):
        moderate = stats.get("moderateIntensityMinutes")
        vigorous = stats.get("vigorousIntensityMinutes")
        if isinstance(moderate, (int, float)) or isinstance(vigorous, (int, float)):
            moderate = float(moderate or 0.0)
            vigorous = float(vigorous or 0.0)
            return moderate + 2.0 * vigorous

    return 0.0


def _load_body_battery(date_dir: Path) -> Optional[float]:
    data = _read_json(date_dir / "body-battery.json")
    if isinstance(data, dict):
        for key in ("highestBodyBattery", "bodyBatteryCharged", "bodyBattery"):
            if isinstance(data.get(key), (int, float)):
                return float(data[key])
        entries = data.get("bodyBatteryValues")
        if isinstance(entries, list):
            return _first_numeric(entry.get("value") for entry in entries if isinstance(entry, dict))
    elif isinstance(data, list):
        values: list[float] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            for key in (
                "bodyBatteryMostRecentValue",
                "bodyBatteryHighestValue",
                "bodyBatteryAtWakeTime",
                "charged",
            ):
                if isinstance(item.get(key), (int, float)):
                    values.append(float(item[key]))
                    break
            array = item.get("bodyBatteryValuesArray")
            if isinstance(array, list):
                for row in array:
                    if isinstance(row, list) and len(row) >= 2 and isinstance(row[1], (int, float)):
                        values.append(float(row[1]))
        if values:
            return max(values)
    return None


def _load_hrv(date_dir: Path) -> Optional[float]:
    data = _read_json(date_dir / "hrv.json")
    if isinstance(data, dict):
        if isinstance(data.get("average"), (int, float)):
            return float(data["average"])
        summary = data.get("hrvSummary")
        if isinstance(summary, dict):
            for key in ("lastNightAvg", "weeklyAvg", "lowestBaseline"):
                if isinstance(summary.get(key), (int, float)):
                    return float(summary[key])
        entries = data.get("hrvValues") or data.get("values")
        if isinstance(entries, list):
            return _first_numeric(entry.get("value") for entry in entries if isinstance(entry, dict))
        readings = data.get("hrvReadings")
        if isinstance(readings, list):
            return _first_numeric(entry.get("hrvValue") for entry in readings if isinstance(entry, dict))
    return None


def _load_training_readiness(date_dir: Path) -> Optional[float]:
    value = _load_single_value(date_dir, "training-readiness.json", ["score"])
    if value is not None:
        return value
    status = _read_json(date_dir / "training-status.json")
    if isinstance(status, dict):
        latest = status.get("mostRecentTrainingStatus", {}).get("latestTrainingStatusData", {})
        if isinstance(latest, dict):
            for value_dict in latest.values():
                if not isinstance(value_dict, dict):
                    continue
                score = value_dict.get("trainingStatus")
                if isinstance(score, (int, float)):
                    return float(score)
    return None


def _load_daily_stress(date_dir: Path) -> Optional[float]:
    data = _read_json(date_dir / "stress.json")
    if isinstance(data, dict):
        if isinstance(data.get("averageStressLevel"), (int, float)):
            return float(data["averageStressLevel"])
        entries = data.get("stressValues")
        if isinstance(entries, list):
            return _first_numeric(entry.get("stressLevel") for entry in entries if isinstance(entry, dict))
    return None


def _load_hydration_shortfall(date_dir: Path) -> Optional[float]:
    data = _read_json(date_dir / "hydration.json")
    if isinstance(data, dict):
        goal = data.get("hydrationGoal")
        total = data.get("totalHydration")
        if isinstance(goal, (int, float)) and isinstance(total, (int, float)) and goal > 0:
            deficit = float(goal) - float(total)
            return max(0.0, deficit)
    return None


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


@dataclass(slots=True)
class NightRecord:
    date: str
    sleep_duration: float
    sleep_time: float
    awake_time: float
    sleep_efficiency: float
    training_load: float
    resting_hr: Optional[float]
    hrv: Optional[float]
    body_battery: Optional[float]
    readiness: Optional[float]
    recovery_score: float

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["high_recovery"] = self.recovery_score >= 0.6
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NightRecord":
        score = data.get("recovery_score")
        if score is None:
            score = 1.0 if data.get("high_recovery") else 0.0
        return cls(
            date=data["date"],
            sleep_duration=float(data["sleep_duration"]),
            sleep_time=float(data["sleep_time"]),
            awake_time=float(data["awake_time"]),
            sleep_efficiency=float(data["sleep_efficiency"]),
            training_load=float(data.get("training_load", 0.0)),
            resting_hr=data.get("resting_hr"),
            hrv=data.get("hrv"),
            body_battery=data.get("body_battery"),
            readiness=data.get("readiness"),
            recovery_score=float(score),
        )


@dataclass(slots=True)
class RollingState:
    history: list[NightRecord] = field(default_factory=list)
    sleep_debt: float = 0.0
    baseline_duration: Optional[float] = None
    baseline_time: Optional[float] = None

    def register_record(self, record: NightRecord) -> None:
        self.history.append(record)
        if len(self.history) > MAX_HISTORY_DAYS:
            self.history = self.history[-MAX_HISTORY_DAYS:]
        self._update_baselines(record)

    def current_baselines(self, fallback_duration: float, fallback_time: float) -> tuple[float, float]:
        if self.baseline_duration is None:
            self.baseline_duration = fallback_duration
        if self.baseline_time is None:
            self.baseline_time = fallback_time
        return self.baseline_duration, self.baseline_time

    def recent_values(self, key: str, days: int) -> list[float]:
        values = []
        for record in reversed(self.history):
            value = getattr(record, key, None)
            if value is not None:
                values.append(float(value))
            if len(values) >= days:
                break
        return list(reversed(values))

    def average(self, key: str, days: int) -> Optional[float]:
        values = self.recent_values(key, days)
        if not values:
            return None
        return mean(values)

    def update_sleep_debt(self, baseline_duration: float, actual_duration: float, recovery_score: float) -> None:
        diff = baseline_duration - actual_duration
        if diff > 0.05:
            self.sleep_debt += diff
        else:
            self.sleep_debt = max(0.0, self.sleep_debt + diff)

        score = _clamp(recovery_score, 0.0, 1.0)
        decay = 1.0 - 0.25 * score
        self.sleep_debt *= decay
        if self.sleep_debt < 0.05:
            self.sleep_debt = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "history": [record.to_dict() for record in self.history],
            "sleep_debt": self.sleep_debt,
            "baseline_duration": self.baseline_duration,
            "baseline_time": self.baseline_time,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RollingState":
        history_data = data.get("history", [])
        history = []
        for item in history_data:
            if isinstance(item, dict):
                history.append(NightRecord.from_dict(item))
        return cls(
            history=history,
            sleep_debt=float(data.get("sleep_debt", 0.0)),
            baseline_duration=data.get("baseline_duration"),
            baseline_time=data.get("baseline_time"),
        )

    def _update_baselines(self, record: NightRecord) -> None:
        if self.baseline_duration is None:
            self.baseline_duration = record.sleep_duration
        if self.baseline_time is None:
            self.baseline_time = record.sleep_time

        valid = [night for night in self.history if night.sleep_duration > 0]
        if len(valid) < MIN_BASELINE_HISTORY:
            return

        duration_target = self._weighted_average("sleep_duration")
        time_target = self._weighted_average("sleep_time")

        self.baseline_duration = self._apply_smoothing(self.baseline_duration, duration_target)
        self.baseline_time = self._apply_smoothing(self.baseline_time, time_target)

    def _weighted_average(self, attr: str) -> Optional[float]:
        long_samples = self.history[-LONG_WINDOW_DAYS:]
        focus_samples = self.history[-FOCUS_WINDOW_DAYS:]

        long_value = _weighted_mean(long_samples, attr, power=1.0)
        focus_value = _weighted_mean(focus_samples, attr, power=1.5)

        if long_value is None and focus_value is None:
            return None
        if long_value is None:
            return focus_value
        if focus_value is None:
            return long_value
        return 0.6 * long_value + 0.4 * focus_value

    def _apply_smoothing(self, current: float, target: Optional[float]) -> float:
        if target is None:
            return current
        blended = current * (1 - BASELINE_SMOOTHING_ALPHA) + target * BASELINE_SMOOTHING_ALPHA
        delta = _clamp(blended - current, -MAX_BASELINE_DELTA, MAX_BASELINE_DELTA)
        return max(0.0, current + delta)


def _weighted_mean(records: list[NightRecord], attr: str, *, power: float) -> Optional[float]:
    total_weight = 0.0
    weighted_sum = 0.0
    for record in records:
        value = getattr(record, attr, None)
        if value is None:
            continue
        weight = max(record.recovery_score, 0.05) ** power
        total_weight += weight
        weighted_sum += value * weight
    if total_weight == 0.0:
        return None
    return weighted_sum / total_weight


def _normalise(value: float, *, lower: float, upper: float) -> float:
    if upper == lower:
        return 0.5
    return _clamp((value - lower) / (upper - lower), 0.0, 1.0)


def _compute_recovery_score(state: RollingState, record: NightRecord) -> float:
    components: list[float] = []

    resting_avg = state.average("resting_hr", LONG_WINDOW_DAYS)
    if record.resting_hr is not None:
        if resting_avg is None:
            resting_avg = record.resting_hr
        diff = resting_avg - record.resting_hr
        components.append(_clamp(0.5 + diff / max(resting_avg, 1.0), 0.0, 1.0))

    hrv_avg = state.average("hrv", LONG_WINDOW_DAYS)
    if record.hrv is not None:
        if hrv_avg is None:
            hrv_avg = record.hrv
        ratio = (record.hrv - hrv_avg) / max(hrv_avg, 1.0)
        components.append(_clamp(0.5 + ratio * 0.6, 0.0, 1.0))

    if record.body_battery is not None:
        components.append(_normalise(record.body_battery, lower=20.0, upper=95.0))

    if record.readiness is not None:
        components.append(_normalise(record.readiness, lower=1.0, upper=10.0))

    components.append(_normalise(record.sleep_efficiency, lower=0.78, upper=0.97))

    if record.training_load > 0:
        avg_load = state.average("training_load", LONG_WINDOW_DAYS) or record.training_load
        ratio = (avg_load - record.training_load) / max(avg_load, 1.0)
        components.append(_clamp(0.5 + ratio * 0.4, 0.0, 1.0))

    if not components:
        return 0.5
    return _clamp(mean(components), 0.0, 1.0)


def _training_adjustment(state: RollingState, training_load: float) -> float:
    avg = state.average("training_load", 7)
    if avg is None or avg <= 0:
        return 0.0
    delta_ratio = (training_load - avg) / avg
    if delta_ratio > 0.5:
        return 0.75
    if delta_ratio > 0.25:
        return 0.5
    if delta_ratio > 0.1:
        return 0.25
    if delta_ratio < -0.4:
        return -0.35
    if delta_ratio < -0.2:
        return -0.2
    return 0.0


def _recovery_adjustment(state: RollingState, record: NightRecord) -> float:
    adjustment = 0.0
    resting_avg = state.average("resting_hr", 14)
    hrv_avg = state.average("hrv", 14)

    if record.resting_hr is not None and resting_avg is not None:
        diff = resting_avg - record.resting_hr
        adjustment += _clamp(diff / 5.0 * 0.25, -0.3, 0.3)

    if record.hrv is not None and hrv_avg is not None and hrv_avg > 0:
        diff = (record.hrv - hrv_avg) / hrv_avg
        adjustment += _clamp(diff * 0.5, -0.3, 0.4)

    return _clamp(adjustment, -0.5, 0.5)


def _stress_adjustment(stress: Optional[float], hydration_deficit: Optional[float]) -> float:
    adjustment = 0.0
    if stress is not None:
        if stress > 50:
            adjustment += 0.25
        elif stress > 30:
            adjustment += 0.1
    if hydration_deficit is not None and hydration_deficit > 250:
        adjustment += 0.15
    return _clamp(adjustment, 0.0, 0.5)


def _expected_awake(state: RollingState, fallback: float) -> float:
    avg = state.average("awake_time", 14)
    if avg is not None:
        return avg
    return fallback


def _generate_summary(
    date_str: str,
    metrics: Optional[SleepMetrics],
    state: RollingState,
    inputs: dict[str, Any],
) -> dict[str, Any]:
    if metrics is None:
        return {
            "date": date_str,
            "status": "skipped",
            "reason": "insufficient_sleep_data",
            "state": state.to_dict(),
            "inputs": inputs,
        }

    sleep_duration = metrics.asleep_hours
    sleep_time = metrics.sleep_hours
    awake_time = metrics.awake_hours

    training_load = float(inputs.get("training_load", 0.0))
    resting_hr = inputs.get("resting_hr")
    hrv = inputs.get("hrv")
    body_battery = inputs.get("body_battery")
    readiness = inputs.get("training_readiness")

    record = NightRecord(
        date=date_str,
        sleep_duration=sleep_duration,
        sleep_time=sleep_time,
        awake_time=awake_time,
        sleep_efficiency=metrics.efficiency,
        training_load=training_load,
        resting_hr=resting_hr,
        hrv=hrv,
        body_battery=body_battery,
        readiness=readiness,
        recovery_score=0.0,
    )

    record.recovery_score = _compute_recovery_score(state, record)

    baseline_duration, baseline_time = state.current_baselines(sleep_duration, sleep_time)

    adj_training = _training_adjustment(state, training_load)
    adj_recovery = _recovery_adjustment(state, record)
    adj_debt = min(0.5 * state.sleep_debt, 1.5)
    adj_stress = _stress_adjustment(inputs.get("stress"), inputs.get("hydration_deficit"))

    recommended_duration = baseline_duration + adj_training + adj_recovery + adj_debt + adj_stress
    recommended_duration = _clamp(recommended_duration, baseline_duration - 0.5, baseline_duration + 1.5)

    expected_awake = _expected_awake(state, awake_time)
    recommended_time_in_bed = recommended_duration + expected_awake

    state.update_sleep_debt(baseline_duration, sleep_duration, record.recovery_score)
    state.register_record(record)

    summary = {
        "date": date_str,
        "status": "ok",
        "sleep": {
            "start": metrics.start.isoformat() if metrics.start.tzinfo else metrics.start.isoformat() + "Z",
            "end": metrics.end.isoformat() if metrics.end.tzinfo else metrics.end.isoformat() + "Z",
            "sleep_time_hours": round(sleep_time, 3),
            "asleep_hours": round(sleep_duration, 3),
            "awake_hours": round(awake_time, 3),
            "efficiency": round(metrics.efficiency, 4),
        },
        "recommendation": {
            "baseline_sleep_duration": round(baseline_duration, 3),
            "baseline_time_in_bed": round(baseline_time, 3),
            "adjustments": {
                "training_load": round(adj_training, 3),
                "recovery": round(adj_recovery, 3),
                "sleep_debt": round(adj_debt, 3),
                "stress": round(adj_stress, 3),
            },
            "recommended_sleep_duration": round(recommended_duration, 3),
            "recommended_time_in_bed": round(recommended_time_in_bed, 3),
            "expected_awake": round(expected_awake, 3),
        },
        "recovery": {
            "score": round(record.recovery_score, 3),
        },
        "state": state.to_dict(),
        "inputs": inputs,
    }
    return summary


def _write_summary_with_meta(
    summary_path: Path,
    summary: dict[str, Any],
    run_id: str,
    dry_run: bool,
    debug: bool,
) -> None:
    summary_json = json.dumps(summary, indent=2, sort_keys=True)
    if dry_run:
        if debug:
            print(f"[sleep-needs][debug] dry run: would write {summary_path}", file=sys.stderr)
        return

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(summary_json + "\n", encoding="utf-8")
    if debug:
        print(f"[sleep-needs][debug] wrote {summary_path}", file=sys.stderr)

    payload = summary_path.read_bytes()
    checksum = sha256(payload).hexdigest()
    meta = {
        "timestamp": datetime.now(UTC).isoformat(),
        "size_bytes": len(payload),
        "checksum": {"sha256": checksum},
        "data_scope": "ai.sleep_summary",
        "correlation_id": run_id,
        "summary_path": summary_path.name,
    }
    meta_path = summary_path.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if debug:
        print(f"[sleep-needs][debug] wrote {meta_path}", file=sys.stderr)


def _load_previous_state(previous_summary_path: Path) -> RollingState:
    if not previous_summary_path.exists():
        return RollingState()
    data = _read_json(previous_summary_path)
    if not isinstance(data, dict):
        return RollingState()
    state_data = data.get("state")
    if isinstance(state_data, dict):
        return RollingState.from_dict(state_data)
    return RollingState()


def _collect_inputs(date_dir: Path) -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    inputs["resting_hr"] = _load_resting_hr(date_dir)
    inputs["hrv"] = _load_hrv(date_dir)
    inputs["body_battery"] = _load_body_battery(date_dir)
    inputs["training_load"] = _load_training_load(date_dir)
    inputs["training_readiness"] = _load_training_readiness(date_dir)
    inputs["stress"] = _load_daily_stress(date_dir)
    inputs["hydration_deficit"] = _load_hydration_shortfall(date_dir)

    stats = _read_json(date_dir / "stats.json")
    if isinstance(stats, dict):
        if inputs.get("body_battery") is None:
            for key in ("bodyBatteryAtWakeTime", "bodyBatteryMostRecentValue", "bodyBatteryHighestValue"):
                if isinstance(stats.get(key), (int, float)):
                    inputs["body_battery"] = float(stats[key])
                    break
        if inputs.get("resting_hr") is None and isinstance(stats.get("restingHeartRate"), (int, float)):
            inputs["resting_hr"] = float(stats["restingHeartRate"])
        if inputs.get("stress") is None and isinstance(stats.get("averageStressLevel"), (int, float)):
            inputs["stress"] = float(stats["averageStressLevel"])
        if inputs.get("training_load", 0.0) == 0.0:
            moderate = stats.get("moderateIntensityMinutes")
            vigorous = stats.get("vigorousIntensityMinutes")
            if isinstance(moderate, (int, float)) or isinstance(vigorous, (int, float)):
                moderate = float(moderate or 0.0)
                vigorous = float(vigorous or 0.0)
                inputs["training_load"] = moderate + 2.0 * vigorous

    return inputs


def _run(
    start: datetime.date,
    end: datetime.date,
    out_root: Path,
    dry_run: bool,
    verbose: bool,
    debug: bool,
) -> int:
    if start > end:  # pragma: no cover - defensive guard
        raise SystemExit("--start cannot be after --end.")

    if not out_root.exists():
        raise SystemExit(f"Output root {out_root} does not exist.")
    if not any(date_dir.is_dir() and _is_date_folder(date_dir.name) for date_dir in out_root.iterdir()):
        raise SystemExit(f"No date directories found under {out_root}.")

    run_id = uuid.uuid4().hex
    if debug:
        print(
            f"[sleep-needs][debug] run_id={run_id} window={start.isoformat()}..{end.isoformat()} "
            f"out_root={out_root}",
            file=sys.stderr,
        )
    processed_ok = 0
    processed_skipped = 0
    processed_missing = 0
    state = RollingState()
    current_date = start
    while current_date <= end:
        date_str = current_date.isoformat()
        date_dir = out_root / date_str
        ai_dir = date_dir / "ai"
        summary_path = ai_dir / "sleep_summary.json"

        # Load state from previous day if summary exists and this is the first iteration
        previous_date = current_date - timedelta(days=1)
        if not state.history:
            previous_summary_path = out_root / previous_date.isoformat() / "ai" / "sleep_summary.json"
            if previous_summary_path.exists():
                state = _load_previous_state(previous_summary_path)
                if debug:
                    print(
                        f"[sleep-needs][debug] hydrated state from {previous_summary_path} "
                        f"(history={len(state.history)}, debt={state.sleep_debt:.3f})",
                        file=sys.stderr,
                    )

        if not date_dir.exists():
            if verbose:
                print(f"[sleep-needs] {date_str}: directory missing, skipping.", file=sys.stderr)
            processed_missing += 1
            current_date += timedelta(days=1)
            continue

        metrics = _load_sleep_metrics(date_str, date_dir)
        inputs = _collect_inputs(date_dir)
        if debug:
            print(
                f"[sleep-needs][debug] processing {date_str} (history={len(state.history)}).",
                file=sys.stderr,
            )
        summary = _generate_summary(date_str, metrics, state, inputs)

        if verbose:
            status = summary["status"]
            if status == "ok":
                rec = summary["recommendation"]
                print(
                    f"[sleep-needs] {date_str}: need {rec['recommended_sleep_duration']}h "
                    f"(base {rec['baseline_sleep_duration']}h, adjust {rec['adjustments']})",
                    file=sys.stderr,
                )
            else:
                print(f"[sleep-needs] {date_str}: skipped ({summary.get('reason')})", file=sys.stderr)
        if summary["status"] == "ok":
            processed_ok += 1
        else:
            processed_skipped += 1
            if debug and summary.get("reason"):
                print(
                    f"[sleep-needs][debug] {date_str}: skipped reason={summary['reason']}",
                    file=sys.stderr,
                )

        _write_summary_with_meta(summary_path, summary, run_id, dry_run=dry_run, debug=debug)
        current_date += timedelta(days=1)

    if not dry_run:
        message = (
            f"sleep-needs: processed {processed_ok} nights, "
            f"skipped {processed_skipped}, missing directories {processed_missing}."
        )
        print(message)

    return 0


def _is_date_folder(name: str) -> bool:
    try:
        datetime.strptime(name, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    start = _parse_date(args.start)
    end = _parse_date(args.end)
    verbose = args.verbose or args.debug
    return _run(start, end, args.out_root, args.dry_run, verbose, args.debug)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
