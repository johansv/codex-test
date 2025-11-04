"""CLI entrypoint for Garmin data collection."""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any, Sequence

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

from dotenv import find_dotenv, load_dotenv

from agentlab.core.garmin import EndpointError, EndpointResult, GarminCredentials, GarminFetchRequest
from agentlab.metadata import DayStats, RunError, RunMetaReader, RunMetaWriter, RunParams
from agentlab.runners.garmin_fetcher import GarminDataFetcher, GarminPacingConfig, RateLimitExceeded
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
        "--preset",
        default=None,
        help="Named endpoint preset defined in the configuration file.",
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
        help="Relative jitter applied to delays (0.2 => +/-20%%; default: 0.2).",
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
    except ValueError as exc:
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


def _normalise_preset_names(value: str | Sequence[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        candidates = value.split(",")
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        candidates: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise SystemExit("Preset selections must be strings when provided.")
            candidates.extend(item.split(","))
    else:
        raise SystemExit("Preset selections must be provided as a comma separated string or list.")

    seen: set[str] = set()
    result: list[str] = []
    for candidate in candidates:
        name = candidate.strip()
        if not name:
            continue
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _load_endpoint_defaults(
    fetcher: GarminDataFetcher,
    config_path: Path | None,
    preset_selection: str | None,
) -> tuple[list[str], set[str], Path, list[str]]:
    path = config_path if config_path is not None else _default_config_path()
    if not path.exists():
        raise SystemExit(f"Endpoint config not found: {path}")

    supported = set(fetcher.supported_endpoints)
    with path.open("rb") as handle:
        data = tomllib.load(handle)

    presets = data.get("presets")
    defaults_section = data.get("defaults", {})
    requested_presets = _normalise_preset_names(preset_selection)
    selected_presets: list[str] = []

    if presets:
        if not isinstance(presets, dict):
            raise SystemExit("Endpoint config presets must be a table of named configurations.")
        selected_presets = requested_presets or _normalise_preset_names(
            defaults_section.get("preset")
        )
        if not selected_presets:
            raise SystemExit(
                "Endpoint config defines presets but none was selected. Provide --preset or set defaults.preset."
            )
        missing = [name for name in selected_presets if name not in presets]
        if missing:
            available = ", ".join(sorted(presets.keys()))
            raise SystemExit(
                f"Unknown endpoint preset(s) "
                f"{', '.join(sorted(missing))}. Available presets: {available}"
            )
        combined_enabled: list[str] = []
        seen_enabled: set[str] = set()
        combined_disabled: set[str] = set()

        for preset_name in selected_presets:
            preset_data = presets.get(preset_name)
            if not isinstance(preset_data, dict):
                raise SystemExit(f"Preset '{preset_name}' must be a table of named configuration values.")
            enabled = preset_data.get("enabled")
            if not isinstance(enabled, list) or not all(isinstance(name, str) for name in enabled):
                raise SystemExit(f"Preset '{preset_name}' must define an enabled list of strings.")
            if not enabled:
                raise SystemExit(f"Preset '{preset_name}' enabled list must contain at least one entry.")
            duplicate_entries = [name for name in enabled if enabled.count(name) > 1]
            if duplicate_entries:
                duplicate_labels = ", ".join(sorted(set(duplicate_entries)))
                raise SystemExit(
                    f"Preset '{preset_name}' enabled contains duplicates: {duplicate_labels}"
                )
            unknown_defaults = [name for name in enabled if name not in supported]
            if unknown_defaults:
                unknown_labels = ", ".join(sorted(unknown_defaults))
                raise SystemExit(
                    f"Preset '{preset_name}' references unsupported endpoint(s): {unknown_labels}"
                )
            for endpoint in enabled:
                if endpoint not in seen_enabled:
                    seen_enabled.add(endpoint)
                    combined_enabled.append(endpoint)

            disabled_entries = preset_data.get("disabled", [])
            if disabled_entries and (
                not isinstance(disabled_entries, list)
                or not all(isinstance(name, str) for name in disabled_entries)
            ):
                raise SystemExit(
                    f"Preset '{preset_name}' disabled entries must be strings when provided."
                )
            unknown_disabled = [
                name for name in disabled_entries if name not in supported
            ]
            if unknown_disabled:
                unknown_labels = ", ".join(sorted(unknown_disabled))
                raise SystemExit(
                    f"Preset '{preset_name}' disabled references unsupported endpoint(s): {unknown_labels}"
                )
            combined_disabled.update(disabled_entries)

        enabled = combined_enabled
        disabled_set = combined_disabled
    else:
        if requested_presets:
            raise SystemExit("Config does not define presets but --preset was provided.")
        enabled = defaults_section.get("enabled")
        disabled = defaults_section.get("disabled", [])
        if disabled and (
            not isinstance(disabled, list) or not all(isinstance(name, str) for name in disabled)
        ):
            raise SystemExit("Endpoint configuration disabled entries must be strings when provided.")
        disabled_set = set(disabled)

    if not isinstance(enabled, list) or not all(isinstance(name, str) for name in enabled):
        raise SystemExit("Endpoint configuration must provide an enabled list of strings.")
    if not enabled:
        raise SystemExit("Endpoint configuration enabled list must contain at least one entry.")
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

    return list(enabled), disabled_set, path, selected_presets


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
    defaults, disabled, config_path_used, selected_presets = _load_endpoint_defaults(
        fetcher, args.config, args.preset
    )
    endpoints = _select_endpoints(fetcher, defaults, disabled, args.include, args.exclude)
    if hasattr(fetcher, "partition_endpoints"):
        run_date_endpoints, per_day_endpoints = fetcher.partition_endpoints(endpoints)
    else:
        run_date_endpoints = []
        per_day_endpoints = list(endpoints)
    run_date = date.today()
    output_root = Path(args.output_dir)
    scheduled_days = max(1, (end - start).days + 1)

    run_id = f"garmin-{int(time.time())}"
    storage = GarminStorageWriter(output_root, run_id=run_id)
    writer = RunMetaWriter(
        out_root=output_root,
        timezone="Europe/Stockholm",
        run_id=run_id,
        garminconnect_version=storage.garmin_version,
        vendor_label="garmin",
    )

    skip_existing = bool(getattr(args, "skip_existing", False))
    resume = bool(getattr(args, "resume", False))
    dry_run_flag = bool(getattr(args, "dry_run", False))
    preset_label = ", ".join(selected_presets) if selected_presets else (args.preset or "")
    writer.start_run(
        RunParams(
            start_date=start,
            end_date=end,
            preset=preset_label,
            skip_existing=skip_existing,
            resume=resume,
        ),
        vendor="garmin",
        days_scheduled=scheduled_days,
        dry_run=dry_run_flag,
        out_root=output_root,
    )
    run_aborted = False

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
            "endpoint_count": len(endpoints),
            "run_date": run_date.isoformat(),
            "run_date_endpoints": run_date_endpoints,
            "run_date_endpoint_count": len(run_date_endpoints),
            "per_day_endpoints": per_day_endpoints,
            "per_day_endpoint_count": len(per_day_endpoints),
            "defaults_disabled": sorted(disabled),
            "config_path": str(config_path_used),
            "output_dir": str(output_root),
            "presets": selected_presets or None,
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
        endpoint_count=len(endpoints),
        presets=selected_presets or None,
    )

    summary: list[dict[str, object]] = []
    days = list(GarminFetchRequest(start_date=start, end_date=end).iter_dates())
    retry_totals = {"scheduled": 0, "succeeded": 0, "failed": 0}
    any_success = False
    rate_limit_exc: RateLimitExceeded | None = None

    if run_date_endpoints:
        run_date_request = GarminFetchRequest(
            start_date=run_date,
            end_date=run_date,
            endpoints=run_date_endpoints,
        )
        run_correlation_id = f"{run_id}:{run_date.isoformat()}"

        _log_cli_event(
            logging.INFO,
            "garmin.cli.run_date.start",
            run_correlation_id,
            date=run_date.isoformat(),
            endpoint_count=len(run_date_endpoints),
        )

        run_observer = None
        if args.debug:
            run_day_str = run_date.isoformat()

            def _run_observer(endpoint: str, *, _day=run_day_str) -> None:
                print(f"[garmin] {_day} (run-date) -> {endpoint}", file=sys.stderr)

            run_observer = _run_observer

        def _run_on_result(result: EndpointResult, *, _day=run_date) -> None:
            storage.write_result(_day, result, correlation_id=run_correlation_id)

        def _run_on_error(error: EndpointError, *, _day=run_date) -> None:
            storage.write_error(_day, error)

        try:
            run_outcome = fetcher.fetch(
                credentials,
                run_date_request,
                observer=run_observer,
                correlation_id=run_correlation_id,
                result_callback=_run_on_result,
                error_callback=_run_on_error,
            )
        except RateLimitExceeded as exc:
            rate_limit_exc = exc
            summary.append(
                {
                    "date": run_date.isoformat(),
                    "successes": [],
                    "failures": [
                        {"endpoint": "rate-limit", "message": str(exc)}
                    ],
                    "retry_outcomes": {"scheduled": 0, "succeeded": 0, "failed": 0},
                    "run_date": True,
                    "rate_limited": True,
                }
            )
            _log_cli_event(
                logging.ERROR,
                "garmin.cli.run_date.rate_limit",
                run_correlation_id,
                wait_minutes=exc.wait_minutes,
            )
        else:
            successes = list(dict.fromkeys(result.endpoint for result in run_outcome.results))
            failures = [
                {"endpoint": error.endpoint, "message": error.message}
                for error in run_outcome.errors
            ]
            retry_summary = {
                "scheduled": run_outcome.retries.scheduled,
                "succeeded": run_outcome.retries.succeeded,
                "failed": run_outcome.retries.failed,
            }
            _accumulate_retry_totals(retry_totals, retry_summary)
            any_success = any_success or bool(successes)

            summary.append(
                {
                    "date": run_date.isoformat(),
                    "successes": successes,
                    "failures": failures,
                    "retry_outcomes": retry_summary,
                    "run_date": True,
                }
            )

            _log_cli_event(
                logging.INFO,
                "garmin.cli.run_date.completed",
                run_correlation_id,
                date=run_date.isoformat(),
                successes=len(successes),
                failures=len(failures),
                retry_outcomes=retry_summary,
            )

    for day in days:
        if rate_limit_exc is not None:
            break

        writer.start_day(day)

        if not per_day_endpoints:
            summary.append(
                {
                    "date": day.isoformat(),
                    "successes": [],
                    "failures": [],
                    "retry_outcomes": {"scheduled": 0, "succeeded": 0, "failed": 0},
                }
            )
            writer.end_day(
                day,
                status="done",
                stats=DayStats(
                    endpoints_ok=0,
                    endpoints_fail=0,
                    endpoints_skipped=0,
                    bytes_payload=0,
                    duration_s=0,
                ),
            )
            continue

        day_request = GarminFetchRequest(
            start_date=day,
            end_date=day,
            endpoints=per_day_endpoints,
        )
        day_correlation_id = f"{run_id}:{day.isoformat()}"
        day_str = day.isoformat()
        day_start_time = time.perf_counter()
        day_success_endpoints: set[str] = set()
        day_error_keys: set[tuple[str, tuple[tuple[str, str | int], ...]]] = set()
        day_payload_bytes = 0
        day_skipped_count = 0
        day_last_endpoint: str | None = None

        def _scope_key(scope: dict[str, str | int] | None) -> tuple[tuple[str, str | int], ...]:
            if not scope:
                return ()
            return tuple(sorted(scope.items()))

        def _elapsed_seconds() -> int:
            return max(0, int(round(time.perf_counter() - day_start_time)))

        _log_cli_event(
            logging.INFO,
            "garmin.cli.day.start",
            day_correlation_id,
            date=day.isoformat(),
            endpoint_count=len(per_day_endpoints),
        )

        def _observer(endpoint: str, *, _day=day_str) -> None:
            nonlocal day_last_endpoint
            day_last_endpoint = endpoint
            if args.debug:
                print(f"[garmin] {_day} -> {endpoint}", file=sys.stderr)

        def _on_result(result: EndpointResult, *, _day=day) -> None:
            nonlocal day_payload_bytes, day_last_endpoint
            day_last_endpoint = result.endpoint
            storage.write_result(_day, result, correlation_id=day_correlation_id)
            metadata = result.metadata or {}
            size_value = metadata.get("payload_size_bytes")
            if isinstance(size_value, int):
                day_payload_bytes += size_value
            key = (result.endpoint, _scope_key(result.scope))
            day_error_keys.discard(key)
            day_success_endpoints.add(result.endpoint)

        def _on_error(error: EndpointError, *, _day=day) -> None:
            nonlocal day_last_endpoint
            day_last_endpoint = error.endpoint
            storage.write_error(_day, error)
            key = (error.endpoint, _scope_key(error.scope))
            day_error_keys.add(key)

        try:
            outcome = fetcher.fetch(
                credentials,
                day_request,
                observer=_observer,
                correlation_id=day_correlation_id,
                result_callback=_on_result,
                error_callback=_on_error,
            )
        except RateLimitExceeded as exc:
            rate_limit_exc = exc
            day_error_keys.add(("rate-limit", ()))
            writer.end_day(
                day,
                status="partial",
                stats=DayStats(
                    endpoints_ok=len(day_success_endpoints),
                    endpoints_fail=len(day_error_keys),
                    endpoints_skipped=day_skipped_count,
                    bytes_payload=day_payload_bytes,
                    duration_s=_elapsed_seconds(),
                ),
                last_endpoint=day_last_endpoint or "rate-limit",
            )
            summary.append(
                {
                    "date": day.isoformat(),
                    "successes": [],
                    "failures": [
                        {"endpoint": "rate-limit", "message": str(exc)}
                    ],
                    "retry_outcomes": {"scheduled": 0, "succeeded": 0, "failed": 0},
                    "rate_limited": True,
                }
            )
            _log_cli_event(
                logging.ERROR,
                "garmin.cli.rate_limit",
                day_correlation_id,
                wait_minutes=exc.wait_minutes,
            )
            break
        except Exception as exc:
            writer.end_day(
                day,
                status="partial",
                stats=DayStats(
                    endpoints_ok=len(day_success_endpoints),
                    endpoints_fail=len(day_error_keys),
                    endpoints_skipped=day_skipped_count,
                    bytes_payload=day_payload_bytes,
                    duration_s=_elapsed_seconds(),
                ),
                last_endpoint=day_last_endpoint or "unknown",
            )
            writer.abort(
                RunError(
                    code="exception",
                    msg=str(exc),
                    last_endpoint=day_last_endpoint,
                )
            )
            run_aborted = True
            raise

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

        writer.end_day(
            day,
            status="done",
            stats=DayStats(
                endpoints_ok=len(successes),
                endpoints_fail=len(failures),
                endpoints_skipped=day_skipped_count,
                bytes_payload=day_payload_bytes,
                duration_s=_elapsed_seconds(),
            ),
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
    run_failed = rate_limit_exc is not None or run_aborted or total_failures > 0
    exit_code = 0 if not run_failed else 1

    if rate_limit_exc is None and not run_aborted:
        writer.finish()

    if rate_limit_exc is not None:
        _log_cli_event(
            logging.ERROR,
            "garmin.cli.run.failed",
            run_id,
            totals={
                "days": len(summary),
                "successes": total_successes,
                "failures": total_failures,
                "retry_outcomes": retry_totals,
            },
            exit_code=1,
            reason="rate_limit",
            wait_minutes=rate_limit_exc.wait_minutes,
        )
    else:
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

    manifest_path = getattr(writer, "_path", None)
    totals_summary: dict[str, Any] = {}
    manifest_snapshot = getattr(writer, "_data", None)
    if manifest_snapshot is None and manifest_path is not None:
        try:
            manifest_snapshot = RunMetaReader(output_root, run_id).load()
        except FileNotFoundError:
            manifest_snapshot = {}
    manifest_snapshot = manifest_snapshot or {}
    if isinstance(manifest_snapshot, dict):
        totals_summary = manifest_snapshot.get("totals", {})
    manifest_display = str(Path(manifest_path).resolve()) if manifest_path else ""
    print(f"Run manifest: {manifest_display}", flush=True)
    if hasattr(json, "dumps"):
        totals_text = json.dumps(totals_summary, sort_keys=True)
    else:  # pragma: no cover - test shim
        buffer = io.StringIO()
        json.dump(totals_summary, buffer, sort_keys=True)
        totals_text = buffer.getvalue()
    print(f"Run totals: {totals_text}", flush=True)

    final_exit = exit_code
    if isinstance(manifest_snapshot, dict):
        aborted = bool(manifest_snapshot.get("aborted"))
        endpoint_totals = totals_summary.get("endpoints", {}) if isinstance(totals_summary, dict) else {}
        has_errors = endpoint_totals.get("error", 0) > 0
        if aborted or has_errors:
            final_exit = 1
        elif totals_summary:
            final_exit = 0

    if rate_limit_exc is not None:
        wait_message = (
            f"Rate limit encountered after {summary[-1]['date']}. "
            f"Wait at least {rate_limit_exc.wait_minutes} minutes before retrying."
        )
        print(wait_message, file=sys.stderr)
        return 1

    return final_exit


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
