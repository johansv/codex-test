from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from tests.withings_l0._utils import (
    FakeTransport,
    assert_meta_common,
    day_folder,
    load_json,
    manifest_path,
    new_fetcher,
    sidecar_path,
    unix_measure_group,
)


def test_writes_empty_payload_when_no_measures(tmp_path: Path) -> None:
    transport = FakeTransport(responses=[[]])
    fetcher = new_fetcher(transport)

    fetcher.fetch_date_range(
        out_root=tmp_path,
        start_date=date(2025, 10, 25),
        end_date=date(2025, 10, 25),
        skip_existing=False,
        dry_run=True,
        resume=False,
    )

    day_dir = day_folder(tmp_path, "2025-10-25")
    json_path = next(day_dir.glob("measures-*.json"))
    assert json_path.name == "measures-20251025.json"
    payload = load_json(json_path)
    assert payload == []

    meta = load_json(sidecar_path(json_path))
    assert_meta_common(meta, date="2025-10-25", status="success")
    assert meta["items"] == 0
    assert meta["payload"]["exists"] is True
    assert meta["payload"]["size_bytes"] > 0

    manifest = load_json(manifest_path(tmp_path, "test-run-123"))
    entry = manifest["progress"]["2025-10-25"]
    assert entry["endpoints_ok"] == 1
    assert manifest["totals"]["endpoints"]["success"] == 1


def test_routes_unix_timestamp_measure_groups(tmp_path: Path) -> None:
    measurement_time = datetime(2025, 10, 25, 7, 15, tzinfo=timezone.utc)

    def payload(_from_dt: datetime, _to_dt: datetime) -> list[dict]:
        return [unix_measure_group(measurement_time)]

    transport = FakeTransport(responses=[payload])
    fetcher = new_fetcher(transport)

    fetcher.fetch_date_range(
        out_root=tmp_path,
        start_date=date(2025, 10, 25),
        end_date=date(2025, 10, 25),
        skip_existing=False,
        dry_run=True,
        resume=False,
    )

    day_dir = day_folder(tmp_path, "2025-10-25")
    json_path = next(day_dir.glob("measures-*.json"))
    assert json_path.name == "measures-20251025.json"
    payload = load_json(json_path)
    assert payload and payload[0]["date"] == int(measurement_time.timestamp())

    meta = load_json(sidecar_path(json_path))
    assert_meta_common(meta, date="2025-10-25", status="success")
