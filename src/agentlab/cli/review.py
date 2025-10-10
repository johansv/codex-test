"""CLI for validating requirement catalogs against the repository."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

from reqflow.catalog import catalog_root

from . import start as start_cli

_ALLOWED_STATUSES = {"backlog", "todo", "doing", "done", "rejected", "superseded"}
_PRIMARY_STATUSES = {"todo", "doing"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate functional and non-functional requirement catalogs for consistency.",
    )
    parser.add_argument(
        "--catalog-root",
        type=Path,
        default=None,
        help="Override auto-detection of the docs/requirements directory.",
    )
    parser.add_argument(
        "--related-threshold",
        type=float,
        default=0.65,
        help="Similarity threshold (0-1) for highlighting potentially overlapping requirements.",
    )
    parser.add_argument(
        "--non-functional-threshold",
        type=float,
        default=0.65,
        help="Similarity threshold (0-1) for non-functional overlaps.",
    )
    parser.add_argument(
        "--no-warn-overlaps",
        action="store_true",
        help="Suppress overlap warnings (useful for focused drift checks).",
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
    non_functional_path = catalog_dir / "non-functional.md"
    issues: list[str] = []
    warnings: list[str] = []

    if not functional_path.exists():
        issues.append("functional catalog not found; run setup first")
        return _emit_results(issues, warnings)

    try:
        func_todo, func_done = start_cli._load_functional_sections(functional_path)  # type: ignore[attr-defined]
    except ValueError as exc:
        issues.append(str(exc))
        return _emit_results(issues, warnings)

    _validate_entries(
        func_todo + func_done,
        repo_root=catalog_dir.parent,
        catalog_name="functional",
        issues=issues,
        warnings=warnings,
    )
    _check_primary_doing(func_todo, catalog_name="functional", issues=issues)
    if not args.no_warn_overlaps:
        warnings.extend(
            _find_overlap_warnings(
                func_todo + func_done,
                threshold=args.related_threshold,
                catalog_name="functional",
            )
        )

    if non_functional_path.exists():
        try:
            nf_todo, nf_done = start_cli._load_functional_sections(non_functional_path)  # type: ignore[attr-defined]
        except ValueError as exc:
            issues.append(str(exc))
            return _emit_results(issues, warnings)

        _validate_entries(
            nf_todo + nf_done,
            repo_root=catalog_dir.parent,
            catalog_name="non-functional",
            issues=issues,
            warnings=warnings,
            is_non_functional=True,
        )
        _check_primary_doing(nf_todo, catalog_name="non-functional", issues=issues)
        if not args.no_warn_overlaps:
            warnings.extend(
                _find_overlap_warnings(
                    nf_todo + nf_done,
                    threshold=args.non_functional_threshold,
                    catalog_name="non-functional",
                )
            )
    else:
        warnings.append("non-functional catalog not found; skipped non-functional validation")

    return _emit_results(issues, warnings)


def _emit_results(issues: Iterable[str], warnings: Iterable[str]) -> int:
    issues = list(issues)
    warnings = list(warnings)

    if issues:
        print("Review failed with the following issues:", file=sys.stderr)
        for item in issues:
            print(f"- {item}", file=sys.stderr)
    else:
        print("No blocking issues detected.")

    if warnings:
        target = sys.stderr if issues else sys.stdout
        print("Warnings:", file=target)
        for item in warnings:
            print(f"- {item}", file=target)

    return 1 if issues else 0


def _validate_entries(
    entries: Iterable[start_cli.RequirementEntry],  # type: ignore[attr-defined]
    *,
    repo_root: Path,
    catalog_name: str,
    issues: list[str],
    warnings: list[str],
    is_non_functional: bool = False,
) -> None:
    for entry in entries:
        status = (entry.status or "").lower()
        if status not in _ALLOWED_STATUSES:
            issues.append(
                f"{catalog_name} requirement {entry.req_id} has invalid status '{entry.status}'."
            )
        elif status in {"todo", "backlog"} and "pending" in "".join(entry.lines).lower():
            warnings.append(
                f"{catalog_name} requirement {entry.req_id} remains {status}; confirm prioritisation."
            )

        trace_line = _extract_trace(entry.lines)
        if trace_line:
            trace_map = _parse_trace(trace_line)
            test_key = "tests" if not is_non_functional else "tests"
            script_key = "scripts" if is_non_functional else None
            monitor_key = "monitors" if is_non_functional else None

            for key in (test_key, script_key, monitor_key):
                if not key:
                    continue
                value = trace_map.get(key, "none").strip()
                if value.lower() == "none":
                    continue
                for part in value.split(";"):
                    path = repo_root / part.strip()
                    if not path.exists():
                        issues.append(
                            f"{catalog_name} requirement {entry.req_id} references missing {key} file: {part.strip()}"
                        )
        else:
            warnings.append(
                f"{catalog_name} requirement {entry.req_id} is missing a Trace line."
            )


def _has_amends(lines: Iterable[str]) -> bool:
    for line in lines:
        if line.strip().startswith("- Amends:"):
            return True
    return False



def _check_primary_doing(
    todo_entries: Iterable[start_cli.RequirementEntry],  # type: ignore[attr-defined]
    *,
    catalog_name: str,
    issues: list[str],
) -> None:
    primaries = [
        entry.req_id
        for entry in todo_entries
        if (entry.status or "").lower() == "doing"
        and not _has_amends(entry.lines)
    ]
    if len(primaries) > 1:
        issues.append(
            f"{catalog_name} catalog has multiple primary requirements in doing: {', '.join(primaries)}"
        )


def _find_overlap_warnings(
    entries: Iterable[start_cli.RequirementEntry],  # type: ignore[attr-defined]
    *,
    threshold: float,
    catalog_name: str,
) -> list[str]:
    entries = list(entries)
    warnings: list[str] = []
    for idx, entry in enumerate(entries):
        others = entries[:idx] + entries[idx + 1 :]
        overlaps = start_cli._find_related_requirements(  # type: ignore[attr-defined]
            entry,
            others,
            excluded_ids={entry.req_id},
            threshold=threshold,
            limit=3,
        )
        for hit in overlaps:
            warnings.append(
                f"Potential overlap in {catalog_name}: {entry.req_id} vs {hit.requirement_id} (similarity {hit.similarity:.2f})."
            )
    return warnings


def _extract_trace(lines: Iterable[str]) -> str | None:
    for line in lines:
        if line.strip().startswith("- Trace:"):
            return line.strip()
    return None


def _parse_trace(trace_line: str) -> dict[str, str]:
    _, _, remainder = trace_line.partition(":")
    result: dict[str, str] = {}
    for part in remainder.split(","):
        item = part.strip()
        if not item:
            continue
        key, _, value = item.partition(" ")
        result[key] = value.strip()
    return result


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
