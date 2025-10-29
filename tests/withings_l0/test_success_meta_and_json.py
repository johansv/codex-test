from __future__ import annotations

from datetime import date
from pathlib import Path

from tests.withings_l0._utils import (
    FakeTransport,
    assert_meta_common,
    day_folder,
    load_json,
    manifest_path,
    new_fetcher,
)


def test_writes_day_folder_and_meta_success(
    tmp_path: Path, success_transport: FakeTransport
) -> None:
    """Acceptance Criterion 1) ensures per-day JSON+meta with required keys and manifest entry."""

    fetcher = new_fetcher(success_transport)

    fetcher.fetch_date_range(
        out_root=tmp_path,
        start_date=date(2025, 10, 25),
        end_date=date(2025, 10, 25),
        skip_existing=False,
        dry_run=True,
        resume=False,
    )

    day_dir = day_folder(tmp_path, "2025-10-25")
    assert day_dir.exists()

    data_path = next(day_dir.glob("measures-*.json"))
    assert data_path.name == "measures-20251025.json"
    meta_path = day_dir / data_path.name.replace(".json", ".meta.json")

    payload = load_json(data_path)
    meta = load_json(meta_path)

    assert isinstance(payload, list)
    assert payload, "Expected measures payload to be preserved"

    assert_meta_common(meta, date="2025-10-25", status="success")

    manifest = load_json(manifest_path(tmp_path, "test-run-123"))
    assert manifest["totals"]["days_done"] >= 1
    assert manifest["totals"]["endpoints"]["success"] >= 1
    assert manifest["progress"]["2025-10-25"]["status"] == "done"

