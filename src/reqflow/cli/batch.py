"""Moved from src/agentlab/cli/batch.py on 2025-10-27.

CLI for orchestrating requirement preparation workflows.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from reqflow.catalog import (
    append_log_entry,
    bulk_reopen_functional_requirements,
    catalog_root,
    reopen_non_functional_requirement_for_amendment,
)

from . import start as start_cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run collision detection, related requirement discovery, and optional "
            "bulk reopen flows for a functional requirement."
        ),
    )
    parser.add_argument(
        "--catalog-root",
        type=Path,
        default=None,
        help="Override auto-detection of the docs/requirements directory.",
    )
    parser.add_argument(
        "--requirement",
        required=True,
        help="Functional requirement identifier to analyse.",
    )
    parser.add_argument(
        "--author",
        default="codex",
        help="Author recorded in the requirements log (default: codex).",
    )
    parser.add_argument(
        "--reference",
        default="batch",
        help="Reference captured in the change log (default: batch).",
    )
    parser.add_argument(
        "--summary",
        default=None,
        help="Custom change-log summary when auto-reopening amendments.",
    )
    parser.add_argument(
        "--collision-threshold",
        type=float,
        default=0.45,
        help="Similarity threshold (0-1) for collision detection (default: 0.45).",
    )
    parser.add_argument(
        "--related-threshold",
        type=float,
        default=0.35,
        help="Similarity threshold (0-1) for related requirement suggestions (default: 0.35).",
    )
    parser.add_argument(
        "--non-functional-threshold",
        type=float,
        default=0.4,
        help="Similarity/token overlap threshold for non-functional suggestions (default: 0.4).",
    )
    parser.add_argument(
        "--auto-reopen-collisions",
        action="store_true",
        help="Automatically reopen detected collisions as amendments.",
    )
    parser.add_argument(
        "--auto-reopen-related",
        action="store_true",
        help="Automatically reopen related functional requirements as amendments.",
    )
    parser.add_argument(
        "--auto-reopen-non-functional",
        action="store_true",
        help="Automatically reopen suggested non-functional requirements as amendments.",
    )
    parser.add_argument(
        "--allow-doing",
        action="store_true",
        help="Allow already in-progress amendments to be refreshed when auto-reopening.",
    )
    parser.add_argument(
        "--reopen-reason",
        default="Batch workflow triggered reopen",
        help="Reason recorded for amendments when auto-reopening (default: Batch workflow triggered reopen).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
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
        return 2

    functional_path = catalog_dir / "functional.md"
    if not functional_path.exists():
        parser.error("functional catalog not found; run setup first")
        return 2

    non_functional_path = catalog_dir / "non-functional.md"
    log_path = catalog_dir / "log.md"
    if not log_path.exists():
        parser.error("log.md not found in catalog directory")
        return 2

    try:
        todo_entries, done_entries = start_cli._load_functional_sections(  # type: ignore[attr-defined]
            functional_path
        )
    except ValueError as exc:
        parser.error(str(exc))
        return 2

    target = start_cli._find_entry(todo_entries, args.requirement)
    if target is None:
        parser.error(f"Requirement {args.requirement} not found in todo section")
        return 2

    status = (target.status or "").lower()
    if status != "todo":
        parser.error(
            f"Requirement {args.requirement} must be todo before batch preparation (current status: {status or 'unknown'})."
        )
        return 2

    collisions = start_cli._find_collisions(  # type: ignore[attr-defined]
        target,
        done_entries,
        args.collision_threshold,
    )
    collision_ids = [item.requirement_id for item in collisions]

    other_entries = [
        entry for entry in todo_entries + done_entries if entry.req_id != args.requirement
    ]
    related_candidates = start_cli._find_related_requirements(  # type: ignore[attr-defined]
        target,
        other_entries,
        excluded_ids=set(collision_ids),
        threshold=args.related_threshold,
    )
    related_ids = [item.requirement_id for item in related_candidates]

    non_functional_candidates: list[start_cli.Collision] = []  # type: ignore[attr-defined]
    non_functional_ids: list[str] = []
    if non_functional_path.exists():
        try:
            nf_todo, nf_done = start_cli._load_functional_sections(  # type: ignore[attr-defined]
                non_functional_path
            )
        except ValueError as exc:
            parser.error(str(exc))
            return 2
        non_functional_candidates = start_cli._find_non_functional_overlaps(  # type: ignore[attr-defined]
            target,
            nf_todo + nf_done,
            threshold=args.non_functional_threshold,
        )
        non_functional_ids = [item.requirement_id for item in non_functional_candidates]

    report_lines = [
        f"Batch preparation for {args.requirement}",
        "",
        "Collisions:",
    ]
    if collisions:
        for item in collisions:
            report_lines.append(
                f"  - {item.requirement_id} ({item.title or 'untitled'}) similarity={item.similarity:.2f}"
            )
    else:
        report_lines.append("  None detected")

    report_lines.append("")
    report_lines.append("Related functional requirements:")
    if related_ids:
        for item in related_candidates:
            report_lines.append(
                f"  - {item.requirement_id} ({item.title or 'untitled'}) similarity={item.similarity:.2f}"
            )
    else:
        report_lines.append("  None detected")

    report_lines.append("")
    report_lines.append("Non-functional overlaps:")
    if non_functional_ids:
        for item in non_functional_candidates:
            report_lines.append(
                f"  - {item.requirement_id} ({item.title or 'untitled'}) similarity={item.similarity:.2f}"
            )
    else:
        report_lines.append("  None detected")

    reopened_collisions: list[str] = []
    reopened_related: list[str] = []
    reopened_non_functional: list[str] = []

    reopen_reason = args.reopen_reason.strip() or "Batch workflow triggered reopen"

    if args.auto_reopen_collisions and collisions:
        reopened_collisions = bulk_reopen_functional_requirements(
            functional_path,
            primary_id=args.requirement,
            amendment_ids=collision_ids,
            reason=reopen_reason,
            allow_doing=args.allow_doing,
        )
    if args.auto_reopen_related and related_ids:
        remaining = [req_id for req_id in related_ids if req_id not in reopened_collisions]
        if remaining:
            reopened_related = bulk_reopen_functional_requirements(
                functional_path,
                primary_id=args.requirement,
                amendment_ids=remaining,
                reason=reopen_reason,
                allow_doing=args.allow_doing,
            )
    if args.auto_reopen_non_functional and non_functional_ids:
        if not non_functional_path.exists():
            parser.error("non-functional catalog not found; cannot reopen suggestions.")
            return 2
        for req_id in non_functional_ids:
            try:
                reopen_non_functional_requirement_for_amendment(
                    non_functional_path,
                    req_id,
                    args.requirement,
                    reason=f"Batch amendment in progress under {args.requirement}: {reopen_reason}",
                )
                reopened_non_functional.append(req_id)
            except ValueError as exc:
                parser.error(str(exc))
                return 2

    if reopened_collisions or reopened_related or reopened_non_functional:
        summary = (
            args.summary
            or (
                "Batch preparation reopened: "
                + ", ".join(
                    filter(
                        None,
                        [
                            ", ".join(reopened_collisions) if reopened_collisions else "",
                            ", ".join(reopened_related) if reopened_related else "",
                            ", ".join(reopened_non_functional)
                            if reopened_non_functional
                            else "",
                        ],
                    )
                )
            )
        )
        append_log_entry(
            log_path,
            req_id=args.requirement,
            change_summary=summary,
            author=args.author,
            reference=args.reference,
        )
        for req_id in reopened_collisions + reopened_related:
            append_log_entry(
                log_path,
                req_id=req_id,
                change_summary=(
                    f"Reopened {req_id} under {args.requirement} from batch workflow"
                ),
                author=args.author,
                reference=args.reference,
            )
        for req_id in reopened_non_functional:
            append_log_entry(
                log_path,
                req_id=req_id,
                change_summary=(
                    f"Reopened {req_id} under {args.requirement} from batch workflow"
                ),
                author=args.author,
                reference=args.reference,
            )

    report_lines.append("")
    report_lines.append("Actions:")
    report_lines.append(
        "  Auto-reopened collisions: "
        + (", ".join(reopened_collisions) if reopened_collisions else "none")
    )
    report_lines.append(
        "  Auto-reopened related: "
        + (", ".join(reopened_related) if reopened_related else "none")
    )
    report_lines.append(
        "  Auto-reopened non-functional: "
        + (", ".join(reopened_non_functional) if reopened_non_functional else "none")
    )

    print("\n".join(report_lines))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
