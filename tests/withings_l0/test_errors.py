from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from tests.withings_l0._utils import (
    FakeTransport,
    NetworkError,
    assert_meta_common,
    day_folder,
    load_json,
    new_fetcher,
    sidecar_path,
)


def test_error_artifacts_on_failure(tmp_path: Path) -> None:
    """Acceptance Criterion 4) failure writes error artifacts and updates metadata."""

    transport = FakeTransport(responses=[NetworkError("boom")])
    fetcher = new_fetcher(transport)

    with pytest.raises(NetworkError):
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

    error_json = day_dir / "measures.error.json"
    error_meta = sidecar_path(error_json)

    assert error_json.exists()
    assert error_meta.exists()

    meta = load_json(error_meta)
    assert_meta_common(meta, date="2025-10-25", status="error")
    assert "error" in meta
    assert meta["error"]["message"]
