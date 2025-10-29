from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence

import pytest

withings_module = pytest.importorskip("agentlab.withings.fetcher")

WithingsFetcher = withings_module.WithingsFetcher
RetryAfter = withings_module.RetryAfter
NetworkError = withings_module.NetworkError


DAY_CUTOVER = "04:00"
TIMEZONE_ID = "Europe/Stockholm"


def new_fetcher(
    transport: Any,
    run_id: str = "test-run-123",
) -> WithingsFetcher:
    """Helper to build a fetcher with consistent defaults for the tests."""

    return WithingsFetcher(
        transport=transport,
        timezone=TIMEZONE_ID,
        day_cutover=DAY_CUTOVER,
        run_id_provider=lambda: run_id,
    )


@dataclass
class FakeTransport:
    """Programmable transport that yields sequential responses or raises errors."""

    responses: Iterable[Any] = field(default_factory=list)
    _queue: list[Any] = field(init=False, repr=False)
    calls: list[tuple[datetime, datetime]] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self._queue = list(self.responses)

    def get_measures(self, from_dt: datetime, to_dt: datetime) -> Any:
        self.calls.append((from_dt, to_dt))
        if not self._queue:
            return []

        action = self._queue.pop(0)
        if isinstance(action, Exception):
            raise action
        if callable(action):
            return action(from_dt, to_dt)
        return action


def sample_measures(*timestamps: str) -> list[dict[str, Any]]:
    """Return a tiny measures payload for the provided ISO timestamps."""

    payload: list[dict[str, Any]] = []
    for idx, iso_ts in enumerate(timestamps, start=1):
        payload.append(
            {
                "group_id": f"grp-{idx}",
                "timestamp": iso_ts,
                "measurements": [
                    {"type": "weight", "unit": "kg", "value": 70.0 + idx},
                    {"type": "bodyfat", "unit": "%", "value": 15.0 + idx},
                ],
            }
        )
    return payload


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def unix_measure_group(moment: datetime) -> dict[str, Any]:
    """Simulate a Withings measure group using Unix timestamps."""

    utc_moment = moment.astimezone(timezone.utc)
    seconds = int(utc_moment.timestamp())
    return {
        "grpid": f"grp-{seconds}",
        "attrib": 0,
        "category": 1,
        "date": seconds,
        "created": seconds,
        "measures": [
            {"type": 1, "unit": -3, "value": 70320},
            {"type": 6, "unit": -1, "value": 152},
        ],
    }


def day_folder(out_root: Path, day: str) -> Path:
    return out_root / "l0" / "withings" / day


def manifest_path(out_root: Path, run_id: str) -> Path:
    manifest_dir = out_root / "runs"
    matches = list(manifest_dir.glob(f"*{run_id}.meta.json"))
    assert matches, f"No manifest created for run_id {run_id}"
    return matches[0]


def assert_meta_common(meta: dict[str, Any], *, date: str, status: str) -> None:
    assert meta["endpoint"] == "measures"
    assert meta["status"] == status
    assert meta["vendor"] == "withings"
    assert meta["timezone"] == TIMEZONE_ID
    assert meta["day_cutover"] == DAY_CUTOVER
    assert meta["day"] == date
    assert meta["scope"]["date"] == date
    payload = meta["payload"]
    if status == "error":
        assert payload["file"] == "measures.error.json"
    else:
        assert payload["file"].startswith("measures-")
    assert payload["extension"] == "json"
    assert payload["size_bytes"] is None or payload["size_bytes"] >= 0
    assert payload["md5"] is None or len(payload["md5"]) == 32
    run_info = meta["run"]
    assert run_info["id"] == "test-run-123"
    assert run_info["correlation"].endswith(f":{date}")
    request = meta["withings"]["request"]
    assert request["action"] == "getmeas"
    assert request["category"] == 1
    assert request["startdate"] <= request["enddate"]
    endpoint = meta["withings"]["endpoint"]
    assert endpoint.endswith("/v2/measure")
    assert meta["withings"]["measures_count"] >= 0


def assert_no_pii(payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload)
    forbidden = ["@", "access_token", "refresh_token", "secret", "password"]
    for token in forbidden:
        assert token not in serialized


@pytest.fixture
def success_transport() -> FakeTransport:
    timestamps = (
        "2025-10-25T02:30:00+02:00",
        "2025-10-25T07:10:00+02:00",
    )
    return FakeTransport(responses=[sample_measures(*timestamps)])

