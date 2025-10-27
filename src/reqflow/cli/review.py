"""Moved from src/agentlab/cli/review.py on 2025-10-27.

CLI for validating requirement catalogs against the repository.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

from reqflow.catalog import (
    _format_requirement_section,
    _set_amends,
    _set_reason,
    _set_status,
    _update_non_functional_trace,
    _update_status_summary,
    _update_trace,
    catalog_root,
)
from reqflow.catalog_cache import catalog_cache

from . import start as start_cli

_ALLOWED_STATUSES = {"backlog", "todo", "doing", "done", "rejected", "superseded"}
_PRIMARY_STATUSES = {"todo", "doing"}
_PRUNE_REASON = "Awaiting reassessment after drift detection"


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
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Move drifted done requirements back to todo with a reassessment reason.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Ignore cached catalog digests and reload catalogs from disk.",
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
    issue_records: list[dict[str, str]] = []
    warnings: list[str] = []
    drift_candidates: list[dict[str, str]] = []

    if not functional_path.exists():
        issue_records.append(
            {
                "message": "functional catalog not found; run setup first",
                "catalog": "functional",
                "req_id": "",
                "type": "missing_catalog",
            }
        )
        return _emit_results(issue_records, warnings)

    try:
        func_todo, func_done = _load_sections(
            functional_path,
            refresh=args.refresh_cache,
        )
    except ValueError as exc:
        issue_records.append(
            {
                "message": str(exc),
                "catalog": "functional",
                "req_id": "",
                "type": "parse_error",
            }
        )
        return _emit_results(issue_records, warnings)

    _validate_entries(
        func_todo + func_done,
        repo_root=catalog_dir.parent,
        catalog_name="functional",
        issue_records=issue_records,
        warnings=warnings,
        drift_candidates=drift_candidates,
    )
    _check_primary_doing(func_todo, catalog_name="functional", issue_records=issue_records)
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
            nf_todo, nf_done = _load_sections(
                non_functional_path,
                refresh=args.refresh_cache,
            )
        except ValueError as exc:
            issue_records.append(
                {
                    "message": str(exc),
                    "catalog": "non-functional",
                    "req_id": "",
                    "type": "parse_error",
                }
            )
            return _emit_results(issue_records, warnings)

        _validate_entries(
            nf_todo + nf_done,
            repo_root=catalog_dir.parent,
            catalog_name="non-functional",
            issue_records=issue_records,
            warnings=warnings,
            is_non_functional=True,
            drift_candidates=drift_candidates,
        )
        _check_primary_doing(nf_todo, catalog_name="non-functional", issue_records=issue_records)
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

    if args.prune and drift_candidates:
        pruned_messages = _prune_drift_candidates(
            catalog_dir,
            drift_candidates,
        )
        if pruned_messages:
            warnings.extend(pruned_messages)
            pruned_ids = {
                (item["catalog"], item["req_id"])
                for item in drift_candidates
            }
            issue_records = [
                record
                for record in issue_records
                if not (
                    record.get("type") == "missing_artifact"
                    and (record.get("catalog"), record.get("req_id")) in pruned_ids
                )
            ]

    return _emit_results(issue_records, warnings)


def _emit_results(issue_records: Iterable[dict[str, str]], warnings: Iterable[str]) -> int:
    issue_records = list(issue_records)
    issues = [record["message"] for record in issue_records]
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


def _load_sections(
    path: Path,
    *,
    refresh: bool,
) -> tuple[list[start_cli.RequirementEntry], list[start_cli.RequirementEntry]]:  # type: ignore[attr-defined]
    return catalog_cache.parse(
        path,
        "sections",
        parser=start_cli._parse_catalog_sections,  # type: ignore[attr-defined]
        refresh=refresh,
    )


def _validate_entries(
    entries: Iterable[start_cli.RequirementEntry],  # type: ignore[attr-defined]
    *,
    repo_root: Path,
    catalog_name: str,
    issue_records: list[dict[str, str]],
    warnings: list[str],
    is_non_functional: bool = False,
    drift_candidates: list[dict[str, str]] | None = None,
) -> None:
    for entry in entries:
        status = (entry.status or "").lower()
        if status not in _ALLOWED_STATUSES:
            issue_records.append(
                {
                    "message": (
                        f"{catalog_name} requirement {entry.req_id} has invalid status '{entry.status}'."
                    ),
                    "catalog": catalog_name,
                    "req_id": entry.req_id,
                    "type": "invalid_status",
                }
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
                        issue_records.append(
                            {
                                "message": (
                                    f"{catalog_name} requirement {entry.req_id} references missing {key} file: {part.strip()}"
                                ),
                                "catalog": catalog_name,
                                "req_id": entry.req_id,
                                "type": "missing_artifact",
                                "artifact": part.strip(),
                            }
                        )
                        if drift_candidates is not None and status == "done":
                            drift_candidates.append(
                                {
                                    "catalog": catalog_name,
                                    "req_id": entry.req_id,
                                    "artifact": part.strip(),
                                    "is_non_functional": "true" if is_non_functional else "false",
                                }
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
    issue_records: list[dict[str, str]],
) -> None:
    primaries = [
        entry.req_id
        for entry in todo_entries
        if (entry.status or "").lower() == "doing"
        and not _has_amends(entry.lines)
    ]
    if len(primaries) > 1:
        issue_records.append(
            {
                "message": (
                    f"{catalog_name} catalog has multiple primary requirements in doing: {', '.join(primaries)}"
                ),
                "catalog": catalog_name,
                "req_id": primaries[0],
                "type": "multiple_doing",
            }
        )


def _split_section(section: str) -> list[list[str]]:
    lines = section.strip("\\n").splitlines()
    entries: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.strip():
            current.append(line)
        elif current:
            entries.append(current)
            current = []
    if current:
        entries.append(current)
    return entries
def _format_section(entries: list[list[str]]) -> str:
    if not entries:
        return "\n\n"
    body = "\n\n".join("\n".join(entry) for entry in entries)
    return f"\n\n{body}\n\n"


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


def _prune_drift_candidates(
    catalog_dir: Path,
    candidates: list[dict[str, str]],
) -> list[str]:
    pruned_notes: list[str] = []
    seen: set[tuple[str, str]] = set()
    for record in candidates:
        key = (record["catalog"], record["req_id"])
        if key in seen:
            continue
        seen.add(key)
        is_non_functional = record["catalog"] == "non-functional"
        catalog_path = catalog_dir / (
            "non-functional.md" if is_non_functional else "functional.md"
        )
        if not catalog_path.exists():
            continue
        try:
            _prune_requirement(
                catalog_path,
                record["req_id"],
                reason=_PRUNE_REASON,
                is_non_functional=is_non_functional,
            )
            pruned_notes.append(
                f"Pruned {record['catalog']} requirement {record['req_id']} due to missing artifacts."
            )
        except ValueError as exc:
            pruned_notes.append(str(exc))
    return pruned_notes


def _prune_requirement(
    path: Path,
    req_id: str,
    *,
    reason: str,
    is_non_functional: bool,
) -> None:
    contents = path.read_text(encoding="utf-8")

    todo_marker = start_cli._TODO_MARKER  # type: ignore[attr-defined]
    done_marker = start_cli._DONE_MARKER  # type: ignore[attr-defined]
    retired_marker = start_cli._RETIRED_MARKER  # type: ignore[attr-defined]

    before_todo, todo_header, remainder = contents.partition(todo_marker)
    if not todo_header:
        raise ValueError("Catalog missing todo section")

    todo_section, done_header, remainder = remainder.partition(done_marker)
    if not done_header:
        raise ValueError("Catalog missing done section")

    done_section, retired_header, suffix = remainder.partition(retired_marker)
    if not retired_header:
        raise ValueError("Catalog missing retired section")

    todo_entries = _split_section(todo_section)
    done_entries = _split_section(done_section)

    entry_index = next(
        (
            idx
            for idx, entry in enumerate(done_entries)
            if entry and entry[0].strip().startswith(f"### {req_id}")
        ),
        None,
    )

    if entry_index is None:
        raise ValueError(f"Requirement {req_id} not found in done section for pruning")

    entry_lines = done_entries.pop(entry_index)
    entry_lines = _set_status(entry_lines, "todo")
    entry_lines = _set_amends(entry_lines, None)
    entry_lines = _set_reason(entry_lines, reason)
    if is_non_functional:
        entry_lines = _update_non_functional_trace(
            entry_lines,
            tests_value="none",
            scripts_value="none",
            monitors_value="none",
            default_prompts="none",
        )
    else:
        entry_lines = _update_trace(
            entry_lines,
            tests_value="none",
            commits_value="none",
            default_prompts="none",
        )

    todo_entries.insert(0, entry_lines)

    updated_contents = (
        before_todo
        + todo_header
        + _format_requirement_section(todo_entries)
        + done_header
        + _format_requirement_section(done_entries)
        + retired_header
        + suffix
    )
    updated_contents = _update_status_summary(updated_contents)
    path.write_text(updated_contents, encoding="utf-8")
    catalog_cache.invalidate(path)

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
