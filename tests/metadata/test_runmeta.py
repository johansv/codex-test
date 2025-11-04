from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

metadata = pytest.importorskip("agentlab.metadata")

DayStats = metadata.DayStats
RunError = metadata.RunError
RunMetaReader = metadata.RunMetaReader
RunMetaWriter = metadata.RunMetaWriter
RunParams = metadata.RunParams

from ._utils import load_json


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self._current = start

    def now(self) -> datetime:
        current = self._current
        self._current += timedelta(seconds=1)
        return current


def manifest_path(out_root: Path, run_id: str) -> Path:
    runs_dir = out_root / "runs"
    matches = sorted(runs_dir.glob(f"run_*_{run_id}.meta.json"))
    assert matches, f"No manifest found for run {run_id}"
    return matches[-1]


def new_writer(
    tmp_path: Path,
    run_id: str,
    clock: FakeClock | None = None,
    garmin_version: str | None = None,
) -> RunMetaWriter:
    return RunMetaWriter(
        out_root=tmp_path,
        timezone="Europe/Stockholm",
        run_id=run_id,
        clock=clock.now if clock else None,
        garminconnect_version=garmin_version,
        vendor_label="garmin",
    )


def sample_params(**overrides: object) -> RunParams:
    params = RunParams(
        start_date=date(2025, 10, 1),
        end_date=date(2025, 10, 3),
        preset="full",
        skip_existing=False,
        resume=False,
    )
    return replace(params, **overrides) if overrides else params


def sample_stats(success: int, error: int = 0, skipped: int = 0, bytes_payload: int = 0, duration_s: int = 0) -> DayStats:
    return DayStats(
        endpoints_ok=success,
        endpoints_fail=error,
        endpoints_skipped=skipped,
        bytes_payload=bytes_payload,
        duration_s=duration_s,
    )


def test_creates_manifest_with_headers(tmp_path: Path) -> None:
    """Manifest creation at start: file with headers, params, env, progress, totals."""
    run_id = "test-run-123"
    writer = new_writer(tmp_path, run_id)
    params = sample_params()

    writer.start_run(params, vendor="garmin", out_root=tmp_path)

    manifest = manifest_path(tmp_path, run_id)
    data = load_json(manifest)
    assert data["run_id"] == run_id
    assert data["schema_version"] == "runmeta/1.0"
    assert data.get("vendor") == "garmin"
    assert "started_at" in data
    name_parts = manifest.name.split("_")
    assert manifest.name.endswith(f"_{run_id}.meta.json")
    assert len(name_parts) >= 3
    timestamp_part = name_parts[1]
    assert len(timestamp_part) == len("202510271200")
    expected_date_prefix = data["started_at"][:10].replace("-", "")
    assert timestamp_part.startswith(expected_date_prefix)
    params_block = data["params"]
    assert params_block["start_date"] == params.start_date.isoformat()
    assert params_block["end_date"] == params.end_date.isoformat()
    assert params_block["preset"] == params.preset
    assert params_block["skip_existing"] == params.skip_existing
    assert params_block["resume"] == params.resume
    assert params_block["dry_run"] is False
    assert params_block["out_root"] == str(tmp_path)
    assert "garminconnect_version" in data["env"]
    totals = data["totals"]
    assert totals["days_scheduled"] == 3
    assert totals["days_done"] == 0
    assert totals["bytes_payload"] == 0
    assert totals["duration_s"] == 0
    assert totals["endpoints"] == {"success": 0, "skipped": 0, "error": 0, "written": 0}
    assert data["progress"] == {}
    assert data["aborted"] is None
    assert data["notes"] == []


def test_creates_manifest_with_supplied_garmin_version(tmp_path: Path) -> None:
    run_id = "run-version"
    writer = new_writer(tmp_path, run_id, garmin_version="1.2.3")
    writer.start_run(sample_params(), vendor="garmin", out_root=tmp_path)

    data = load_json(manifest_path(tmp_path, run_id))
    assert data["env"]["garminconnect_version"] == "1.2.3"


def test_creates_manifest_with_resolved_garmin_version(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(metadata, "pkg_version", lambda name: "9.9.9")

    run_id = "run-version-auto"
    writer = new_writer(tmp_path, run_id, garmin_version="unknown")
    writer.start_run(sample_params(), vendor="garmin", out_root=tmp_path)

    data = load_json(manifest_path(tmp_path, run_id))
    assert data["env"]["garminconnect_version"] == "9.9.9"


def test_start_run_uses_configured_timezone_offset(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Ensure configured ZoneInfo provides correct offset in stored timestamps."""
    tz = timezone(timedelta(hours=2))
    monkeypatch.setattr(metadata, "ZoneInfo", lambda name: tz)

    run_id = "run-timezone"
    fixed_now = datetime(2025, 10, 27, 15, 5, 2, 559616)
    writer = new_writer(tmp_path, run_id, clock=FakeClock(fixed_now))
    writer.start_run(sample_params(), vendor="garmin", out_root=tmp_path)

    data = load_json(manifest_path(tmp_path, run_id))
    assert data["started_at"].endswith("+02:00")


def test_falls_back_to_local_timezone_when_zoneinfo_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """If ZoneInfo data is missing, fall back to system local zone with correct offset."""

    def _raise_zoneinfo(name: str) -> None:
        raise metadata.ZoneInfoNotFoundError()

    monkeypatch.setattr(metadata, "ZoneInfo", _raise_zoneinfo)
    fallback_tz = timezone(timedelta(hours=1))
    monkeypatch.setattr(metadata, "_system_local_timezone", lambda: fallback_tz)

    run_id = "run-fallback"
    fixed_now = datetime(2025, 1, 3, 8, 0, 0, 0)
    writer = new_writer(tmp_path, run_id, clock=FakeClock(fixed_now))
    writer.start_run(sample_params(), vendor="garmin", out_root=tmp_path)

    data = load_json(manifest_path(tmp_path, run_id))
    assert data["started_at"].endswith("+01:00")


def test_updates_progress_and_totals_per_day(tmp_path: Path) -> None:
    """Per-day progress & totals: append entries, accumulate counts."""
    run_id = "run-456"
    writer = new_writer(tmp_path, run_id)
    writer.start_run(sample_params(), vendor="garmin", out_root=tmp_path)

    writer.start_day(date(2025, 10, 25))
    writer.end_day(date(2025, 10, 25), status="done", stats=sample_stats(success=4, error=1, skipped=2, bytes_payload=5000, duration_s=120))
    writer.start_day(date(2025, 10, 26))
    writer.end_day(date(2025, 10, 26), status="done", stats=sample_stats(success=3, error=0, skipped=1, bytes_payload=3000, duration_s=90))

    data = load_json(manifest_path(tmp_path, run_id))
    assert data["totals"]["days_scheduled"] == 3
    assert data["totals"]["days_done"] == 2
    assert data["totals"]["endpoints"] == {"written": 8, "success": 7, "error": 1, "skipped": 3}
    assert data["totals"]["bytes_payload"] == 8000
    assert data["totals"]["duration_s"] == 210
    assert data["progress"]["2025-10-25"]["status"] == "done"
    assert data["progress"]["2025-10-26"]["status"] == "done"
    day_25 = data["progress"]["2025-10-25"]
    assert day_25["endpoints_ok"] == 4
    assert day_25["endpoints_fail"] == 1
    assert day_25["endpoints_skipped"] == 2


def test_records_partial_day_and_abort(tmp_path: Path) -> None:
    """Partial day & abort: record partial status and immutable aborted block on failure."""
    run_id = "run-789"
    writer = new_writer(tmp_path, run_id)
    writer.start_run(sample_params(), vendor="garmin", out_root=tmp_path)

    writer.start_day(date(2025, 10, 25))
    writer.record_partial(
        date(2025, 10, 25),
        stats=sample_stats(success=1, error=1, skipped=0, bytes_payload=1200, duration_s=45),
        last_endpoint="activities",
    )
    writer.abort(RunError(code="E2E", msg="boom", last_endpoint="activities"))

    data = load_json(manifest_path(tmp_path, run_id))
    partial = data["progress"]["2025-10-25"]
    assert partial["status"] == "partial"
    assert partial["last_endpoint"] == "activities"
    assert data["aborted"]["code"] == "E2E"
    assert data["aborted"]["msg"] == "boom"


def test_finish_sets_ended_at_once(tmp_path: Path) -> None:
    """Finish timestamp immutability: ended_at set once and not modified later."""
    run_id = "run-immutable"
    clock = FakeClock(datetime(2025, 10, 1, 8, tzinfo=timezone.utc))
    writer = new_writer(tmp_path, run_id, clock=clock)
    writer.start_run(sample_params(), vendor="garmin", out_root=tmp_path)
    writer.finish()

    data_before = load_json(manifest_path(tmp_path, run_id))
    ended_at_first = data_before["ended_at"]

    writer.finish()  # second call should not change ended_at
    data_after = load_json(manifest_path(tmp_path, run_id))
    assert data_after["ended_at"] == ended_at_first


def test_atomic_idempotent_writes(tmp_path: Path) -> None:
    """Atomic, idempotent persistence: identical updates keep totals stable."""
    run_id = "run-atomic"
    writer = new_writer(tmp_path, run_id)
    writer.start_run(sample_params(), vendor="garmin", out_root=tmp_path)

    payload = sample_stats(success=2, error=1, skipped=0, bytes_payload=4000, duration_s=60)
    writer.start_day(date(2025, 10, 25))
    writer.end_day(date(2025, 10, 25), status="done", stats=payload)
    first_totals = load_json(manifest_path(tmp_path, run_id))["totals"].copy()

    writer.end_day(date(2025, 10, 25), status="done", stats=payload)  # repeat write
    second_totals = load_json(manifest_path(tmp_path, run_id))["totals"]

    assert second_totals == first_totals
