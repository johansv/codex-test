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
    sidecar_path,
)


def test_strict_calendar_routing_without_cutover(tmp_path: Path) -> None:
    """Measurements before 04:00 stay on the same calendar day (no artificial cutover)."""

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
        end_date=date(2025, 10, 25),
        skip_existing=False,
        dry_run=True,
        resume=False,
    )

    previous_day = day_folder(tmp_path, "2025-10-24")
    target_day = day_folder(tmp_path, "2025-10-25")

    assert not previous_day.exists(), "Strict calendar routing must not emit a previous-day folder"
    assert target_day.exists(), "Expected measures to land on the same calendar day"

    data_files = [p for p in sorted(target_day.glob("measures-*.json")) if not p.name.endswith(".meta.json")]
    assert data_files, "Expected at least one payload file for the target day"
    for payload_file in data_files:
        assert payload_file.name.startswith("measures-20251025")
        meta = load_json(sidecar_path(payload_file))
        assert_meta_common(meta, date="2025-10-25", status="success")
