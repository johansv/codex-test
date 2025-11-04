from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from agentlab.core.garmin import EndpointError, EndpointResult
from agentlab.utils.storage import GarminStorageWriter

FORBIDDEN = ("token", "secret", "password", "client_id", "client_secret", "@")


def _load_meta(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_no_pii(meta: dict[str, object]) -> None:
    lower = json.dumps(meta).lower()
    for needle in FORBIDDEN:
        assert needle not in lower, f"PII token {needle!r} leaked into metadata"


def test_garmin_meta_schema_success_and_error(tmp_path: Path) -> None:
    writer = GarminStorageWriter(tmp_path, run_id="garmin-run")

    result = EndpointResult(
        endpoint="activities-for-date",
        scope={"date": "2025-10-29"},
        payload={"foo": "bar"},
        metadata={
            "api_calls": [
                {
                    "name": "activities_for_date",
                    "args": [],
                    "kwargs": {"date": "2025-10-29"},
                }
            ],
            "data_scope": "day",
        },
    )
    writer.write_result(date(2025, 10, 29), result)

    success_meta_path = (
        tmp_path / "l0" / "garmin" / "2025-10-29" / "activities-for-date.json.meta.json"
    )
    success_meta = _load_meta(success_meta_path)
    assert success_meta["schema_version"] == "meta/1.0"
    assert success_meta["vendor"] == "garmin"
    assert success_meta["endpoint"] == "activities-for-date"
    assert success_meta["day"] == "2025-10-29"
    scope = success_meta["scope"]
    assert scope["data_scope"] == "day"
    assert scope["day_context"] == "local"
    payload = success_meta["payload"]
    assert payload["file"] == "l0/garmin/2025-10-29/activities-for-date.json"
    assert payload["exists"] is True
    assert payload["size_bytes"] > 0
    assert payload["md5"]
    assert payload["type"] == "application/json"
    assert success_meta["items"] >= 1
    request = success_meta["request"]
    assert request["method"] in {"GET", "LOCAL"}
    assert request["endpoint_path"].startswith("garmin.")
    _assert_no_pii(success_meta)

    error = EndpointError(
        endpoint="activities-for-date",
        scope={"date": "2025-10-29"},
        message="boom",
        traceback="traceback",
    )
    writer.write_error(date(2025, 10, 29), error)

    error_meta_path = (
        tmp_path
        / "l0"
        / "garmin"
        / "2025-10-29"
        / "activities-for-date.error.json.meta.json"
    )
    error_meta = _load_meta(error_meta_path)
    assert error_meta["status"] == "error"
    error_payload = error_meta["payload"]
    assert error_payload["file"] == "l0/garmin/2025-10-29/activities-for-date.error.json"
    assert error_payload["exists"] is False
    assert error_payload["size_bytes"] == 0
    assert error_payload["md5"] == ""
    assert error_meta["items"] == 0
    assert error_meta["error"] == {"code": "GARMIN_ERROR", "message": "boom"}
    _assert_no_pii(error_meta)
