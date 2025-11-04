from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest

import agentlab.metadata as runmeta_module
from agentlab.cli import withings_fetch
from agentlab.withings.fetcher import WithingsFetcher
from tests.withings_l0._utils import FakeTransport, load_json, new_fetcher, sample_measures


def _write_manifest(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read_manifest(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_runmeta_creation_and_finish_withings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    AC: Withings MUST use the unified, vendor-neutral run manifest v1.0 and write it atomically at
        <OUT_ROOT>/runs/run_<YYYYMMDDHHMM>_<RUN_ID>.meta.json with fields:
        schema_version, run_id, started_at, timezone, vendor="withings", params{}, totals{}, progress{}, aborted|null.
    AC: totals include days_scheduled, days_done, endpoints{success,skipped,error,written}, bytes_payload, duration_s.
    AC: progress has a YYYY-MM-DD key for the day under test with status in {"done","skipped","partial","error"}.
    """
    replacements: List[tuple[Path, Path]] = []
    original_replace = runmeta_module.os.replace

    def spy_replace(src: str | bytes | Path, dst: str | bytes | Path) -> None:
        replacements.append((Path(src), Path(dst)))
        original_replace(src, dst)

    monkeypatch.setattr(runmeta_module.os, "replace", spy_replace)

    transport = FakeTransport(responses=[sample_measures("2025-10-25T07:10:00+02:00")])
    fetcher = new_fetcher(transport, run_id="test-run-ac")
    fetcher.fetch_date_range(
        out_root=tmp_path,
        start_date=date(2025, 10, 25),
        end_date=date(2025, 10, 25),
        skip_existing=False,
        dry_run=False,
        resume=False,
    )

    manifest_file = next((tmp_path / "runs").glob("run_*_test-run-ac.meta.json"))
    manifest = load_json(manifest_file)

    assert re.match(r"run_\d{12}_test-run-ac\.meta\.json", manifest_file.name)
    assert manifest.get("schema_version") == "runmeta/1.0"
    assert manifest.get("vendor") == "withings"
    assert manifest.get("run_id") == "test-run-ac"
    assert "started_at" in manifest and manifest.get("timezone") == "Europe/Stockholm"

    totals = manifest.get("totals", {})
    for field in ["days_scheduled", "days_done", "bytes_payload", "duration_s"]:
        assert field in totals
    assert {"success", "skipped", "error", "written"} <= totals.get("endpoints", {}).keys()

    progress_entries = manifest.get("progress", {})
    assert progress_entries, "Expected run manifest to record per-day progress"
    for day_key, entry in progress_entries.items():
        assert re.match(r"\d{4}-\d{2}-\d{2}", day_key)
        assert entry.get("status") in {"done", "skipped", "partial", "error"}, entry

    assert replacements, "Expected atomic writes via os.replace"
    run_replacements = [
        (src, dst) for src, dst in replacements if dst.parents and dst.parent.name == "runs"
    ]
    assert run_replacements, "Expected run manifest atomic replacement"
    for src, dst in run_replacements:
        assert src.name.startswith(".tmp-test-run-ac"), "Expected temp file prefix for atomic replace"
        assert dst.name.endswith("test-run-ac.meta.json")


def test_cli_prints_and_exit_success_withings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    AC: CLI MUST print exactly two lines once per run:
        "Run manifest: <abs-path>"
        "Run totals: {...}"
        and exit 0 on success.
    """
    manifest_path = tmp_path / "runs" / "run_202510301215_fake-run.meta.json"
    manifest_payload = {
        "schema_version": "runmeta/1.0",
        "run_id": "fake-run",
        "vendor": "withings",
        "started_at": "2025-10-30T12:15:00+01:00",
        "finished_at": "2025-10-30T12:16:00+01:00",
        "timezone": "Europe/Stockholm",
        "params": {},
        "totals": {"days_scheduled": 1, "days_done": 1, "endpoints": {"success": 1, "skipped": 0, "error": 0, "written": 1}, "bytes_payload": 123, "duration_s": 42},
        "progress": {"2025-10-29": {"status": "done"}},
        "aborted": None,
        "notes": [],
    }

    class FakeFetcher:
        def __init__(self, transport: object, **_: object) -> None:
            self.last_manifest_path: Path | None = None
            self.last_manifest: Dict[str, Any] | None = None
            self.last_run_id: str = "fake-run"

        def fetch_date_range(self, *, out_root: Path, **__: object) -> None:
            _write_manifest(out_root / manifest_path.relative_to(tmp_path), manifest_payload)
            self.last_manifest_path = out_root / manifest_path.relative_to(tmp_path)
            self.last_manifest = manifest_payload

    monkeypatch.setattr(withings_fetch, "WithingsFetcher", FakeFetcher)
    monkeypatch.setattr(withings_fetch, "_load_transport", lambda args: object())

    exit_code = withings_fetch.main(
        ["--start-date", "2025-10-29", "--end-date", "2025-10-29", "--out-root", str(tmp_path)]
    )

    captured = capsys.readouterr()
    stdout_lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(stdout_lines) == 2
    assert stdout_lines[0].startswith("Run manifest: ")
    assert stdout_lines[1].startswith("Run totals: ")
    assert exit_code == 0


def test_cli_prints_and_exit_abort_withings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    AC: On failure/abort the CLI MUST record 'aborted', print the same two lines once, and exit 1.
    """
    manifest_path = tmp_path / "runs" / "run_202510301300_fake-run.meta.json"
    manifest_payload = {
        "schema_version": "runmeta/1.0",
        "run_id": "fake-run",
        "vendor": "withings",
        "started_at": "2025-10-30T13:00:00+01:00",
        "timezone": "Europe/Stockholm",
        "params": {},
        "totals": {"days_scheduled": 2, "days_done": 1, "endpoints": {"success": 1, "skipped": 0, "error": 1, "written": 2}, "bytes_payload": 321, "duration_s": 99},
        "progress": {"2025-10-30": {"status": "error"}},
        "aborted": {"code": "HTTP_500", "message": "boom"},
        "notes": [],
    }

    class FakeFetcher:
        def __init__(self, transport: object, **_: object) -> None:
            self.last_manifest_path: Path | None = None
            self.last_manifest: Dict[str, Any] | None = None
            self.last_run_id: str = "fake-run"

        def fetch_date_range(self, *, out_root: Path, **__: object) -> None:
            _write_manifest(out_root / manifest_path.relative_to(tmp_path), manifest_payload)
            self.last_manifest_path = out_root / manifest_path.relative_to(tmp_path)
            self.last_manifest = manifest_payload

    monkeypatch.setattr(withings_fetch, "WithingsFetcher", FakeFetcher)
    monkeypatch.setattr(withings_fetch, "_load_transport", lambda args: object())

    exit_code = withings_fetch.main(
        ["--start-date", "2025-10-30", "--end-date", "2025-10-30", "--out-root", str(tmp_path)]
    )

    manifest = _read_manifest(manifest_path)
    assert manifest.get("aborted") is not None

    captured = capsys.readouterr()
    stdout_lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(stdout_lines) == 2
    assert stdout_lines[0].startswith("Run manifest: ")
    assert stdout_lines[1].startswith("Run totals: ")
    assert exit_code == 1, "Abort scenario should exit with status 1"


def test_resume_semantics_withings(tmp_path: Path) -> None:
    """
    AC: Resume MUST process ONLY days with status in {pending, partial, error}; NOT reprocess 'done' or 'skipped'.
    """
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    manifest_payload = {
        "schema_version": "runmeta/1.0",
        "run_id": "resume-run",
        "progress": {
            "2025-10-25": {"status": "done"},
            "2025-10-26": {"status": "skipped"},
            "2025-10-27": {"status": "partial"},
            "2025-10-28": {"status": "error"},
            "2025-10-29": {"status": "pending"},
        },
    }
    _write_manifest(runs_dir / "run_202510250900_resume-run.meta.json", manifest_payload)

    class RecordingTransport:
        def __init__(self) -> None:
            self.calls: List[str] = []

        def get_measures(self, from_dt: datetime, to_dt: datetime) -> list[dict[str, Any]]:
            self.calls.append(from_dt.date().isoformat())
            return []

    transport = RecordingTransport()
    fetcher = WithingsFetcher(
        transport=transport,
        run_id_provider=lambda: "resume-run",
    )
    fetcher.fetch_date_range(
        out_root=tmp_path,
        start_date=date(2025, 10, 25),
        end_date=date(2025, 10, 29),
        skip_existing=False,
        resume=True,
    )

    assert set(transport.calls) == {"2025-10-27", "2025-10-28", "2025-10-29"}


def test_privacy_manifest_withings(tmp_path: Path) -> None:
    """
    AC: Manifest MUST be PII-free (no emails, usernames, tokens, secrets).
    """
    transport = FakeTransport(responses=[sample_measures("2025-10-25T07:10:00+02:00")])
    fetcher = new_fetcher(transport, run_id="pii-run")
    fetcher.fetch_date_range(
        out_root=tmp_path,
        start_date=date(2025, 10, 25),
        end_date=date(2025, 10, 25),
        skip_existing=False,
        dry_run=False,
        resume=False,
    )

    manifest_file = next((tmp_path / "runs").glob("run_*_pii-run.meta.json"))
    manifest_text = manifest_file.read_text(encoding="utf-8").lower()
    forbidden = ["token", "secret", "@", "password", "client_id", "client_secret", "email"]
    assert all(pattern not in manifest_text for pattern in forbidden)


def test_time_semantics_strict_stockholm_calendar_day(tmp_path: Path) -> None:
    """
    AC: Withings MUST bucket by strict Europe/Stockholm calendar dates (NO 04:00 cutover).
    """
    fetcher = WithingsFetcher(
        transport=FakeTransport(responses=[]),
        timezone="Europe/Stockholm",
        day_cutover="00:00",
        run_id_provider=lambda: "time-run",
    )
    records = [
        {"timestamp": "2025-10-27T00:05:00+02:00"},
        {"timestamp": "2025-10-27T03:55:00+02:00"},
        {"timestamp": "2025-10-26T02:30:00+02:00"},
    ]
    buckets = fetcher._bucket_by_day(records)
    observed_days = {day.isoformat() for day in buckets.keys()}

    assert {"2025-10-27", "2025-10-26"} == observed_days, "Expected strict calendar bucketing without 04:00 cutover"
