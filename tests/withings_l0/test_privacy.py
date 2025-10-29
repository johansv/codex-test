from __future__ import annotations

from datetime import date
from pathlib import Path

from tests.withings_l0._utils import (
    FakeTransport,
    assert_meta_common,
    assert_no_pii,
    day_folder,
    load_json,
    manifest_path,
    new_fetcher,
    sample_measures,
)


def test_no_pii_in_artifacts_and_logs(tmp_path: Path) -> None:
    """Acceptance Criterion 6) ensures artifacts stay free of PII tokens."""

    transport = FakeTransport(responses=[sample_measures("2025-10-25T07:10:00+02:00")])
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
    data_path = next(day_dir.glob("measures-*.json"))
    meta_path = next(day_dir.glob("measures-*.meta.json"))

    payload = load_json(data_path)
    meta = load_json(meta_path)

    assert_meta_common(meta, date="2025-10-25", status="success")

    assert_no_pii(payload)
    assert_no_pii(meta)
    assert_no_pii(load_json(manifest_path(tmp_path, "test-run-123")))
