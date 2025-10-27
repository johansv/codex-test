from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from hashlib import sha256

import pytest

from agentlab.cli import sleep_needs


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_sleep_needs_cli_builds_summaries(tmp_path: Path) -> None:
    out_root = tmp_path / "out"

    first_day = out_root / "2025-08-21"
    second_day = out_root / "2025-08-22"
    third_day = out_root / "2025-08-23"

    # Day 1: solid sleep
    _write_json(
        first_day / "sleep.json",
        {
            "sessions": [
                {
                    "start": "2025-08-21T22:00:00",
                    "end": "2025-08-22T06:30:00",
                    "stages": [
                        {"stage": "LIGHT", "duration": 4 * 3600},
                        {"stage": "DEEP", "duration": 2 * 3600},
                        {"stage": "REM", "duration": 1.5 * 3600},
                        {"stage": "AWAKE", "duration": 0.5 * 3600},
                    ],
                }
            ]
        },
    )
    _write_json(
        first_day / "resting-heart-rate.json",
        {
            "allMetrics": {
                "metricsMap": {
                    "WELLNESS_RESTING_HEART_RATE": [
                        {"calendarDate": "2025-08-21", "value": 56},
                    ]
                }
            }
        },
    )
    _write_json(
        first_day / "progress-summary.json",
        {
            "summary": {
                "trainingLoad": 500,
            }
        },
    )
    _write_json(first_day / "hrv.json", {"average": 80})
    _write_json(first_day / "body-battery.json", {"highestBodyBattery": 90})

    # Day 2: higher training load, slightly elevated HR
    _write_json(
        second_day / "sleep.json",
        {
            "sessions": [
                {
                    "start": "2025-08-22T22:30:00",
                    "end": "2025-08-23T06:00:00",
                    "stages": [
                        {"stage": "LIGHT", "duration": 4 * 3600},
                        {"stage": "DEEP", "duration": 1.5 * 3600},
                        {"stage": "REM", "duration": 1.5 * 3600},
                        {"stage": "AWAKE", "duration": 0.5 * 3600},
                    ],
                }
            ]
        },
    )
    _write_json(
        second_day / "resting-heart-rate.json",
        {
            "allMetrics": {
                "metricsMap": {
                    "WELLNESS_RESTING_HEART_RATE": [
                        {"calendarDate": "2025-08-22", "value": 58},
                    ]
                }
            }
        },
    )
    _write_json(
        second_day / "progress-summary.json",
        {
            "summary": {
                "trainingLoad": 750,
            }
        },
    )
    _write_json(second_day / "hrv.json", {"average": 75})
    _write_json(second_day / "body-battery.json", {"highestBodyBattery": 70})
    _write_json(second_day / "stress.json", {"averageStressLevel": 48})

    # Day 3: insufficient sleep (should be skipped)
    _write_json(
        third_day / "sleep.json",
        {
            "sessions": [
                {
                    "start": "2025-08-23T22:30:00",
                    "end": "2025-08-23T23:30:00",
                    "stages": [
                        {"stage": "LIGHT", "duration": 50 * 60},
                        {"stage": "AWAKE", "duration": 10 * 60},
                    ],
                }
            ]
        },
    )

    exit_code = sleep_needs.main(
        [
            "--start",
            "2025-08-21",
            "--end",
            "2025-08-23",
            "--out-root",
            str(out_root),
        ]
    )
    assert exit_code == 0

    summary_day1 = json.loads((first_day / "ai" / "sleep_summary.json").read_text(encoding="utf-8"))
    summary_day2 = json.loads((second_day / "ai" / "sleep_summary.json").read_text(encoding="utf-8"))
    summary_day3 = json.loads((third_day / "ai" / "sleep_summary.json").read_text(encoding="utf-8"))

    assert summary_day1["status"] == "ok"
    assert pytest.approx(summary_day1["sleep"]["asleep_hours"], rel=1e-3) == 7.5
    assert summary_day1["recommendation"]["baseline_sleep_duration"] == summary_day1["sleep"]["asleep_hours"]

    assert summary_day2["status"] == "ok"
    assert summary_day2["recommendation"]["recommended_sleep_duration"] > summary_day2["sleep"]["asleep_hours"]
    assert summary_day2["recommendation"]["adjustments"]["training_load"] > 0

    assert summary_day3["status"] == "skipped"
    assert summary_day3["state"]["sleep_debt"] == summary_day2["state"]["sleep_debt"]

    meta_path = second_day / "ai" / "sleep_summary.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    payload = (second_day / "ai" / "sleep_summary.json").read_bytes()
    assert meta["checksum"]["sha256"] == sha256(payload).hexdigest()
    assert meta["size_bytes"] == len(payload)

    # Dry-run with debug should still complete successfully.
    exit_code = sleep_needs.main(
        [
            "--start",
            "2025-08-21",
            "--end",
            "2025-08-22",
            "--out-root",
            str(out_root),
            "--dry-run",
            "--debug",
        ]
    )
    assert exit_code == 0


def test_sleep_needs_baseline_smoothing(tmp_path: Path) -> None:
    out_root = tmp_path / "out"

    def _daily_sleep_payload(hours: float, wake: float = 0.1) -> dict:
        asleep_seconds = int(hours * 3600)
        awake_seconds = int(wake * 3600)
        return {
            "dailySleepDTO": {
                "sleepTimeSeconds": asleep_seconds + awake_seconds,
                "deepSleepSeconds": asleep_seconds // 3,
                "lightSleepSeconds": asleep_seconds // 2,
                "remSleepSeconds": asleep_seconds - (asleep_seconds // 3) - (asleep_seconds // 2),
                "awakeSleepSeconds": awake_seconds,
                "sleepStartTimestampGMT": "2025-01-01T22:00:00.0",
                "sleepEndTimestampGMT": "2025-01-02T06:00:00.0",
            }
        }

    def _write_day(date: datetime.date, hours: float) -> Path:
        day_dir = out_root / date.isoformat()
        _write_json(day_dir / "sleep.json", _daily_sleep_payload(hours))
        _write_json(day_dir / "resting-heart-rate.json", {"restingHeartRate": 55})
        _write_json(day_dir / "hrv.json", {"hrvSummary": {"lastNightAvg": 40}})
        _write_json(day_dir / "body-battery.json", {"bodyBatteryMostRecentValue": 80})
        _write_json(day_dir / "progress-summary.json", {"summary": {"trainingLoad": 400}})
        return day_dir

    start_date = datetime.strptime("2025-01-01", "%Y-%m-%d").date()
    for i in range(30):
        _write_day(start_date + timedelta(days=i), hours=7.2)

    exit_code = sleep_needs.main(
        [
            "--start",
            "2025-01-01",
            "--end",
            "2025-01-30",
            "--out-root",
            str(out_root),
        ]
    )
    assert exit_code == 0

    baseline_day30 = json.loads(
        (out_root / "2025-01-30" / "ai" / "sleep_summary.json").read_text(encoding="utf-8")
    )["recommendation"]["baseline_sleep_duration"]

    new_day = start_date + timedelta(days=30)
    _write_day(new_day, hours=5.5)

    exit_code = sleep_needs.main(
        [
            "--start",
            new_day.isoformat(),
            "--end",
            new_day.isoformat(),
            "--out-root",
            str(out_root),
        ]
    )
    assert exit_code == 0

    summary_new = json.loads((out_root / new_day.isoformat() / "ai" / "sleep_summary.json").read_text(encoding="utf-8"))
    new_baseline = summary_new["recommendation"]["baseline_sleep_duration"]
    assert abs(new_baseline - baseline_day30) <= 0.051
    assert "recovery" in summary_new
    assert "score" in summary_new["recovery"]
