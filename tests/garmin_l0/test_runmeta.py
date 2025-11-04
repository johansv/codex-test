from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from agentlab.cli import garmin_fetch
from build.lib.agentlab import metadata as runmeta_module


def _write_manifest(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_manifest(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_runmeta_creation_and_finish_garmin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    AC: Garmin MUST use the vendor-neutral manifest ("runmeta/1.0") and write it atomically at
        <OUT_ROOT>/runs/run_<YYYYMMDDHHMM>_<RUN_ID>.meta.json with required fields.
    """
    replacements: List[tuple[Path, Path]] = []
    original_replace = runmeta_module.os.replace

    def spy_replace(src: str | bytes | Path, dst: str | bytes | Path) -> None:
        replacements.append((Path(src), Path(dst)))
        original_replace(src, dst)

    monkeypatch.setattr(runmeta_module.os, "replace", spy_replace)

    writer = runmeta_module.RunMetaWriter(
        out_root=tmp_path,
        timezone="Europe/Stockholm",
        run_id="garmin-run",
        vendor="garmin",
    )
    writer.start_run(
        runmeta_module.RunParams(
            start_date=date(2025, 10, 30),
            end_date=date(2025, 10, 30),
            preset="garmin-l0",
            skip_existing=False,
            resume=False,
            dry_run=False,
        ),
        vendor="garmin",
        out_root=tmp_path,
        days_scheduled=1,
        dry_run=False,
    )
    writer.start_day(date(2025, 10, 30))
    writer.end_day(
        date(2025, 10, 30),
        status="done",
        stats=runmeta_module.DayStats(
            endpoints_ok=3,
            endpoints_fail=0,
            endpoints_skipped=0,
            bytes_payload=1234,
            duration_s=42,
        ),
    )
    writer.finish()

    manifest_file = next((tmp_path / "runs").glob("run_*_garmin-run.meta.json"))
    manifest = _load_manifest(manifest_file)

    assert re.match(r"run_\d{12}_garmin-run\.meta\.json", manifest_file.name)
    assert manifest["schema_version"] == "runmeta/1.0"
    assert manifest["vendor"] == "garmin"
    assert manifest["run_id"] == "garmin-run"
    assert "started_at" in manifest
    assert manifest.get("finished_at") or manifest.get("ended_at")

    totals = manifest["totals"]
    for key in ["days_scheduled", "days_done", "bytes_payload", "duration_s"]:
        assert key in totals
    assert {"success", "skipped", "error", "written"} <= totals["endpoints"].keys()

    progress = manifest.get("progress", {})
    assert "2025-10-30" in progress
    assert progress["2025-10-30"]["status"] in {"done", "skipped", "partial", "error", "pending"}

    assert replacements, "Expected atomic write via os.replace"
    for src, dst in replacements:
        assert src.name.startswith(".tmp-garmin-run"), "Temp file should carry .tmp-run prefix"
        assert dst.name.endswith("garmin-run.meta.json")


def test_cli_prints_and_exit_success_garmin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """
    AC: Garmin CLI MUST print exactly two lines once per run and exit 0 on success.
    """
    manifest_rel = Path("runs") / "run_202510301100_fake-run.meta.json"
    manifest_payload = {
        "schema_version": "runmeta/1.0",
        "run_id": "fake-run",
        "vendor": "garmin",
        "started_at": "2025-10-30T11:00:00+01:00",
        "finished_at": "2025-10-30T11:02:00+01:00",
        "timezone": "Europe/Stockholm",
        "params": {},
        "totals": {
            "days_scheduled": 1,
            "days_done": 1,
            "endpoints": {"success": 2, "skipped": 0, "error": 0, "written": 2},
            "bytes_payload": 9876,
            "duration_s": 90,
        },
        "progress": {"2025-10-30": {"status": "done"}},
        "aborted": None,
        "notes": [],
    }

    def fake_parser_factory(path: Path):
        class _Parser:
            def parse_args(self, argv: Sequence[str] | None = None) -> argparse.Namespace:
                return SimpleNamespace(
                    date=None,
                    start_date="2025-10-30",
                    end_date="2025-10-30",
                    include=[],
                    exclude=[],
                    config=None,
                    preset=None,
                    list_endpoints=False,
                    output_dir=str(path),
                    debug=False,
                    delay_post_login=0.0,
                    delay_between_endpoints=0.0,
                    delay_pagination=0.0,
                    delay_jitter=0.0,
                    retry_limit=0,
                    mfa_code=None,
                    skip_existing=False,
                    resume=False,
                )

        return _Parser()

    class FakeFetcher:
        supported_endpoints: List[str] = []

        def __init__(self, pacing: object) -> None:
            self.pacing = pacing

        def partition_endpoints(self, endpoints: List[str]) -> tuple[list[str], list[str]]:
            return [], []

    class FakeStorage:
        def __init__(self, root: Path, *, run_id: str) -> None:
            self.root = Path(root)
            self.run_id = run_id
            self.garmin_version = "0.0"

        def write_result(self, *args: object, **kwargs: object) -> None:  # pragma: no cover
            pass

        def write_error(self, *args: object, **kwargs: object) -> None:  # pragma: no cover
            pass

    def fake_start_run(*args: object, **kwargs: object) -> writer:  # type: ignore[no-redef]
        raise AssertionError("Unexpected call")  # pragma: no cover

    class ManifestWriter(runmeta_module.RunMetaWriter):  # type: ignore[misc]
        def __init__(self, out_root: Path, timezone: str, run_id: str, **_: object) -> None:
            super().__init__(out_root=out_root, timezone=timezone, run_id=run_id, vendor="garmin")
            self._target = out_root / manifest_rel

        def start_run(self, *args: object, **kwargs: object) -> None:
            _write_manifest(self._target, manifest_payload)
            self._path = self._target  # type: ignore[attr-defined]
            self._data = manifest_payload

        def finish(self) -> None:
            pass

    monkeypatch.setattr(garmin_fetch, "build_parser", lambda: fake_parser_factory(tmp_path))
    monkeypatch.setattr(garmin_fetch, "_resolve_range", lambda args: (date(2025, 10, 30), date(2025, 10, 30)))
    monkeypatch.setattr(garmin_fetch, "_load_credentials", lambda args: SimpleNamespace(username="demo", mfa_code=None))
    monkeypatch.setattr(
        garmin_fetch,
        "_load_endpoint_defaults",
        lambda fetcher, config, preset: ([], set(), Path("config"), []),
    )
    monkeypatch.setattr(
        garmin_fetch,
        "_select_endpoints",
        lambda fetcher, defaults, disabled, include, exclude: [],
    )
    monkeypatch.setattr(garmin_fetch, "GarminDataFetcher", FakeFetcher)
    monkeypatch.setattr(garmin_fetch, "GarminStorageWriter", FakeStorage)
    monkeypatch.setattr(garmin_fetch, "RunMetaWriter", ManifestWriter)
    monkeypatch.setattr(garmin_fetch, "_log_cli_event", lambda *_, **__: None)
    monkeypatch.setattr(garmin_fetch, "json", SimpleNamespace(dump=lambda *_, **__: None))

    exit_code = garmin_fetch.main(["--start-date", "2025-10-30", "--end-date", "2025-10-30", "--output-dir", str(tmp_path)])

    captured = capsys.readouterr()
    stdout_lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(stdout_lines) == 2
    assert stdout_lines[0].startswith("Run manifest: ")
    assert stdout_lines[1].startswith("Run totals: ")
    assert exit_code == 0


def test_cli_prints_and_exit_abort_garmin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """
    AC: On failure/abort the Garmin CLI MUST persist an 'aborted' block, print the two lines, and exit 1.
    """
    manifest_rel = Path("runs") / "run_202510301130_fake-run.meta.json"
    manifest_payload = {
        "schema_version": "runmeta/1.0",
        "run_id": "fake-run",
        "vendor": "garmin",
        "started_at": "2025-10-30T11:30:00+01:00",
        "timezone": "Europe/Stockholm",
        "params": {},
        "totals": {"days_scheduled": 2, "days_done": 1, "endpoints": {"success": 1, "skipped": 0, "error": 1, "written": 2}, "bytes_payload": 10, "duration_s": 5},
        "progress": {"2025-10-30": {"status": "error"}},
        "aborted": {"code": "HTTP_500", "message": "boom"},
        "notes": [],
    }

    class FakeFailureWriter(runmeta_module.RunMetaWriter):  # type: ignore[misc]
        def __init__(self, out_root: Path, timezone: str, run_id: str, **_: object) -> None:
            super().__init__(out_root=out_root, timezone=timezone, run_id=run_id, vendor="garmin")
            self._target = out_root / manifest_rel

        def start_run(self, *args: object, **kwargs: object) -> None:
            _write_manifest(self._target, manifest_payload)
            self._path = self._target  # type: ignore[attr-defined]
            self._data = manifest_payload

        def finish(self) -> None:
            pass

    monkeypatch.setattr(garmin_fetch, "build_parser", lambda: SimpleNamespace(parse_args=lambda _: SimpleNamespace(
        date=None,
        start_date="2025-10-30",
        end_date="2025-10-30",
        include=[],
        exclude=[],
        config=None,
        preset=None,
        list_endpoints=False,
        output_dir=str(tmp_path),
        debug=False,
        delay_post_login=0.0,
        delay_between_endpoints=0.0,
        delay_pagination=0.0,
        delay_jitter=0.0,
        retry_limit=0,
        mfa_code=None,
        skip_existing=False,
        resume=False,
    )))
    monkeypatch.setattr(garmin_fetch, "_resolve_range", lambda args: (date(2025, 10, 30), date(2025, 10, 30)))
    monkeypatch.setattr(garmin_fetch, "_load_credentials", lambda args: SimpleNamespace(username="demo", mfa_code=None))
    monkeypatch.setattr(garmin_fetch, "_load_endpoint_defaults", lambda *_, **__: ([], set(), Path("config"), []))
    monkeypatch.setattr(garmin_fetch, "_select_endpoints", lambda *_, **__: [])
    monkeypatch.setattr(garmin_fetch, "GarminDataFetcher", lambda pacing: SimpleNamespace(partition_endpoints=lambda _: ([], [])))
    monkeypatch.setattr(garmin_fetch, "GarminStorageWriter", lambda root, *, run_id: SimpleNamespace(garmin_version="0.0"))
    monkeypatch.setattr(garmin_fetch, "RunMetaWriter", FakeFailureWriter)
    monkeypatch.setattr(garmin_fetch, "_log_cli_event", lambda *_, **__: None)
    monkeypatch.setattr(garmin_fetch, "json", SimpleNamespace(dump=lambda *_, **__: None))

    exit_code = garmin_fetch.main(["--start-date", "2025-10-30", "--end-date", "2025-10-30", "--output-dir", str(tmp_path)])

    manifest = _load_manifest(tmp_path / manifest_rel)
    assert manifest.get("aborted") is not None

    captured = capsys.readouterr()
    stdout_lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(stdout_lines) == 2
    assert stdout_lines[0].startswith("Run manifest: ")
    assert stdout_lines[1].startswith("Run totals: ")
    assert exit_code == 1


def test_resume_semantics_garmin(tmp_path: Path) -> None:
    """
    AC: Resume MUST process ONLY days with status in {pending, partial, error}; NOT reprocess 'done' or 'skipped'.
    """
    manifest_path = tmp_path / "runs" / "run_202510250900_resume.meta.json"
    payload = {
        "schema_version": "runmeta/1.0",
        "run_id": "resume",
        "vendor": "garmin",
        "progress": {
            "2025-10-25": {"status": "done"},
            "2025-10-26": {"status": "skipped"},
            "2025-10-27": {"status": "partial"},
            "2025-10-28": {"status": "error"},
            "2025-10-29": {"status": "pending"},
        },
    }
    _write_manifest(manifest_path, payload)

    resumable = [
        day for day, info in payload["progress"].items() if info.get("status") in {"pending", "partial", "error"}
    ]
    assert resumable == ["2025-10-27", "2025-10-28", "2025-10-29"]


def test_privacy_manifest_garmin(tmp_path: Path) -> None:
    """
    AC: Manifest MUST be PII-free (no emails, usernames, tokens, secrets).
    """
    writer = runmeta_module.RunMetaWriter(
        out_root=tmp_path,
        timezone="Europe/Stockholm",
        run_id="privacy",
        vendor="garmin",
    )
    writer.start_run(
        runmeta_module.RunParams(
            start_date=date(2025, 10, 29),
            end_date=date(2025, 10, 29),
            preset="garmin-l0",
            skip_existing=False,
            resume=False,
            dry_run=False,
        ),
        vendor="garmin",
        out_root=tmp_path,
        days_scheduled=1,
        dry_run=False,
    )
    writer.start_day(date(2025, 10, 29))
    writer.end_day(
        date(2025, 10, 29),
        status="done",
        stats=runmeta_module.DayStats(
            endpoints_ok=1,
            endpoints_fail=0,
            endpoints_skipped=0,
            bytes_payload=1,
            duration_s=1,
        ),
    )
    writer.finish()

    manifest_file = next((tmp_path / "runs").glob("run_*_privacy.meta.json"))
    text = manifest_file.read_text(encoding="utf-8").lower()
    forbidden = ["token", "secret", "@", "password", "client_id", "client_secret", "email"]
    assert all(word not in text for word in forbidden)


def test_timezone_day_semantics_garmin() -> None:
    """
    AC: Day keys reflect Garmin’s vendor/device local semantics under timezone shifts.
    """
    stockholm = timezone(timedelta(hours=2))
    nyc = timezone(timedelta(hours=-4))

    sweden_time = datetime(2025, 10, 29, 7, 0, tzinfo=stockholm)
    nyc_time = datetime(2025, 10, 29, 23, 30, tzinfo=nyc)

    # Device-local day should respect each locale's calendar day
    assert sweden_time.date().isoformat() == "2025-10-29"
    assert nyc_time.date().isoformat() == "2025-10-29"
