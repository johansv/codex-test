from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from agentlab.core.garmin import EndpointError, EndpointResult, FetchOutcome
from agentlab.utils.storage import GarminStorageWriter


def _read_meta(base: Path, day: str, filename: str) -> dict[str, object]:
    meta_path = base / day / f"{filename}.meta.json"
    assert meta_path.exists()
    return json.loads(meta_path.read_text(encoding="utf-8"))


def test_storage_writes_json_payload(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path, run_id="test-run")
    outcome = FetchOutcome(
        results=[EndpointResult(endpoint="alpha", scope={}, payload={"value": 1})],
        errors=[],
    )

    writer.store(date(2024, 1, 1), outcome)

    path = tmp_path / "2024-01-01" / "alpha.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {"value": 1}
    meta = _read_meta(tmp_path, "2024-01-01", "alpha.json")
    assert meta["endpoint"] == "alpha"
    assert meta["scope"] == {}
    assert meta["garmin_methods"] == []
    assert meta["run"]["id"] == "test-run"
    assert meta["status"] == "success"
    assert meta["payload"]["exists"] is True
    assert meta["payload"]["md5"] == hashlib.md5(path.read_bytes()).hexdigest()


def test_storage_overwrites_existing_file(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path, run_id="test-run")
    day = date(2024, 1, 1)

    writer.store(
        day,
        FetchOutcome(
            results=[EndpointResult(endpoint="alpha", scope={}, payload={"value": 1})],
            errors=[],
        ),
    )
    writer.store(
        day,
        FetchOutcome(
            results=[EndpointResult(endpoint="alpha", scope={}, payload={"value": 2})],
            errors=[],
        ),
    )

    path = tmp_path / "2024-01-01" / "alpha.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {"value": 2}
    meta = _read_meta(tmp_path, "2024-01-01", "alpha.json")
    assert meta["run"]["id"] == "test-run"
    assert meta["garmin_methods"] == []
    assert meta["payload"]["type"] == "json"
    assert meta["status"] == "success"
    assert meta["payload"]["exists"] is True
    assert meta["payload"]["md5"] == hashlib.md5(path.read_bytes()).hexdigest()


def test_storage_respects_format_scope_for_bytes(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path, run_id="test-run")
    tcx_payload = b"tcx"
    zip_payload = b"zip-data"
    outcome = FetchOutcome(
        results=[
            EndpointResult(
                endpoint="activity-download",
                scope={"activityId": 123, "format": "TCX"},
                payload=tcx_payload,
            ),
            EndpointResult(
                endpoint="activity-download",
                scope={"activityId": 123, "format": "ORIGINAL"},
                payload=zip_payload,
            ),
        ],
        errors=[],
    )

    writer.store(date(2024, 1, 1), outcome)

    tcx_path = tmp_path / "2024-01-01" / "activity-download_123.tcx"
    zip_path = tmp_path / "2024-01-01" / "activity-download_123.zip"
    assert tcx_path.read_bytes() == tcx_payload
    assert zip_path.read_bytes() == zip_payload
    tcx_meta = _read_meta(tmp_path, "2024-01-01", "activity-download_123.tcx")
    assert tcx_meta["payload"]["extension"] == "tcx"
    assert tcx_meta["payload"]["type"] == "bytes"
    assert tcx_meta["run"]["id"] == "test-run"
    assert tcx_meta["status"] == "success"
    assert tcx_meta["payload"]["exists"] is True
    assert tcx_meta["payload"]["md5"] == hashlib.md5(tcx_path.read_bytes()).hexdigest()
    zip_meta = _read_meta(tmp_path, "2024-01-01", "activity-download_123.zip")
    assert zip_meta["payload"]["extension"] == "zip"
    assert zip_meta["payload"]["type"] == "bytes"
    assert zip_meta["status"] == "success"
    assert zip_meta["payload"]["exists"] is True
    assert zip_meta["payload"]["md5"] == hashlib.md5(zip_path.read_bytes()).hexdigest()


def test_storage_writes_workout_download_as_fit(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path, run_id="test-run")
    payload = b"fit-bytes"
    outcome = FetchOutcome(
        results=[
            EndpointResult(
                endpoint="workout-download",
                scope={"workoutId": 42},
                payload=payload,
            )
        ],
        errors=[],
    )

    writer.store(date(2024, 1, 1), outcome)

    fit_path = tmp_path / "2024-01-01" / "workout-download_42.fit"
    assert fit_path.read_bytes() == payload
    meta = _read_meta(tmp_path, "2024-01-01", "workout-download_42.fit")
    assert meta["payload"]["extension"] == "fit"
    assert meta["payload"]["type"] == "bytes"
    assert meta["status"] == "success"
    assert meta["payload"]["exists"] is True
    assert meta["payload"]["md5"] == hashlib.md5(fit_path.read_bytes()).hexdigest()


def test_storage_writes_error_files(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path, run_id="test-run")
    outcome = FetchOutcome(
        results=[],
        errors=[
            EndpointError(
                endpoint="alpha",
                scope={"date": "2024-01-01"},
                message="boom",
                traceback="traceback",
            )
        ],
    )

    writer.store(date(2024, 1, 1), outcome)

    path = tmp_path / "2024-01-01" / "alpha.error.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["endpoint"] == "alpha"
    assert "boom" in payload["message"]
    assert "traceback" in payload["traceback"]

    meta = _read_meta(tmp_path, "2024-01-01", "alpha.json")
    assert meta["payload"]["file"] == "alpha.json"
    assert meta["status"] == "error"
    assert meta["payload"]["exists"] is False
    assert meta["payload"]["md5"] is None
    assert meta["error"]["file"] == "alpha.error.json"


def test_storage_removes_error_file_on_success(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path, run_id="test-run")
    day = date(2024, 1, 1)

    writer.store(
        day,
        FetchOutcome(
            results=[],
            errors=[
                EndpointError(
                    endpoint="alpha",
                    scope={},
                    message="boom",
                    traceback="trace",
                )
            ],
        ),
    )

    error_path = tmp_path / "2024-01-01" / "alpha.error.json"
    assert error_path.exists()
    meta_error = _read_meta(tmp_path, "2024-01-01", "alpha.json")
    assert meta_error["payload"]["file"] == "alpha.json"
    assert meta_error["status"] == "error"
    assert meta_error["payload"]["exists"] is False

    writer.store(
        day,
        FetchOutcome(
            results=[
                EndpointResult(
                    endpoint="alpha",
                    scope={},
                    payload={"value": 1},
                )
            ],
            errors=[],
        ),
    )

    assert not error_path.exists()
    meta = _read_meta(tmp_path, "2024-01-01", "alpha.json")
    assert meta["status"] == "success"
    assert meta["payload"]["file"] == "alpha.json"
    assert meta["payload"]["exists"] is True


def test_storage_includes_activity_id_in_filenames(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path, run_id="test-run")
    day = date(2024, 1, 1)
    result = EndpointResult(
        endpoint="activity-detail",
        scope={"activityId": 456},
        payload={"detail": "value"},
    )
    error = EndpointError(
        endpoint="activity-detail",
        scope={"activityId": 456},
        message="failed",
        traceback="traceback",
    )

    writer.store(day, FetchOutcome(results=[], errors=[error]))
    error_path = tmp_path / "2024-01-01" / "activity-detail_456.error.json"
    assert error_path.exists()
    meta_error = _read_meta(tmp_path, "2024-01-01", "activity-detail_456.json")
    assert meta_error["payload"]["file"] == "activity-detail_456.json"
    assert meta_error["status"] == "error"
    assert meta_error["payload"]["exists"] is False

    writer.store(day, FetchOutcome(results=[result], errors=[]))

    data_path = tmp_path / "2024-01-01" / "activity-detail_456.json"
    assert json.loads(data_path.read_text(encoding="utf-8")) == {"detail": "value"}
    assert not error_path.exists()
    meta = _read_meta(tmp_path, "2024-01-01", "activity-detail_456.json")
    assert meta["scope"]["activityId"] == 456
    assert meta["status"] == "success"
    assert meta["payload"]["exists"] is True
    assert meta["payload"]["md5"] == hashlib.md5(data_path.read_bytes()).hexdigest()


def test_storage_includes_gear_uuid_in_filenames(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path, run_id="test-run")
    day = date(2024, 1, 1)
    result = EndpointResult(
        endpoint="gear-stats",
        scope={"gearUuid": "gear-1"},
        payload={"distance": 123},
    )

    writer.store(day, FetchOutcome(results=[result], errors=[]))

    data_path = tmp_path / "2024-01-01" / "gear-stats_gear-1.json"
    assert json.loads(data_path.read_text(encoding="utf-8")) == {"distance": 123}
    meta = _read_meta(tmp_path, "2024-01-01", "gear-stats_gear-1.json")
    assert meta["scope"]["gearUuid"] == "gear-1"
    assert meta["payload"]["md5"] == hashlib.md5(data_path.read_bytes()).hexdigest()


def test_storage_clears_legacy_gear_error_on_success(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path, run_id="test-run")
    day = date(2024, 1, 1)

    writer.store(
        day,
        FetchOutcome(
            results=[],
            errors=[
                EndpointError(
                    endpoint="gear-activities",
                    scope={},
                    message="boom",
                    traceback="traceback",
                )
            ],
        ),
    )

    legacy_error = tmp_path / "2024-01-01" / "gear-activities.error.json"
    assert legacy_error.exists()
    meta_error = _read_meta(tmp_path, "2024-01-01", "gear-activities.json")
    assert meta_error["payload"]["file"] == "gear-activities.json"
    assert meta_error["status"] == "error"
    assert meta_error["payload"]["exists"] is False

    writer.store(
        day,
        FetchOutcome(
            results=[
                EndpointResult(
                    endpoint="gear-activities",
                    scope={"gearUuid": "gear-1"},
                    payload=[{"gearUuid": "gear-1"}],
                )
            ],
            errors=[],
        ),
    )

    assert not legacy_error.exists()
    meta = _read_meta(tmp_path, "2024-01-01", "gear-activities_gear-1.json")
    assert meta["status"] == "success"


def test_storage_includes_device_id_in_filenames(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path, run_id="test-run")
    day = date(2024, 1, 1)
    result = EndpointResult(
        endpoint="device-settings",
        scope={"deviceId": "abc"},
        payload={"setting": 1},
    )

    writer.store(day, FetchOutcome(results=[result], errors=[]))

    data_path = tmp_path / "2024-01-01" / "device-settings_abc.json"
    assert json.loads(data_path.read_text(encoding="utf-8")) == {"setting": 1}
    meta = _read_meta(tmp_path, "2024-01-01", "device-settings_abc.json")
    assert meta["scope"]["deviceId"] == "abc"
