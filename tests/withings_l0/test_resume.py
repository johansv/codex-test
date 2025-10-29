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
    sample_measures,
)


def test_resume_starts_from_first_incomplete_day(tmp_path: Path) -> None:
    """Acceptance Criterion 7) resume starts at first non-done day using manifest progress."""

    first_transport = FakeTransport(responses=[sample_measures("2025-10-25T07:10:00+02:00")])
    fetcher = new_fetcher(first_transport)

    fetcher.fetch_date_range(
        out_root=tmp_path,
        start_date=date(2025, 10, 25),
        end_date=date(2025, 10, 25),
        skip_existing=False,
        dry_run=True,
        resume=False,
    )

    manifest = load_json(manifest_path(tmp_path, "test-run-123"))
    assert manifest["progress"]["2025-10-25"]["status"] == "done"

    def expect_resume(from_dt, to_dt):
        assert from_dt.date().isoformat() == "2025-10-26"
        return sample_measures("2025-10-26T07:10:00+02:00")

    second_transport = FakeTransport(responses=[expect_resume])
    fetcher = new_fetcher(second_transport)

    fetcher.fetch_date_range(
        out_root=tmp_path,
        start_date=date(2025, 10, 25),
        end_date=date(2025, 10, 26),
        skip_existing=False,
        dry_run=True,
        resume=True,
    )

    assert len(second_transport.calls) == 1

    new_day = day_folder(tmp_path, "2025-10-26")
    meta = load_json(next(new_day.glob("measures-*.meta.json")))
    assert_meta_common(meta, date="2025-10-26", status="success")
