from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone as dt_timezone, tzinfo as dt_tzinfo
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path
from typing import Callable, Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class RunParams:
    start_date: date
    end_date: date
    preset: str
    skip_existing: bool = False
    resume: bool = False
    dry_run: bool = False


@dataclass(frozen=True)
class DayStats:
    endpoints_ok: int
    endpoints_fail: int
    endpoints_skipped: int
    bytes_payload: int
    duration_s: int


@dataclass(frozen=True)
class RunError:
    code: str
    msg: str
    last_endpoint: Optional[str] = None
    at: Optional[datetime] = None


class RunMetaWriter:
    def __init__(
        self,
        out_root: Path,
        timezone: str,
        run_id: str,
        clock: Optional[Callable[[], datetime]] = None,
        garminconnect_version: Optional[str] = None,
        vendor_label: Optional[str] = None,
        vendor: Optional[str] = None,
    ) -> None:
        self._out_root = out_root
        self._timezone_name = timezone
        self._timezone = _resolve_timezone(timezone)
        self._run_id = run_id
        self._clock = clock or datetime.now
        self._path: Optional[Path] = None
        self._data: Optional[dict] = None
        self._started = False
        self._garmin_version = _resolve_garmin_version(garminconnect_version)
        self._vendor_label = vendor_label
        self._default_vendor = vendor or vendor_label

    def start_run(
        self,
        params: RunParams,
        *,
        vendor: Optional[str] = None,
        days_scheduled: Optional[int] = None,
        dry_run: Optional[bool] = None,
        out_root: Optional[Path] = None,
    ) -> None:
        if self._started:
            return
        self._started = True

        existing = self._locate_existing_path()
        if existing is not None:
            self._path = existing
            self._data = _load_json(existing)
            return

        now = self._clock()
        local_dt = _as_timezone(now, self._timezone)
        started_at = _isoformat(now, self._timezone)
        filename_stamp = local_dt.strftime("%Y%m%d%H%M")
        runs_dir = self._out_root / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        self._path = runs_dir / self._compose_filename(filename_stamp)

        scheduled_days = (
            days_scheduled
            if days_scheduled is not None
            else max(1, (params.end_date - params.start_date).days + 1)
        )
        dry_run_flag = bool(dry_run) if dry_run is not None else bool(getattr(params, "dry_run", False))

        self._data = {
            "schema_version": "runmeta/1.0",
            "run_id": self._run_id,
            "started_at": started_at,
            "params": {
                "start_date": params.start_date.isoformat(),
                "end_date": params.end_date.isoformat(),
                "preset": params.preset,
                "out_root": str(out_root or self._out_root),
                "skip_existing": params.skip_existing,
                "resume": params.resume,
                "dry_run": dry_run_flag,
            },
            "env": {
                "garminconnect_version": self._garmin_version or "unknown",
                "python_version": sys.version.split()[0],
                "timezone": self._timezone_name,
            },
            "progress": {},
            "totals": {
                "days_scheduled": scheduled_days,
                "days_done": 0,
                "endpoints": {"written": 0, "success": 0, "error": 0, "skipped": 0},
                "bytes_payload": 0,
                "duration_s": 0,
            },
            "aborted": None,
            "notes": [],
        }
        if vendor:
            self._data["vendor"] = vendor
        elif self._default_vendor:
            self._data["vendor"] = self._default_vendor
        self._data["timezone"] = self._timezone_name
        self._save()

    def start_day(self, day: date) -> None:
        if not self._data:
            raise RuntimeError("Run not started")
        progress = self._data.setdefault("progress", {})
        progress.setdefault(day.isoformat(), {})
        self._save()

    def end_day(
        self,
        day: date,
        status: Literal["done", "partial", "skipped"],
        stats: Optional[DayStats] = None,
        last_endpoint: Optional[str] = None,
    ) -> None:
        if not self._data:
            raise RuntimeError("Run not started")

        day_key = day.isoformat()
        entry = {
            "status": status,
            "endpoints_ok": stats.endpoints_ok if stats else 0,
            "endpoints_fail": stats.endpoints_fail if stats else 0,
            "endpoints_skipped": stats.endpoints_skipped if stats else 0,
            "bytes_payload": stats.bytes_payload if stats else 0,
            "duration_s": stats.duration_s if stats else 0,
        }
        if status == "partial" and last_endpoint:
            entry["last_endpoint"] = last_endpoint
        self._data["progress"][day_key] = entry
        self._recalculate_totals()
        self._save()

    def record_partial(
        self,
        day: date,
        stats: DayStats,
        last_endpoint: str,
    ) -> None:
        self.end_day(day, status="partial", stats=stats, last_endpoint=last_endpoint)

    def abort(self, err: RunError) -> None:
        if not self._data:
            raise RuntimeError("Run not started")
        if "aborted" in self._data and self._data["aborted"] is not None:
            return
        at = err.at or self._clock().astimezone(self._timezone)
        self._data["aborted"] = {
            "code": err.code,
            "msg": err.msg,
            "at": _isoformat(at, self._timezone),
        }
        if err.last_endpoint:
            self._data["aborted"]["last_endpoint"] = err.last_endpoint
        self._save()

    def finish(self) -> None:
        if not self._data:
            raise RuntimeError("Run not started")
        if "ended_at" in self._data:
            return
        ended_at = _isoformat(self._clock(), self._timezone)
        self._data["ended_at"] = ended_at
        self._save()

    def _recalculate_totals(self) -> None:
        existing_totals = self._data.get("totals", {}) if self._data else {}
        scheduled = existing_totals.get("days_scheduled", 0)
        totals = {
            "days_scheduled": scheduled,
            "days_done": 0,
            "endpoints": {"written": 0, "success": 0, "error": 0, "skipped": 0},
            "bytes_payload": 0,
            "duration_s": 0,
        }
        for entry in self._data["progress"].values():
            stats_ok = entry.get("endpoints_ok", 0)
            stats_fail = entry.get("endpoints_fail", 0)
            stats_skipped = entry.get("endpoints_skipped", 0)
            totals["endpoints"]["success"] += stats_ok
            totals["endpoints"]["error"] += stats_fail
            totals["endpoints"]["skipped"] += stats_skipped
            totals["bytes_payload"] += entry.get("bytes_payload", 0)
            totals["duration_s"] += entry.get("duration_s", 0)
            if entry.get("status") == "done":
                totals["days_done"] += 1
        totals["endpoints"]["written"] = totals["endpoints"]["success"] + totals["endpoints"]["error"]
        self._data["totals"] = totals

    def _locate_existing_path(self) -> Optional[Path]:
        runs_dir = self._out_root / "runs"
        if not runs_dir.exists():
            return None
        pattern = f"run_*_{self._run_id}.meta.json"
        matches = sorted(runs_dir.glob(pattern))
        if not matches and self._vendor_label:
            legacy_pattern = f"run_*_{self._vendor_label}_{self._run_id}.meta.json"
            matches = sorted(runs_dir.glob(legacy_pattern))
        if not matches:
            return None
        return matches[-1]

    def _save(self) -> None:
        if not self._data:
            return
        if self._path is None:
            raise RuntimeError("Run file path not initialised")
        serialized = json.dumps(self._data, indent=2, sort_keys=True)
        temp_path = self._path.parent / f".tmp-{self._run_id}-{os.getpid()}.meta.json"
        temp_path.write_text(serialized, encoding="utf-8")
        for attempt in range(5):
            try:
                os.replace(temp_path, self._path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05)

    def _compose_filename(self, local_stamp: str) -> str:
        parts = ["run", local_stamp, self._run_id]
        return "_".join(parts) + ".meta.json"


class RunMetaReader:
    def __init__(self, out_root: Path, run_id: str, local_stamp: str | None = None) -> None:
        runs_dir = out_root / "runs"
        if local_stamp is not None:
            candidate = runs_dir / f"run_{local_stamp}_{run_id}.meta.json"
            self._path = candidate
        else:
            matches = sorted(runs_dir.glob(f"run_*_{run_id}.meta.json"))
            if not matches:
                raise FileNotFoundError(runs_dir / f"run_*_{run_id}.meta.json")
            self._path = matches[-1]

    def load(self) -> dict:
        return _load_json(self._path)


def _isoformat(moment: datetime, tz: dt_tzinfo) -> str:
    aware = _as_timezone(moment, tz)
    return aware.isoformat()


def _system_local_timezone() -> Optional[dt_tzinfo]:
    aware = datetime.now(dt_timezone.utc).astimezone()
    return aware.tzinfo


def _resolve_timezone(name: str) -> dt_tzinfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        fallback = _system_local_timezone()
        return fallback or dt_timezone.utc


def _as_timezone(moment: datetime, tz: dt_tzinfo) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=tz)
    return moment.astimezone(tz)


def _resolve_garmin_version(provided: Optional[str]) -> str:
    if provided and provided.lower() != "unknown":
        return provided
    try:
        return pkg_version("garminconnect")
    except PackageNotFoundError:
        return "unknown"


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))
