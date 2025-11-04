from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from agentlab.withings.fetcher import NetworkError
from tests.withings_l0._utils import FakeTransport, new_fetcher, sample_measures, sidecar_path

FORBIDDEN = ("token", "secret", "password", "client_id", "client_secret", "@")


def _load_meta(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_no_pii(meta: dict[str, object]) -> None:
    lowered = json.dumps(meta).lower()
    for needle in FORBIDDEN:
        assert needle not in lowered, f"PII token {needle!r} leaked into metadata"


def test_withings_meta_schema_success_and_error(tmp_path: Path) -> None:
    fetcher = new_fetcher(
        FakeTransport(responses=[sample_measures("2025-10-25T07:10:00+02:00")]),
        run_id="withings-run",
    )
    fetcher.fetch_date_range(
        out_root=tmp_path,
        start_date=date(2025, 10, 25),
        end_date=date(2025, 10, 25),
    )

    payload_path = next((tmp_path / "l0" / "withings" / "2025-10-25").glob("measures-*.json"))
    success_meta = _load_meta(sidecar_path(payload_path))
    assert success_meta["schema_version"] == "meta/1.0"
    assert success_meta["vendor"] == "withings"
    assert success_meta["endpoint"] == "measures"
    assert success_meta["day"] == "2025-10-25"
    scope = success_meta["scope"]
    assert scope["data_scope"] == "day"
    assert scope["day_context"] == "Europe/Stockholm"
    payload = success_meta["payload"]
    assert payload["file"].startswith("l0/withings/2025-10-25/measures-")
    assert payload["exists"] is True
    assert payload["size_bytes"] > 0
    assert payload["md5"]
    assert payload["type"] == "application/json"
    assert success_meta["items"] > 0
    request = success_meta["request"]
    assert request["method"] == "GET"
    assert request["endpoint_path"] == "withings.measure.getmeas"
    params = request["params"]
    assert params["action"] == "getmeas"
    assert params["category"] == 1
    assert isinstance(params["startdate"], int) and isinstance(params["enddate"], int)
    assert params["startdate"] <= params["enddate"]
    _assert_no_pii(success_meta)

    failing_fetcher = new_fetcher(FakeTransport(responses=[NetworkError("failure")]), run_id="withings-run-error")
    with pytest.raises(NetworkError):
        failing_fetcher.fetch_date_range(
            out_root=tmp_path,
            start_date=date(2025, 10, 26),
            end_date=date(2025, 10, 26),
        )

    error_payload = tmp_path / "l0" / "withings" / "2025-10-26" / "measures.error.json"
    error_meta = _load_meta(sidecar_path(error_payload))
    assert error_meta["status"] == "error"
    error_payload_block = error_meta["payload"]
    assert error_payload_block["file"].endswith("measures.error.json")
    assert error_payload_block["exists"] is False
    assert error_payload_block["size_bytes"] == 0
    assert error_payload_block["md5"] == ""
    assert error_meta["items"] == 0
    assert error_meta["error"]["message"]
    _assert_no_pii(error_meta)
