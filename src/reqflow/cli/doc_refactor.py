"""Moved from src/agentlab/cli/doc_refactor.py on 2025-10-27.

CLI wrapper for documentation/refactor alignment workflows.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Sequence

from reqflow.catalog import catalog_root

from . import review as review_cli
from . import start as start_cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run catalog review followed by collision/overlap analysis for documentation or refactor changes."
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
        help="Requirement identifier to analyse for potential overlaps.",
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
        default=0.50,
        help="Similarity threshold (0-1) for related functional requirements (default: 0.50).",
    )
    parser.add_argument(
        "--non-functional-threshold",
        type=float,
        default=0.40,
        help="Similarity threshold (0-1) for non-functional overlap suggestions (default: 0.40).",
    )
    parser.add_argument(
        "--acknowledge",
        action="store_true",
        help="Confirm that overlaps have been reviewed when collisions or related entries are detected.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Refresh cached catalog digests before running review/batch analysis.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        catalog_dir = args.catalog_root if args.catalog_root else catalog_root(Path.cwd())
    except FileNotFoundError as exc:  # pragma: no cover - defensive guard
        parser.error(str(exc))
        return 2

    review_args = ["--catalog-root", str(catalog_dir)]
    if args.refresh_cache:
        review_args.append("--refresh-cache")
    review_exit = review_cli.main(review_args)
    if review_exit != 0:
        return review_exit

    functional_path = catalog_dir / "functional.md"
    if not functional_path.exists():
        parser.error("functional catalog not found; run setup first")
        return 2

    try:
        todo_entries, done_entries = start_cli._load_functional_sections(functional_path)  # type: ignore[attr-defined]
    except ValueError as exc:
        parser.error(str(exc))
        return 2

    target = _find_entry(todo_entries, done_entries, args.requirement)
    if target is None:
        parser.error(f"Requirement {args.requirement} not found in functional catalog (todo/done).")
        return 2

    collisions = start_cli._find_collisions(  # type: ignore[attr-defined]
        target,
        done_entries,
        args.collision_threshold,
    )

    other_entries = [
        entry for entry in todo_entries + done_entries if entry.req_id != target.req_id
    ]
    related = start_cli._find_related_requirements(  # type: ignore[attr-defined]
        target,
        other_entries,
        excluded_ids={item.requirement_id for item in collisions},
        threshold=args.related_threshold,
    )

    non_functional_path = catalog_dir / "non-functional.md"
    nf_entries: list[start_cli.Collision] = []  # type: ignore[attr-defined]
    if non_functional_path.exists():
        try:
            nf_todo, nf_done = start_cli._load_functional_sections(non_functional_path)  # type: ignore[attr-defined]
        except ValueError as exc:
            parser.error(str(exc))
            return 2
        nf_entries = start_cli._find_non_functional_overlaps(  # type: ignore[attr-defined]
            target,
            nf_todo + nf_done,
            threshold=args.non_functional_threshold,
        )

    print(f"Documentation/Refactor alignment for {args.requirement}")
    print("")
    _print_section("Collisions", collisions)
    _print_section("Related functional requirements", related)
    _print_section("Non-functional overlaps", nf_entries)

    if (collisions or related or nf_entries) and not args.acknowledge:
        print(
            "\nOverlaps detected. Review the suggestions above and re-run with --acknowledge "
            "once requirement adjustments are captured."
        )
        return 1

    if not (collisions or related or nf_entries):
        print("\nNo overlaps detected; documentation/refactor alignment looks clear.")
    else:
        print("\nOverlaps acknowledged; proceed with documentation/refactor updates.")

    return 0


def _find_entry(
    todo_entries: Sequence[start_cli.RequirementEntry],  # type: ignore[attr-defined]
    done_entries: Sequence[start_cli.RequirementEntry],  # type: ignore[attr-defined]
    req_id: str,
) -> start_cli.RequirementEntry | None:  # type: ignore[attr-defined]
    for entry in todo_entries:
        if entry.req_id == req_id:
            return entry
    for entry in done_entries:
        if entry.req_id == req_id:
            return entry
    return None


def _print_section(
    title: str,
    entries: Iterable[start_cli.Collision],  # type: ignore[attr-defined]
) -> None:
    entries = list(entries)
    print(f"{title}:")
    if not entries:
        print("  None detected")
        return
    for item in entries:
        summary = item.title or "untitled"
        print(f"  - {item.requirement_id} ({summary}) similarity={item.similarity:.2f}")
