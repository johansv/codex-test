"""CLI for streaming scoped requirement slices."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Sequence

from reqflow.catalog_cache import catalog_cache

from . import start as start_cli

_SUMMARY_LIMIT = 250
_STATUS_ORDER = ("backlog", "todo", "doing", "done", "rejected", "superseded")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stream selected requirement entries while summarising the remainder.",
    )
    parser.add_argument(
        "--catalog-root",
        type=Path,
        default=None,
        help="Override auto-detection of the docs/requirements directory.",
    )
    parser.add_argument(
        "--catalog",
        choices=("functional", "non-functional", "both"),
        default="both",
        help="Catalog to query (default: both).",
    )
    parser.add_argument(
        "--id",
        action="append",
        dest="ids",
        default=[],
        help="Requirement identifier to include; repeatable.",
    )
    parser.add_argument(
        "--tag",
        action="append",
        dest="tags",
        default=[],
        help="Tag to include (matches '- Tags:' lines); repeatable.",
    )
    parser.add_argument(
        "--summary-length",
        type=int,
        default=_SUMMARY_LIMIT,
        help="Maximum tokens used for the unrelated summary (default: 250).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.ids and not args.tags:
        parser.error("Provide at least one --id or --tag to scope the results.")

    try:
        catalog_dir = (
            args.catalog_root
            if args.catalog_root is not None
            else start_cli.catalog_root(Path.cwd())  # type: ignore[attr-defined]
        )
    except FileNotFoundError as exc:  # pragma: no cover - defensive guard
        parser.error(str(exc))
        return 2

    functional_matches: list[str] = []
    non_functional_matches: list[str] = []
    functional_summary = ""
    non_functional_summary = ""

    if args.catalog in {"functional", "both"}:
        path = catalog_dir / "functional.md"
        functional_matches, functional_summary = _render_catalog(
            path,
            "Functional Requirements",
            ids=args.ids,
            tags=args.tags,
            summary_limit=args.summary_length,
            is_non_functional=False,
        )

    if args.catalog in {"non-functional", "both"}:
        path = catalog_dir / "non-functional.md"
        non_functional_matches, non_functional_summary = _render_catalog(
            path,
            "Non-Functional Requirements",
            ids=args.ids,
            tags=args.tags,
            summary_limit=args.summary_length,
            is_non_functional=True,
        )

    if not functional_matches and not non_functional_matches:
        print("No matching requirements found.")
    else:
        if functional_matches:
            print("# Functional Requirements\n")
            print("\n\n".join(functional_matches))
        if non_functional_matches:
            print("# Non-Functional Requirements\n")
            print("\n\n".join(non_functional_matches))

    summaries = [item for item in (functional_summary, non_functional_summary) if item]
    if summaries:
        print("\n# Summary\n")
        print("\n\n".join(summaries))

    return 0


def _render_catalog(
    path: Path,
    heading: str,
    *,
    ids: list[str],
    tags: list[str],
    summary_limit: int,
    is_non_functional: bool,
) -> tuple[list[str], str]:
    if not path.exists():
        return [], f"{heading}: catalog not found."

    sections = catalog_cache.parse(
        path,
        "sections",
        parser=start_cli._parse_catalog_sections,  # type: ignore[attr-defined]
    )
    todo_entries, done_entries = sections
    all_entries = todo_entries + done_entries

    lower_ids = {value.strip().lower() for value in ids if value and value.strip()}
    lower_tags = {value.strip().lower() for value in tags if value and value.strip()}

    matched_ids: set[str] = set()
    matched_entries: list[start_cli.RequirementEntry] = []  # type: ignore[attr-defined]
    amendments_to_include: set[str] = set()

    for entry in all_entries:
        if entry.req_id:
            normalized_id = entry.req_id.lower()
            entry_tags = _extract_tags(entry.lines)
            has_id = normalized_id in lower_ids if lower_ids else False
            has_tag = bool(lower_tags & entry_tags) if lower_tags else False
            if has_id or has_tag:
                matched_entries.append(entry)
                matched_ids.add(entry.req_id)
                amendment_target = _extract_amends(entry.lines)
                if amendment_target:
                    amendments_to_include.add(amendment_target)

    if matched_ids:
        for entry in all_entries:
            if entry in matched_entries:
                continue
            amends = _extract_amends(entry.lines)
            if amends and amends in matched_ids:
                matched_entries.append(entry)

    rendered_matches = ["\n".join(entry.lines) for entry in matched_entries]
    summary = _summarise_catalog(
        heading,
        all_entries,
        matched_entries,
        summary_limit,
    )
    return rendered_matches, summary


def _extract_tags(lines: Iterable[str]) -> set[str]:
    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith("- tags:"):
            _, _, remainder = stripped.partition(":")
            return {item.strip().lower() for item in remainder.split(",") if item.strip()}
    return set()


def _extract_amends(lines: Iterable[str]) -> str | None:
    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith("- amends:"):
            _, _, remainder = stripped.partition(":")
            return remainder.strip()
    return None


def _summarise_catalog(
    heading: str,
    all_entries: Sequence[start_cli.RequirementEntry],  # type: ignore[attr-defined]
    matched_entries: Sequence[start_cli.RequirementEntry],  # type: ignore[attr-defined]
    summary_limit: int,
) -> str:
    total = len(all_entries)
    matched = len(matched_entries)
    status_counts: dict[str, int] = {}
    for entry in all_entries:
        status = (entry.status or "unknown").lower()
        status_counts[status] = status_counts.get(status, 0) + 1

    ordered_counts = [
        f"{status}={status_counts[status]}"
        for status in _STATUS_ORDER
        if status in status_counts
    ]
    other = max(total - matched, 0)
    summary = (
        f"{heading}: {matched} matched, {other} other entries. "
        f"Status counts: {', '.join(ordered_counts) if ordered_counts else 'none'}."
    )
    tokens = summary.split()
    if len(tokens) > summary_limit:
        summary = " ".join(tokens[:summary_limit]) + "..."
    return summary


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
