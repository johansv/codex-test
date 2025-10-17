"""CLI entrypoint for Garmin data collection."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Sequence

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

from dotenv import load_dotenv

from agentlab.core.garmin import GarminCredentials, GarminFetchRequest
from agentlab.runners.garmin_fetcher import GarminDataFetcher
from agentlab.utils.storage import GarminStorageWriter

_DEFAULT_CONFIG_RELATIVE = Path("assets") / "config" / "garmin-endpoints.toml"


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
        "--include",
        dest="include",
        action="append",
        default=None,
        help="Explicitly include an endpoint (repeat to specify more than one).",
    )
    parser.add_argument(
        "--exclude",
        dest="exclude",
        action="append",
        default=None,
        help="Exclude an endpoint from the run (repeat to specify more than one).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Endpoint configuration file (default: assets/config/garmin-endpoints.toml).",
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


def _default_config_path() -> Path:
    current = Path(__file__).resolve()
    for candidate_root in (current.parent, *current.parents):
        candidate = candidate_root / _DEFAULT_CONFIG_RELATIVE
        if candidate.exists():
            return candidate
    raise SystemExit(
        f"Could not locate default endpoint config at {_DEFAULT_CONFIG_RELATIVE}"
    )


def _load_endpoint_defaults(
    fetcher: GarminDataFetcher,
    config_path: Path | None,
) -> tuple[list[str], set[str]]:
    path = config_path if config_path is not None else _default_config_path()
    if not path.exists():
        raise SystemExit(f"Endpoint config not found: {path}")

    supported = set(fetcher.supported_endpoints)
    with path.open("rb") as handle:
        data = tomllib.load(handle)

    defaults_section = data.get("defaults", {})
    enabled = defaults_section.get("enabled")
    if not isinstance(enabled, list) or not all(isinstance(name, str) for name in enabled):
        raise SystemExit("Endpoint config must define defaults.enabled as a list of strings.")
    if not enabled:
        raise SystemExit("Endpoint config defaults.enabled must contain at least one entry.")
    disabled = defaults_section.get("disabled", [])
    if disabled and (
        not isinstance(disabled, list) or not all(isinstance(name, str) for name in disabled)
    ):
        raise SystemExit(
            "Endpoint config defaults.disabled must be a list of strings when provided."
        )

    duplicates = [name for name in enabled if enabled.count(name) > 1]
    if duplicates:
        duplicate_labels = ", ".join(sorted(set(duplicates)))
        raise SystemExit(
            f"Endpoint config defaults.enabled contains duplicates: {duplicate_labels}"
        )

    unknown_defaults = [name for name in enabled if name not in supported]
    if unknown_defaults:
        unknown_labels = ", ".join(sorted(unknown_defaults))
        raise SystemExit(
            f"Endpoint config references unsupported endpoint(s): {unknown_labels}"
        )

    disabled_set = set(disabled)
    unknown_disabled = [name for name in disabled_set if name not in supported]
    if unknown_disabled:
        raise SystemExit(
            f"Endpoint config disabled list references unsupported endpoint(s): "
            f"{', '.join(sorted(unknown_disabled))}"
        )

    overlap = [name for name in enabled if name in disabled_set]
    if overlap:
        raise SystemExit(
            f"Endpoint config lists the same endpoint as enabled and disabled: "
            f"{', '.join(sorted(overlap))}"
        )

    return list(enabled), disabled_set


def _select_endpoints(
    fetcher: GarminDataFetcher,
    defaults: list[str],
    disabled: set[str],
    include: Sequence[str] | None,
    exclude: Sequence[str] | None,
) -> list[str]:
    supported = set(fetcher.supported_endpoints)

    def _normalise(values: Sequence[str] | None) -> list[str]:
        result: list[str] = []
        if not values:
            return result
        for entry in values:
            item = entry.strip()
            if item and item not in result:
                result.append(item)
        return result

    include = _normalise(include)
    exclude = _normalise(exclude)

    def _validate(names: Sequence[str]) -> None:
        unknown = [name for name in names if name not in supported]
        if unknown:
            raise SystemExit(f"Unknown endpoint(s): {', '.join(sorted(unknown))}")

    _validate(include)
    _validate(exclude)

    disallowed = [name for name in include if name in disabled]
    if disallowed:
        raise SystemExit(
            f"Endpoint(s) disabled via configuration: {', '.join(sorted(disallowed))}"
        )

    selection: list[str] = list(dict.fromkeys(defaults))
    for name in include:
        if name not in selection:
            selection.append(name)

    exclude_set = set(exclude)
    selection = [name for name in selection if name not in exclude_set]

    if not selection:
        raise SystemExit("No endpoints selected after applying include/exclude rules.")

    return selection


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
    defaults, disabled = _load_endpoint_defaults(fetcher, args.config)
    endpoints = _select_endpoints(fetcher, defaults, disabled, args.include, args.exclude)
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
                "saved": list(dict.fromkeys(result.endpoint for result in outcome.results)),
                "errors": list(dict.fromkeys(error.endpoint for error in outcome.errors)),
            }
        )

    json.dump(summary, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
