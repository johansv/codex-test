"""CLI entrypoint for Garmin data collection."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv

from agentlab.core.garmin import GarminCredentials, GarminFetchRequest
from agentlab.runners.garmin_fetcher import GarminDataFetcher
from agentlab.utils.storage import GarminStorageWriter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download Garmin Connect data using explicit endpoint calls.",
    )
    parser.add_argument(
        "--date",
        help="Collect data for a single date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--start-date",
        help="Start date for collection (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--end-date",
        help="End date for collection (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--endpoint",
        dest="endpoints",
        action="append",
        default=None,
        help="Endpoint identifier to collect (repeat to specify more than one).",
    )
    parser.add_argument(
        "--list-endpoints",
        action="store_true",
        help="Print the supported endpoint identifiers and exit.",
    )
    parser.add_argument(
        "--mfa-code",
        default=None,
        help="TOTP or MFA code when required for login (default: None).",
    )
    parser.add_argument(
       "--output-dir",
        default="out",
        help="Directory where fetched data is stored (default: ./out).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Log each endpoint as it executes.",
    )
    return parser


def _parse_date(value: str | None, label: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - argparse validation
        raise argparse.ArgumentTypeError(f"{label} must be YYYY-MM-DD: {value}") from exc


def _resolve_range(args: argparse.Namespace) -> tuple[date, date]:
    if args.date:
        day = _parse_date(args.date, "--date")
        return day, day

    start = _parse_date(args.start_date, "--start-date")
    end = _parse_date(args.end_date, "--end-date")
    if not start or not end:
        raise SystemExit("Provide either --date or both --start-date and --end-date.")
    if end < start:
        raise SystemExit("--end-date cannot precede --start-date.")
    return start, end


def _load_credentials(args: argparse.Namespace) -> GarminCredentials:
    load_dotenv()
    username = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")
    if not username or not password:
        raise SystemExit("GARMIN_EMAIL and GARMIN_PASSWORD must be set in the environment.")
    return GarminCredentials(username=username, password=password, mfa_code=args.mfa_code)


def _resolve_endpoints(
    fetcher: GarminDataFetcher,
    endpoints: Sequence[str] | None,
) -> Sequence[str] | None:
    if endpoints is None:
        return None

    supported = set(fetcher.supported_endpoints)
    unknown = [entry for entry in endpoints if entry not in supported]
    if unknown:
        raise SystemExit(f"Unknown endpoint(s): {', '.join(sorted(unknown))}")
    return list(dict.fromkeys(endpoints))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    fetcher = GarminDataFetcher()

    if args.list_endpoints:
        for name in fetcher.supported_endpoints:
            print(name)
        return 0

    start, end = _resolve_range(args)
    credentials = _load_credentials(args)
    endpoints = _resolve_endpoints(fetcher, args.endpoints)
    output_root = Path(args.output_dir)
    storage = GarminStorageWriter(output_root)

    summary: list[dict[str, object]] = []
    days = list(GarminFetchRequest(start_date=start, end_date=end).iter_dates())
    for day in days:
        day_request = GarminFetchRequest(start_date=day, end_date=day, endpoints=endpoints)

        observer = None
        if args.debug:
            day_str = day.isoformat()

            def _observer(endpoint: str, *, _day=day_str) -> None:
                print(f"[garmin] {_day} -> {endpoint}", file=sys.stderr)

            observer = _observer

        outcome = fetcher.fetch(credentials, day_request, observer=observer)
        storage.store(day, outcome)

        summary.append(
            {
                "date": day.isoformat(),
                "saved": [result.endpoint for result in outcome.results],
                "errors": [error.endpoint for error in outcome.errors],
            }
        )

    json.dump(summary, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
