from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from agentlab.core.garmin import EndpointError, EndpointResult, FetchOutcome
from agentlab.utils.storage import GarminStorageWriter


def test_storage_writes_json_payload(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path)
    outcome = FetchOutcome(
        results=[EndpointResult(endpoint="alpha", scope={}, payload={"value": 1})],
        errors=[],
    )

    writer.store(date(2024, 1, 1), outcome)

    path = tmp_path / "2024-01-01" / "alpha.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {"value": 1}


def test_storage_overwrites_existing_file(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path)
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


def test_storage_respects_format_scope_for_bytes(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path)
    payload = b"data"
    outcome = FetchOutcome(
        results=[
            EndpointResult(
                endpoint="activity-download",
                scope={"activityId": 123, "format": "TCX"},
                payload=payload,
            )
        ],
        errors=[],
    )

    writer.store(date(2024, 1, 1), outcome)

    path = tmp_path / "2024-01-01" / "activity-download_123.tcx"
    assert path.read_bytes() == payload


def test_storage_writes_error_files(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path)
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


def test_storage_removes_error_file_on_success(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path)
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


def test_storage_includes_activity_id_in_filenames(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path)
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

    writer.store(day, FetchOutcome(results=[result], errors=[]))

    data_path = tmp_path / "2024-01-01" / "activity-detail_456.json"
    assert json.loads(data_path.read_text(encoding="utf-8")) == {"detail": "value"}
    assert not error_path.exists()
