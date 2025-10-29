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


def test_skip_existing_is_idempotent(tmp_path: Path) -> None:
    """Acceptance Criterion 3) skip-existing avoids rewrites and records skipped meta."""

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

    day_dir = day_folder(tmp_path, "2025-10-25")
    initial_json = sorted(
        path
        for path in day_dir.glob("measures-*.json")
        if not path.name.endswith(".meta.json")
    )
    assert len(initial_json) == 1
    meta_path = day_dir / initial_json[0].name.replace(".json", ".meta.json")
    initial_meta = load_json(meta_path)
    assert_meta_common(initial_meta, date="2025-10-25", status="success")

    second_transport = FakeTransport(responses=[sample_measures("2025-10-25T07:10:00+02:00")])
    fetcher = new_fetcher(second_transport)
    fetcher.fetch_date_range(
        out_root=tmp_path,
        start_date=date(2025, 10, 25),
        end_date=date(2025, 10, 25),
        skip_existing=True,
        dry_run=True,
        resume=False,
    )

    final_json = sorted(
        path
        for path in day_dir.glob("measures-*.json")
        if not path.name.endswith(".meta.json")
    )
    assert [p.name for p in final_json] == [p.name for p in initial_json], (
        "JSON files should not duplicate"
    )

    final_meta = load_json(meta_path)
    assert_meta_common(final_meta, date="2025-10-25", status="skipped")
