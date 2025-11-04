"""CLI entrypoint for the Withings L0 ingest."""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Sequence

from agentlab.metadata import RunMetaReader
from agentlab.utils.withings_tokens import WithingsTokenStore
from agentlab.withings import WithingsFetcher, WithingsTransport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch Withings L0 measures data.")
    parser.add_argument(
        "--start-date",
        required=True,
        help="Start date inclusive (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        help="End date inclusive (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--out-root",
        type=Path,
        default=Path("out"),
        help="Root directory for L0 outputs (default: ./out).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Reserved for parity with Garmin CLI; currently writes outputs regardless.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip day folders that already contain successful payloads.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from the first non-done day recorded in the manifest.",
    )
    parser.add_argument(
        "--request-delay",
        type=float,
        default=1.0,
        help="Seconds to wait between Withings API requests (default: 1.0).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Emit per-day Withings fetch progress to stderr (mirrors Garmin debug output).",
    )
    parser.add_argument(
        "--auth-file",
        type=Path,
        default=Path("secrets/withings_tokens.json"),
        help="Path to the OAuth token bundle (default: secrets/withings_tokens.json).",
    )
    parser.add_argument(
        "--transport",
        default=None,
        help=(
            "Dotted import path to a callable returning a Withings transport. "
            "Defaults to WITHINGS_TRANSPORT_MODULE env var."
        ),
    )
    return parser


def _parse_date(raw: str, label: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise SystemExit(f"{label} must be YYYY-MM-DD (received {raw!r})") from exc


def _load_transport(args: argparse.Namespace) -> object:
    if args.transport:
        module_path, _, attr = args.transport.partition(":")
        if not attr:
            raise SystemExit("--transport must be 'module:factory'")
        module = importlib.import_module(module_path)
        factory = getattr(module, attr, None)
        if factory is None:
            raise SystemExit(f"Transport factory {args.transport!r} not found.")
        return factory()

    module_name = os.getenv("WITHINGS_TRANSPORT_MODULE")
    factory_name = os.getenv("WITHINGS_TRANSPORT_FACTORY", "create_transport")
    if module_name:
        module = importlib.import_module(module_name)
        factory = getattr(module, factory_name, None)
        if factory is None:
            raise SystemExit(
                f"{module_name} does not expose {factory_name}; cannot construct transport."
            )
        return factory()

    try:
        store = WithingsTokenStore(args.auth_file)
        return WithingsTransport(token_store=store, request_delay=args.request_delay)
    except FileNotFoundError as exc:
        raise SystemExit(f"Withings auth file not found: {exc}") from exc
    except ValueError as exc:
        raise SystemExit(f"Invalid Withings auth file: {exc}") from exc
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    start = _parse_date(args.start_date, "--start-date")
    end = _parse_date(args.end_date, "--end-date")
    if end < start:
        raise SystemExit("--end-date cannot be earlier than --start-date")

    transport = _load_transport(args)
    fetcher = WithingsFetcher(transport=transport)
    fetcher.fetch_date_range(
        out_root=args.out_root,
        start_date=start,
        end_date=end,
        skip_existing=args.skip_existing,
        dry_run=args.dry_run,
        resume=args.resume,
        debug=args.debug,
    )

    manifest_path = fetcher.last_manifest_path
    manifest = fetcher.last_manifest
    if manifest_path is None or manifest is None:
        run_id = fetcher.last_run_id
        if run_id:
            try:
                reader = RunMetaReader(args.out_root, run_id)
                manifest = reader.load()
                manifest_path = reader._path  # type: ignore[attr-defined]
            except FileNotFoundError:
                manifest = manifest or {}
        else:
            manifest = manifest or {}

    totals = (manifest or {}).get("totals", {})
    aborted = bool((manifest or {}).get("aborted"))

    manifest_display = str(Path(manifest_path).resolve()) if manifest_path else ""
    print(f"Run manifest: {manifest_display}")
    print(f"Run totals: {json.dumps(totals, sort_keys=True)}")

    return 1 if aborted else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
