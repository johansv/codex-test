from __future__ import annotations

from datetime import date
from pathlib import Path

from tests.withings_l0._utils import (
    FakeTransport,
    assert_meta_common,
    day_folder,
    load_json,
    new_fetcher,
    sample_measures,
)


def test_cutover_0400_routes_measurements_correctly(tmp_path: Path) -> None:
    """Acceptance Criterion 2) routes <04:00 local to previous day and ≥04:00 to same day."""

    transport = FakeTransport(
        responses=[
            sample_measures(
                "2025-10-25T02:30:00+02:00",
                "2025-10-25T07:10:00+02:00",
            )
        ]
    )
    fetcher = new_fetcher(transport)

    fetcher.fetch_date_range(
        out_root=tmp_path,
        start_date=date(2025, 10, 25),
        end_date=date(2025, 10, 26),
        skip_existing=False,
        dry_run=True,
        resume=False,
    )

    early_day = day_folder(tmp_path, "2025-10-24")
    late_day = day_folder(tmp_path, "2025-10-25")

    assert early_day.exists(), "02:30 measurement must land in previous day folder"
    assert late_day.exists(), "07:10 measurement must stay on same calendar day"

    early_file = next(early_day.glob("measures-*.json"))
    late_file = next(late_day.glob("measures-*.json"))

    assert early_file.name == "measures-20251024.json"
    assert late_file.name == "measures-20251025.json"

    early_meta = load_json(early_file.with_suffix(".meta.json"))
    late_meta = load_json(late_file.with_suffix(".meta.json"))

    assert_meta_common(early_meta, date="2025-10-24", status="success")
    assert_meta_common(late_meta, date="2025-10-25", status="success")
