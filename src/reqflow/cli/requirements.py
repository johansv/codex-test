"""Moved from src/agentlab/cli/requirements.py on 2025-10-27.

CLI helpers for maintaining requirement catalogs.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from reqflow.catalog import (
    FunctionalRequirement,
    NonFunctionalRequirement,
    append_functional_requirement,
    append_log_entry,
    append_non_functional_requirement,
    catalog_root,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Add functional or non-functional requirements to the catalog",
    )
    parser.add_argument(
        "--catalog-root",
        type=Path,
        default=None,
        help="Override the docs/requirements directory (defaults to auto-detect)",
    )
    parser.add_argument(
        "--author",
        default="codex",
        help="Name used for the change log entry (default: codex)",
    )
    parser.add_argument(
        "--reference",
        default="prompt",
        help="Ticket, prompt, or link recorded in the change log",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    functional = subparsers.add_parser(
        "functional", help="Capture a functional requirement entry"
    )
    functional.add_argument("--title", required=True)
    functional.add_argument("--owner", required=True)
    functional.add_argument("--narrative", required=True)
    functional.add_argument(
        "--reason",
        default="pending",
        help="Reason associated with the current status (default: pending)",
    )
    functional.add_argument(
        "--priority",
        choices=["low", "medium", "high"],
        default="medium",
        help="Priority recorded with the requirement (default: medium)",
    )
    functional.add_argument(
        "--acceptance",
        action="append",
        dest="acceptance",
        required=True,
        help="Acceptance criterion; repeat the flag for multiple items",
    )
    functional.add_argument(
        "--status",
        default="backlog",
        help="Lifecycle status recorded with the requirement",
    )
    functional.add_argument("--trace-prompts", default="none")
    functional.add_argument("--trace-tests", default="none")
    functional.add_argument("--trace-commits", default="none")
    functional.add_argument(
        "--notes",
        default=None,
        help="Optional notes field appended to the entry",
    )
    functional.add_argument(
        "--summary",
        default=None,
        help="Override summary text used in the change log",
    )

    non_functional = subparsers.add_parser(
        "non-functional", help="Capture a non-functional requirement entry"
    )
    non_functional.add_argument("--title", required=True)
    non_functional.add_argument("--owner", required=True)
    non_functional.add_argument(
        "--priority",
        choices=["low", "medium", "high"],
        default="medium",
        help="Priority recorded with the requirement (default: medium)",
    )
    non_functional.add_argument(
        "--reason",
        default="pending",
        help="Reason associated with the current status (default: pending)",
    )
    non_functional.add_argument(
        "--category",
        required=True,
        help="Requirement category: performance, reliability, security, etc.",
    )
    non_functional.add_argument(
        "--description",
        required=True,
        help="Constraint statement or quality objective",
    )
    non_functional.add_argument(
        "--measurement",
        required=True,
        help="How the requirement is validated or monitored",
    )
    non_functional.add_argument(
        "--status",
        default="backlog",
        help="Lifecycle status recorded with the requirement",
    )
    non_functional.add_argument("--trace-prompts", default="none")
    non_functional.add_argument("--trace-tests", default="none")
    non_functional.add_argument("--trace-scripts", default="none")
    non_functional.add_argument("--trace-monitors", default="none")
    non_functional.add_argument(
        "--notes",
        default=None,
        help="Optional notes field appended to the entry",
    )
    non_functional.add_argument(
        "--summary",
        default=None,
        help="Override summary text used in the change log",
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        catalog_dir = (
            args.catalog_root
            if args.catalog_root is not None
            else catalog_root(Path.cwd())
        )
    except FileNotFoundError as exc:  # pragma: no cover - defensive guard
        parser.error(str(exc))

    log_path = catalog_dir / "log.md"
    if not log_path.exists():
        parser.error("log.md not found in catalog directory")

    if args.command == "functional":
        _handle_functional(args, catalog_dir, log_path, parser)
    elif args.command == "non-functional":
        _handle_non_functional(args, catalog_dir, log_path, parser)
    else:  # pragma: no cover - safety switch
        parser.error(f"Unsupported command: {args.command}")


def _validate_functional_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    narrative = args.narrative.strip()
    lowered = narrative.lower()
    if not ("as " in lowered and " i want " in lowered and (" so that " in lowered or " so i can " in lowered)):
        parser.error("Narrative must include a role, capability, and outcome (e.g., 'As a ..., I want ..., so that ...').")

    acceptance = [item.strip() for item in args.acceptance if item.strip()]
    if not acceptance:
        parser.error("Provide at least one non-empty --acceptance value.")
    args.acceptance = acceptance

    args.trace_prompts = args.trace_prompts.strip()
    args.trace_tests = args.trace_tests.strip()
    args.trace_commits = args.trace_commits.strip()
    traces = [args.trace_prompts, args.trace_tests, args.trace_commits]
    if all(value.lower() == "none" for value in traces):
        parser.error("Provide at least one trace field (--trace-prompts/--trace-tests/--trace-commits) with a non-'none' value.")



def _handle_functional(
    args: argparse.Namespace, catalog_dir: Path, log_path: Path, parser: argparse.ArgumentParser
) -> None:
    _validate_functional_args(args, parser)
    catalog_path = catalog_dir / "functional.md"
    if not catalog_path.exists():
        raise SystemExit("functional catalog not found; run setup first")

    requirement = FunctionalRequirement(
        title=args.title,
        owner=args.owner,
        narrative=args.narrative,
        acceptance_criteria=args.acceptance,
        priority=args.priority,
        status=args.status,
        trace_prompts=args.trace_prompts,
        trace_tests=args.trace_tests,
        trace_commits=args.trace_commits,
        reason=args.reason,
        notes=args.notes,
    )
    req_id = append_functional_requirement(catalog_path, requirement)
    summary = args.summary or f"Added functional requirement {req_id}: {args.title}"
    append_log_entry(log_path, req_id, summary, args.author, args.reference)
    print(f"Recorded {req_id} in {catalog_path}")


def _handle_non_functional(
    args: argparse.Namespace, catalog_dir: Path, log_path: Path, _parser: argparse.ArgumentParser
) -> None:
    catalog_path = catalog_dir / "non-functional.md"
    if not catalog_path.exists():
        raise SystemExit("non-functional catalog not found; run setup first")

    requirement = NonFunctionalRequirement(
        title=args.title,
        owner=args.owner,
        category=args.category,
        description=args.description,
        measurement=args.measurement,
        priority=args.priority,
        status=args.status,
        trace_prompts=args.trace_prompts,
        trace_tests=args.trace_tests,
        trace_scripts=args.trace_scripts,
        trace_monitors=args.trace_monitors,
        reason=args.reason,
        notes=args.notes,
    )
    req_id = append_non_functional_requirement(catalog_path, requirement)
    summary = args.summary or f"Added non-functional requirement {req_id}: {args.title}"
    append_log_entry(log_path, req_id, summary, args.author, args.reference)
    print(f"Recorded {req_id} in {catalog_path}")


if __name__ == "__main__":  # pragma: no cover
    main(sys.argv[1:])
