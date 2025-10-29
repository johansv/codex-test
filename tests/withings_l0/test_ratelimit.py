from __future__ import annotations

from datetime import date
from pathlib import Path

from tests.withings_l0._utils import (
    FakeTransport,
    assert_meta_common,
    day_folder,
    load_json,
    RetryAfter,
    new_fetcher,
    sample_measures,
)


def test_retry_after_and_backoff(tmp_path: Path) -> None:
    """Acceptance Criterion 5) honors Retry-After and retries with backoff before succeeding."""

    transport = FakeTransport(
        responses=[
            RetryAfter(5),
            sample_measures("2025-10-25T07:10:00+02:00"),
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

    assert len(transport.calls) == 2, "Fetcher should retry after rate limit"

    day_dir = day_folder(tmp_path, "2025-10-25")
    meta = load_json(next(day_dir.glob("measures-*.meta.json")))
    assert_meta_common(meta, date="2025-10-25", status="success")
