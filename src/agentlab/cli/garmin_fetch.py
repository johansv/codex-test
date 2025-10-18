"""CLI entrypoint for Garmin data collection."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from datetime import date
from pathlib import Path
from typing import Sequence

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

from dotenv import find_dotenv, load_dotenv

from agentlab.core.garmin import EndpointError, EndpointResult, GarminCredentials, GarminFetchRequest
from agentlab.runners.garmin_fetcher import GarminDataFetcher, GarminPacingConfig
from agentlab.utils.storage import GarminStorageWriter

_DEFAULT_CONFIG_RELATIVE = Path("assets") / "config" / "garmin-endpoints.toml"
logger = logging.getLogger(__name__)


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
    parser.add_argument(
        "--delay-post-login",
        type=float,
        default=5.0,
        help="Seconds to wait after login before first endpoint (default: 5.0).",
    )
    parser.add_argument(
        "--delay-between-endpoints",
        type=float,
        default=2.0,
        help="Seconds to wait between endpoints (default: 2.0).",
    )
    parser.add_argument(
        "--delay-pagination",
        type=float,
        default=1.0,
        help="Seconds to wait between paginated API calls (default: 1.0).",
    )
    parser.add_argument(
        "--delay-jitter",
        type=float,
        default=0.2,
        help="Relative jitter applied to delays (0.2 => ±20%%; default: 0.2).",
    )
    parser.add_argument(
        "--retry-limit",
        type=int,
        default=1,
        help="Maximum number of retry passes for failed endpoints (default: 1).",
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
    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path=dotenv_path, override=False)
    else:
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
) -> tuple[list[str], set[str], Path]:
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

    return list(enabled), disabled_set, path


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


def _configure_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    logging.basicConfig(level=logging.INFO, format="%(message)s")


def _log_cli_event(
    level: int,
    event: str,
    correlation_id: str,
    **payload: object,
) -> None:
    if not logger.isEnabledFor(level):
        return

    record = {
        "event": event,
        "correlation_id": correlation_id,
        **{key: value for key, value in payload.items() if value is not None},
    }
    logger.log(level, json.dumps(record, default=str))


def _accumulate_retry_totals(
    totals: dict[str, int],
    delta: dict[str, int],
) -> None:
    for key in ("scheduled", "succeeded", "failed"):
        totals[key] = totals.get(key, 0) + delta.get(key, 0)


def main(argv: list[str] | None = None) -> int:
    _configure_logging()

    parser = build_parser()
    args = parser.parse_args(argv)

    pacing = GarminPacingConfig(
        post_login_delay=args.delay_post_login,
        between_endpoints_delay=args.delay_between_endpoints,
        pagination_delay=args.delay_pagination,
        jitter_ratio=args.delay_jitter,
        retry_limit=args.retry_limit,
    )
    fetcher = GarminDataFetcher(pacing=pacing)

    if args.list_endpoints:
        for name in fetcher.supported_endpoints:
            print(name)
        return 0

    start, end = _resolve_range(args)
    credentials = _load_credentials(args)
    defaults, disabled, config_path_used = _load_endpoint_defaults(fetcher, args.config)
    endpoints = _select_endpoints(fetcher, defaults, disabled, args.include, args.exclude)
    output_root = Path(args.output_dir)
    storage = GarminStorageWriter(output_root)

    run_id = uuid.uuid4().hex

    if args.debug:
        job_settings = {
            "username": credentials.username,
            "mfa_provided": bool(credentials.mfa_code),
            "date": args.date,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "include": args.include or [],
            "exclude": args.exclude or [],
            "endpoints": endpoints,
            "defaults_disabled": sorted(disabled),
            "config_path": str(config_path_used),
            "output_dir": str(output_root),
            "pacing": {
                "post_login_delay": pacing.post_login_delay,
                "between_endpoints_delay": pacing.between_endpoints_delay,
                "pagination_delay": pacing.pagination_delay,
                "jitter_ratio": pacing.jitter_ratio,
                "retry_limit": pacing.retry_limit,
            },
            "debug": True,
        }
        _log_cli_event(
            logging.INFO,
            "garmin.cli.config",
            run_id,
            settings=job_settings,
        )

    _log_cli_event(
        logging.INFO,
        "garmin.cli.run.start",
        run_id,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        endpoints=endpoints,
    )

    summary: list[dict[str, object]] = []
    days = list(GarminFetchRequest(start_date=start, end_date=end).iter_dates())
    retry_totals = {"scheduled": 0, "succeeded": 0, "failed": 0}
    any_success = False

    for day in days:
        day_request = GarminFetchRequest(start_date=day, end_date=day, endpoints=endpoints)
        day_correlation_id = f"{run_id}:{day.isoformat()}"

        _log_cli_event(
            logging.INFO,
            "garmin.cli.day.start",
            day_correlation_id,
            date=day.isoformat(),
            endpoints=endpoints,
        )

        observer = None
        if args.debug:
            day_str = day.isoformat()

            def _observer(endpoint: str, *, _day=day_str) -> None:
                print(f"[garmin] {_day} -> {endpoint}", file=sys.stderr)

            observer = _observer

        def _on_result(result: EndpointResult, *, _day=day) -> None:
            storage.write_result(_day, result)

        def _on_error(error: EndpointError, *, _day=day) -> None:
            storage.write_error(_day, error)

        outcome = fetcher.fetch(
            credentials,
            day_request,
            observer=observer,
            correlation_id=day_correlation_id,
            result_callback=_on_result,
            error_callback=_on_error,
        )

        successes = list(dict.fromkeys(result.endpoint for result in outcome.results))
        failures = [
            {"endpoint": error.endpoint, "message": error.message}
            for error in outcome.errors
        ]
        retry_summary = {
            "scheduled": outcome.retries.scheduled,
            "succeeded": outcome.retries.succeeded,
            "failed": outcome.retries.failed,
        }
        _accumulate_retry_totals(retry_totals, retry_summary)
        any_success = any_success or bool(successes)

        summary.append(
            {
                "date": day.isoformat(),
                "successes": successes,
                "failures": failures,
                "retry_outcomes": retry_summary,
            }
        )

        _log_cli_event(
            logging.INFO,
            "garmin.cli.day.completed",
            day_correlation_id,
            date=day.isoformat(),
            successes=len(successes),
            failures=len(failures),
            retry_outcomes=retry_summary,
        )

    total_successes = sum(len(entry["successes"]) for entry in summary)
    total_failures = sum(len(entry["failures"]) for entry in summary)
    exit_code = 0 if any_success else 1

    _log_cli_event(
        logging.INFO if exit_code == 0 else logging.ERROR,
        "garmin.cli.run.completed" if exit_code == 0 else "garmin.cli.run.failed",
        run_id,
        totals={
            "days": len(summary),
            "successes": total_successes,
            "failures": total_failures,
            "retry_outcomes": retry_totals,
        },
        exit_code=exit_code,
    )

    json.dump(summary, sys.stdout, indent=2)
    print()
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
