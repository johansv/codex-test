from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from agentlab.core.garmin import EndpointError, EndpointResult, FetchOutcome
from agentlab.utils.storage import GarminStorageWriter

FORBIDDEN = ("token", "secret", "password", "client_id", "client_secret", "@")


def _read_meta(base: Path, day: str, filename: str) -> dict[str, object]:
    meta_path = base / "l0" / "garmin" / day / f"{filename}.meta.json"
    assert meta_path.exists()
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _assert_schema(
    meta: dict[str, object],
    *,
    day: str,
    endpoint: str,
    status: str,
    exists: bool,
    run_id: str | None,
) -> dict[str, object]:
    assert meta["schema_version"] == "meta/1.0"
    assert meta["vendor"] == "garmin"
    assert meta["endpoint"] == endpoint
    assert meta["day"] == day
    assert meta["status"] == status
    scope = meta["scope"]
    assert scope["data_scope"] == "day"
    assert scope["day_context"] == "local"
    assert scope["date_from"].startswith(day)
    assert scope["date_to"].startswith(day)
    payload = meta["payload"]
    expected_path_prefix = f"l0/garmin/{day}/"
    assert str(payload["file"]).startswith(expected_path_prefix)
    if exists:
        assert payload["size_bytes"] > 0
        assert payload["md5"]
    else:
        assert payload["size_bytes"] == 0
        assert payload["md5"] == ""
    assert payload["type"]
    assert payload["exists"] is exists
    run = meta["run"]
    if run_id is not None:
        assert run["id"] == run_id
    request = meta["request"]
    assert set(request.keys()) == {"method", "endpoint_path", "params"}
    assert isinstance(request["params"], dict)
    return payload


def _assert_no_pii(meta: dict[str, object]) -> None:
    def _check(value: object) -> None:
        if isinstance(value, dict):
            for item in value.values():
                _check(item)
        elif isinstance(value, list):
            for item in value:
                _check(item)
        elif isinstance(value, str):
            if value in {"***", "***REDACTED***", "[redacted]"}:
                return
            lowered = value.lower()
            for needle in FORBIDDEN:
                assert needle not in lowered, f"PII token {needle!r} leaked"
    _check(meta)


def test_storage_writes_json_payload(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path, run_id="test-run")
    outcome = FetchOutcome(
        results=[EndpointResult(endpoint="alpha", scope={}, payload={"value": 1})],
        errors=[],
    )

    writer.store(date(2024, 1, 1), outcome)

    payload_path = tmp_path / "l0" / "garmin" / "2024-01-01" / "alpha.json"
    assert json.loads(payload_path.read_text(encoding="utf-8")) == {"value": 1}
    meta = _read_meta(tmp_path, "2024-01-01", "alpha.json")
    payload = _assert_schema(meta, day="2024-01-01", endpoint="alpha", status="success", exists=True, run_id="test-run")
    assert payload["extension"] == ".json"
    assert payload["type"] == "application/json"
    assert payload["md5"] == hashlib.md5(payload_path.read_bytes()).hexdigest()
    assert meta["items"] == 1
    _assert_no_pii(meta)


def test_write_result_records_request_metadata(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path, run_id="test-run")
    metadata = {
        "api_calls": [
            {
                "name": "getDailySummary",
                "args": ["user@example.com"],
                "kwargs": {"token": "secret-token", "range": "daily"},
            }
        ]
    }
    writer.write_result(
        date(2024, 1, 2),
        EndpointResult(
            endpoint="beta",
            scope={"foo": "bar"},
            payload={"value": 2},
            metadata=metadata,
        ),
    )

    meta = _read_meta(tmp_path, "2024-01-02", "beta.json")
    _assert_schema(meta, day="2024-01-02", endpoint="beta", status="success", exists=True, run_id="test-run")
    request = meta["request"]
    assert request["method"] == "GET"
    assert request["endpoint_path"] == "garmin.getDailySummary"
    assert request["params"]["scope"] == {"foo": "bar"}
    assert request["params"]["kwargs"]["token"] == "***REDACTED***"
    assert request["params"]["args"][0] == "[redacted]"
    _assert_no_pii(meta)


def test_storage_overwrites_existing_file(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path, run_id="test-run")
    day = date(2024, 1, 3)
    writer.store(day, FetchOutcome(results=[EndpointResult(endpoint="alpha", scope={}, payload={"value": 1})], errors=[]))
    writer.store(day, FetchOutcome(results=[EndpointResult(endpoint="alpha", scope={}, payload={"value": 2})], errors=[]))

    payload_path = tmp_path / "l0" / "garmin" / "2024-01-03" / "alpha.json"
    meta = _read_meta(tmp_path, "2024-01-03", "alpha.json")
    payload = _assert_schema(meta, day="2024-01-03", endpoint="alpha", status="success", exists=True, run_id="test-run")
    assert json.loads(payload_path.read_text(encoding="utf-8")) == {"value": 2}
    assert payload["md5"] == hashlib.md5(payload_path.read_bytes()).hexdigest()


def test_storage_handles_binary_formats(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path, run_id="test-run")
    outcome = FetchOutcome(
        results=[
            EndpointResult(endpoint="activity-download", scope={"activityId": 123, "format": "TCX"}, payload=b"tcx"),
            EndpointResult(endpoint="activity-download", scope={"activityId": 123, "format": "ORIGINAL"}, payload=b"zip"),
        ],
        errors=[],
    )
    writer.store(date(2024, 1, 4), outcome)

    tcx_meta = _read_meta(tmp_path, "2024-01-04", "activity-download_123.tcx")
    tcx_payload = _assert_schema(tcx_meta, day="2024-01-04", endpoint="activity-download", status="success", exists=True, run_id="test-run")
    assert tcx_payload["extension"] == ".tcx"
    assert tcx_payload["type"] == "application/octet-stream"

    zip_meta = _read_meta(tmp_path, "2024-01-04", "activity-download_123.zip")
    zip_payload = _assert_schema(zip_meta, day="2024-01-04", endpoint="activity-download", status="success", exists=True, run_id="test-run")
    assert zip_payload["extension"] == ".zip"
    assert zip_payload["type"] == "application/octet-stream"


def test_storage_writes_workout_download_as_fit(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path, run_id="test-run")
    writer.write_result(
        date(2024, 1, 5),
        EndpointResult(endpoint="workout-download", scope={"workoutId": 42}, payload=b"fit-bytes"),
    )

    meta = _read_meta(tmp_path, "2024-01-05", "workout-download_42.fit")
    payload = _assert_schema(meta, day="2024-01-05", endpoint="workout-download", status="success", exists=True, run_id="test-run")
    assert payload["extension"] == ".fit"
    assert payload["type"] == "application/octet-stream"


def test_storage_writes_error_files(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path, run_id="test-run")
    error = EndpointError(endpoint="alpha", scope={}, message="boom", traceback="trace")

    writer.write_error(date(2024, 1, 6), error)

    error_json = tmp_path / "l0" / "garmin" / "2024-01-06" / "alpha.error.json"
    assert error_json.exists()
    meta = _read_meta(tmp_path, "2024-01-06", "alpha.error.json")
    _assert_schema(meta, day="2024-01-06", endpoint="alpha", status="error", exists=False, run_id="test-run")
    assert meta["error"] == {"code": "GARMIN_ERROR", "message": "boom"}


def test_storage_removes_error_file_on_success(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path, run_id="test-run")
    day = date(2024, 1, 7)
    writer.write_error(day, EndpointError(endpoint="alpha", scope={}, message="boom", traceback="trace"))
    writer.write_result(day, EndpointResult(endpoint="alpha", scope={}, payload={"value": 1}))

    error_path = tmp_path / "l0" / "garmin" / "2024-01-07" / "alpha.error.json"
    assert not error_path.exists()
    meta = _read_meta(tmp_path, "2024-01-07", "alpha.json")
    _assert_schema(meta, day="2024-01-07", endpoint="alpha", status="success", exists=True, run_id="test-run")


def test_storage_includes_identifiers_in_filenames(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path, run_id="test-run")
    writer.write_result(
        date(2024, 1, 8),
        EndpointResult(endpoint="details", scope={"activityId": 1, "gearUuid": "gear", "deviceId": 5}, payload={}),
    )

    day_dir = tmp_path / "l0" / "garmin" / "2024-01-08"
    files = {path.name for path in day_dir.iterdir() if path.suffix and not path.name.endswith(".meta.json")}
    assert files == {"details_1.json"}
    meta = _read_meta(tmp_path, "2024-01-08", "details_1.json")
    _assert_schema(meta, day="2024-01-08", endpoint="details", status="success", exists=True, run_id="test-run")


def test_store_applies_endpoint_day_overrides(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path, run_id="test-run")
    outcome = FetchOutcome(
        results=[
            EndpointResult(endpoint="alpha", scope={}, payload={}),
            EndpointResult(endpoint="beta", scope={}, payload={}),
        ],
        errors=[],
    )
    overrides = {"alpha": date(2024, 1, 10)}
    writer.store(date(2024, 1, 9), outcome, day_overrides=overrides)

    assert (tmp_path / "l0" / "garmin" / "2024-01-10" / "alpha.json").exists()
    assert (tmp_path / "l0" / "garmin" / "2024-01-09" / "beta.json").exists()


def test_store_uses_default_override_for_remaining_endpoints(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path, run_id="test-run")
    outcome = FetchOutcome(
        results=[EndpointResult(endpoint="alpha", scope={}, payload={})],
        errors=[EndpointError(endpoint="beta", scope={}, message="fail", traceback="trace")],
    )
    writer.store(date(2024, 1, 11), outcome, default_override=date(2024, 1, 12))

    assert (tmp_path / "l0" / "garmin" / "2024-01-12" / "alpha.json").exists()
    assert (tmp_path / "l0" / "garmin" / "2024-01-12" / "beta.error.json").exists()
