"""Utilities for managing requirement catalogs."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
import random
import re
import string
from pathlib import Path
from typing import Sequence

__all__ = [
    "FunctionalRequirement",
    "NonFunctionalRequirement",
    "append_functional_requirement",
    "append_non_functional_requirement",
    "append_log_entry",
    "catalog_root",
    "generate_next_id",
    "mark_functional_requirement_done",
    "begin_historic_amendment",
    "bulk_reopen_functional_requirements",
    "reopen_functional_requirement_for_amendment",
    "start_functional_requirement",
]

_TODO_MARKER = "## Todo Requirements"
_DONE_MARKER = "## Done Requirements"
_RETIRED_MARKER = "## Retired Requirements"
_FUNCTIONAL_PREFIX = "REQ-F"
_NON_FUNCTIONAL_PREFIX = "REQ-NF"
_ID_PATTERN = re.compile(r"REQ-[A-Z]+-(?P<number>\d{3})")
_SUMMARY_START = "<!-- STATUS-SUMMARY:START -->"
_SUMMARY_END = "<!-- STATUS-SUMMARY:END -->"


@dataclass(slots=True)
class FunctionalRequirement:
    """Represents a functional requirement entry."""

    title: str
    owner: str
    narrative: str
    acceptance_criteria: list[str]
    priority: str = "medium"
    status: str = "backlog"
    trace_prompts: str = "none"
    trace_tests: str = "none"
    trace_commits: str = "none"
    reason: str = "pending"
    notes: str | None = None
    req_id: str | None = None


@dataclass(slots=True)
class NonFunctionalRequirement:
    """Represents a non-functional requirement entry."""

    title: str
    owner: str
    category: str
    description: str
    measurement: str
    priority: str = "medium"
    status: str = "backlog"
    trace_prompts: str = "none"
    trace_tests: str = "none"
    trace_scripts: str = "none"
    trace_monitors: str = "none"
    reason: str = "pending"
    notes: str | None = None
    req_id: str | None = None


def catalog_root(start: Path | None = None) -> Path:
    """Return the expected root for requirement catalogs."""

    candidate = start or Path(__file__).resolve()
    for parent in candidate.parents:
        docs_dir = parent / "docs" / "requirements"
        if docs_dir.exists():
            return docs_dir
    raise FileNotFoundError("Could not locate docs/requirements directory")


def generate_next_id(contents: str, prefix: str) -> str:
    """Return a unique requirement ID for *prefix* using timestamp+suffix."""

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    base = f"{prefix}-{timestamp}"

    existing = {
        match.group(0)
        for match in re.finditer(rf"{re.escape(base)}-[0-9A-Z]{{2}}", contents)
    }

    for _ in range(5):
        suffix = _random_suffix()
        candidate = f"{base}-{suffix}"
        if candidate not in existing:
            return candidate
    raise RuntimeError("Could not generate unique requirement ID after retries")


def _random_suffix() -> str:
    alphabet = string.digits + string.ascii_uppercase
    value = random.randint(0, 1295)  # 36**2 combinations
    return alphabet[value // 36] + alphabet[value % 36]












def _split_requirement_entries(section: str) -> list[list[str]]:
    lines = section.strip().splitlines()
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


def _format_requirement_section(entries: list[list[str]]) -> str:
    if not entries:
        return "\n\n"
    body = "\n\n".join("\n".join(entry) for entry in entries)
    return f"\n\n{body}\n\n"


def _extract_requirement_id(entry: list[str]) -> str | None:
    for line in entry:
        stripped = line.strip()
        if stripped.startswith("### "):
            heading = stripped[4:]
            req_id, _, _title = heading.partition(":")
            return req_id.strip()
        if stripped.startswith("- ID:"):
            return stripped.split(":", 1)[1].strip()
    return None


def _extract_status(entry: list[str]) -> str | None:
    for line in entry:
        stripped = line.strip()
        if stripped.startswith("- Status:"):
            return stripped.split(":", 1)[1].strip().lower()
    return None


def _set_status(entry: list[str], value: str) -> list[str]:
    updated: list[str] = []
    replaced = False
    for line in entry:
        if line.strip().startswith("- Status:"):
            updated.append(f"- Status: {value}")
            replaced = True
        else:
            updated.append(line)
    if not replaced:
        updated.append(f"- Status: {value}")
    return updated


def _extract_amends(entry: list[str]) -> str | None:
    for line in entry:
        stripped = line.strip()
        if stripped.startswith("- Amends:"):
            return stripped.split(":", 1)[1].strip()
    return None


def _set_amends(entry: list[str], primary_id: str | None) -> list[str]:
    filtered = [line for line in entry if not line.strip().startswith("- Amends:")]
    if primary_id is None:
        return filtered

    result: list[str] = []
    inserted = False
    for line in filtered:
        result.append(line)
        if not inserted and line.strip().startswith("- Status:"):
            result.append(f"- Amends: {primary_id}")
            inserted = True
    if not inserted:
        result.append(f"- Amends: {primary_id}")
    return result


def _set_reason(entry: list[str], value: str) -> list[str]:
    updated: list[str] = []
    replaced = False
    for line in entry:
        if line.strip().startswith("- Reason:"):
            updated.append(f"- Reason: {value}")
            replaced = True
        else:
            updated.append(line)
    if not replaced:
        updated.append(f"- Reason: {value}")
    return updated


def _update_trace(entry: list[str], tests_value: str, commits_value: str, *, default_prompts: str = "none") -> list[str]:
    updated: list[str] = []
    replaced = False
    for line in entry:
        stripped = line.strip()
        if stripped.startswith("- Trace:"):
            remainder = stripped[len("- Trace: "):]
            trace_parts: dict[str, str] = {}
            for part in remainder.split(','):
                item = part.strip()
                if not item:
                    continue
                key, _, value = item.partition(' ')
                if value:
                    trace_parts[key] = value
            prompts_value = trace_parts.get('prompts', default_prompts)
            updated.append(
                f"- Trace: prompts {prompts_value}, tests {tests_value}, commits {commits_value}"
            )
            replaced = True
        else:
            updated.append(line)
    if not replaced:
        updated.append(
            f"- Trace: prompts {default_prompts}, tests {tests_value}, commits {commits_value}"
        )
    return updated



def append_functional_requirement(path: Path, requirement: FunctionalRequirement) -> str:
    """Append *requirement* to the functional catalog located at *path*."""

    text = path.read_text(encoding="utf-8")
    req_id = requirement.req_id or generate_next_id(text, _FUNCTIONAL_PREFIX)

    entry_lines = [
        f"### {req_id}: {requirement.title}",
        f"- Owner: {requirement.owner}",
        f"- Narrative: {requirement.narrative}",
        "- Acceptance Criteria:",
    ]
    for criterion in requirement.acceptance_criteria:
        entry_lines.append(f"  * {criterion}")
    entry_lines.append(f"- Priority: {requirement.priority}")
    entry_lines.extend(
        [
            f"- Status: {requirement.status}",
            f"- Reason: {requirement.reason}",
            f"- Trace: prompts {requirement.trace_prompts}, tests {requirement.trace_tests}, commits {requirement.trace_commits}",
        ]
    )
    if requirement.notes:
        entry_lines.append(f"- Notes: {requirement.notes}")
    entry_lines.append("---")

    updated = _insert_entry(text, "\n".join(entry_lines))
    updated = _update_status_summary(updated)
    path.write_text(updated, encoding="utf-8")
    return req_id








def mark_functional_requirement_done(
    path: Path,
    req_id: str,
    reason: str,
    tests: Sequence[str],
    commits: Sequence[str] | None = None,
) -> list[str]:
    """Mark *req_id* done in the functional catalog located at *path*."""

    if not tests:
        raise ValueError("Provide at least one verifying test path.")

    commits = [value for value in (commits or []) if value]
    contents = path.read_text(encoding="utf-8")

    heading = f"### {req_id}"
    if heading not in contents:
        raise ValueError(f"Requirement {req_id} not found in {path}")

    before_todo, todo_header, remainder = contents.partition(_TODO_MARKER)
    if not todo_header:
        raise ValueError("Functional catalog missing todo section")

    todo_section, done_header, remainder = remainder.partition(_DONE_MARKER)
    if not done_header:
        raise ValueError("Functional catalog missing done section")

    done_section, retired_header, suffix = remainder.partition(_RETIRED_MARKER)
    if not retired_header:
        raise ValueError("Functional catalog missing retired section")

    todo_entries = _split_requirement_entries(todo_section)
    done_entries = _split_requirement_entries(done_section)

    entry_index = next(
        (
            idx
            for idx, entry in enumerate(todo_entries)
            if entry and entry[0].strip().startswith(f"### {req_id}")
        ),
        None,
    )

    if entry_index is None:
        if heading in done_section:
            raise ValueError(f"Requirement {req_id} is already done")
        if heading in suffix:
            raise ValueError(f"Requirement {req_id} is retired")
        raise ValueError(f"Requirement {req_id} not found in todo section")

    entry_lines = todo_entries.pop(entry_index)
    tests_value = "; ".join(tests)
    commits_value = "; ".join(commits) if commits else "none"

    updated_entry: list[str] = []
    status_set = False
    reason_set = False
    for line in entry_lines:
        stripped = line.strip()
        if stripped.startswith("- Status:"):
            updated_entry.append("- Status: done")
            status_set = True
        elif stripped.startswith("- Reason:"):
            updated_entry.append(f"- Reason: {reason}")
            reason_set = True
        elif stripped.startswith("- Amends:"):
            continue
        else:
            updated_entry.append(line)

    if not status_set:
        updated_entry.append("- Status: done")
    if not reason_set:
        updated_entry.append(f"- Reason: {reason}")

    updated_entry = _update_trace(updated_entry, tests_value, commits_value, default_prompts="none")
    updated_entry = _set_amends(updated_entry, None)
    done_entries.insert(0, updated_entry)

    closed_amendments: list[str] = []
    remaining_todo: list[list[str]] = []
    for entry in todo_entries:
        amends_target = _extract_amends(entry)
        if amends_target == req_id:
            amendment_id = _extract_requirement_id(entry) or req_id
            entry = _set_status(entry, "done")
            entry = _set_amends(entry, None)
            entry = _set_reason(
                entry,
                f"Amendment completed under {req_id}",
            )
            entry = _update_trace(entry, tests_value, commits_value, default_prompts="none")
            done_entries.insert(0, entry)
            closed_amendments.append(amendment_id)
        else:
            remaining_todo.append(entry)

    todo_entries = remaining_todo

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
    return closed_amendments





def reopen_functional_requirement_for_amendment(
    path: Path,
    amendment_id: str,
    primary_id: str,
    *,
    reason: str | None = None,
) -> None:
    """Reopen *amendment_id* under *primary_id* for in-progress updates."""

    contents = path.read_text(encoding="utf-8")

    before_todo, todo_header, remainder = contents.partition(_TODO_MARKER)
    if not todo_header:
        raise ValueError("Functional catalog missing todo section")

    todo_section, done_header, remainder = remainder.partition(_DONE_MARKER)
    if not done_header:
        raise ValueError("Functional catalog missing done section")

    done_section, retired_header, suffix = remainder.partition(_RETIRED_MARKER)
    if not retired_header:
        raise ValueError("Functional catalog missing retired section")

    todo_entries = _split_requirement_entries(todo_section)
    done_entries = _split_requirement_entries(done_section)

    target_index = None
    for idx, entry in enumerate(todo_entries):
        if _extract_requirement_id(entry) == amendment_id:
            target_index = idx
            break

    if target_index is not None:
        entry = todo_entries[target_index]
        entry = _set_status(entry, "doing")
        entry = _set_amends(entry, primary_id)
        entry = _set_reason(entry, reason or f"Amendment in progress under {primary_id}")
        todo_entries[target_index] = entry
    else:
        for idx, entry in enumerate(done_entries):
            if _extract_requirement_id(entry) == amendment_id:
                entry = _set_status(entry, "doing")
                entry = _set_amends(entry, primary_id)
                entry = _set_reason(entry, reason or f"Amendment in progress under {primary_id}")
                done_entries.pop(idx)
                todo_entries.insert(0, entry)
                break
        else:
            raise ValueError(f"Requirement {amendment_id} not found for amendment")

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


def begin_historic_amendment(
    path: Path,
    req_id: str,
    *,
    amendment_reason: str,
    allow_parallel: bool = False,
) -> None:
    """Reopen *req_id* for a historic amendment session."""

    reason_text = amendment_reason.strip()
    if not reason_text:
        raise ValueError("Provide a non-empty amendment reason.")

    contents = path.read_text(encoding="utf-8")
    heading = f"### {req_id}"
    if heading not in contents:
        raise ValueError(f"Requirement {req_id} not found in {path}")

    before_todo, todo_header, remainder = contents.partition(_TODO_MARKER)
    if not todo_header:
        raise ValueError("Functional catalog missing todo section")

    todo_section, done_header, remainder = remainder.partition(_DONE_MARKER)
    if not done_header:
        raise ValueError("Functional catalog missing done section")

    done_section, retired_header, _suffix = remainder.partition(_RETIRED_MARKER)
    if not retired_header:
        raise ValueError("Functional catalog missing retired section")

    todo_entries = _split_requirement_entries(todo_section)
    done_entries = _split_requirement_entries(done_section)

    if any(_extract_requirement_id(entry) == req_id for entry in todo_entries):
        raise ValueError(
            f"Requirement {req_id} must be done before reopening for amendment."
        )

    if not any(_extract_requirement_id(entry) == req_id for entry in done_entries):
        raise ValueError(f"Requirement {req_id} is not marked done and cannot be amended.")

    active_primaries = [
        _extract_requirement_id(entry)
        for entry in todo_entries
        if _extract_status(entry) == "doing" and not _extract_amends(entry)
    ]
    if active_primaries and not allow_parallel:
        names = ", ".join(filter(None, active_primaries))
        raise ValueError(
            "Another primary requirement is already in progress: "
            f"{names}. Re-run with --allow-parallel to override."
        )

    reopen_functional_requirement_for_amendment(
        path,
        amendment_id=req_id,
        primary_id=req_id,
        reason=f"Historic amendment in progress: {reason_text}",
    )


def bulk_reopen_functional_requirements(
    path: Path,
    primary_id: str,
    amendment_ids: Sequence[str],
    *,
    reason: str,
    allow_doing: bool = False,
) -> list[str]:
    """Reopen multiple requirements under *primary_id* as amendments."""

    unique_ids: list[str] = []
    seen: set[str] = set()
    for amendment_id in amendment_ids:
        trimmed = amendment_id.strip()
        if not trimmed:
            continue
        if trimmed in seen:
            continue
        seen.add(trimmed)
        unique_ids.append(trimmed)

    if not unique_ids:
        raise ValueError("Provide at least one requirement ID to reopen.")

    reason_text = reason.strip()
    if not reason_text:
        raise ValueError("Provide a non-empty reason summarising the amendment.")

    contents = path.read_text(encoding="utf-8")

    heading = f"### {primary_id}"
    if heading not in contents:
        raise ValueError(f"Primary requirement {primary_id} not found in {path}")

    before_todo, todo_header, remainder = contents.partition(_TODO_MARKER)
    if not todo_header:
        raise ValueError("Functional catalog missing todo section")

    todo_section, done_header, remainder = remainder.partition(_DONE_MARKER)
    if not done_header:
        raise ValueError("Functional catalog missing done section")

    done_section, retired_header, _suffix = remainder.partition(_RETIRED_MARKER)
    if not retired_header:
        raise ValueError("Functional catalog missing retired section")

    todo_entries = _split_requirement_entries(todo_section)
    done_entries = _split_requirement_entries(done_section)

    status_map: dict[str, tuple[str, list[str]]] = {}
    for entry in todo_entries:
        req = _extract_requirement_id(entry)
        if req:
            status_map[req] = ("todo", entry)
    for entry in done_entries:
        req = _extract_requirement_id(entry)
        if req:
            status_map[req] = ("done", entry)

    for req in unique_ids:
        if req not in status_map:
            raise ValueError(f"Requirement {req} not found in {path}")
        section, entry = status_map[req]
        current_status = (_extract_status(entry) or "").lower()
        if section == "todo":
            if current_status == "doing":
                if not allow_doing:
                    raise ValueError(
                        f"Requirement {req} is already in progress; use --allow-doing to override."
                    )
                continue
            raise ValueError(
                f"Requirement {req} is not done and cannot be reopened as an amendment."
            )
        if current_status != "done":
            raise ValueError(
                f"Requirement {req} must be done before reopening; current status is {current_status or 'unknown'}."
            )

    reopened: list[str] = []
    bulk_reason = f"Bulk amendment in progress under {primary_id}: {reason_text}"
    for req in unique_ids:
        reopen_functional_requirement_for_amendment(
            path,
            amendment_id=req,
            primary_id=primary_id,
            reason=bulk_reason,
        )
        reopened.append(req)

    return reopened

def start_functional_requirement(
    path: Path,
    req_id: str,
    *,
    allow_parallel: bool = False,
) -> None:
    """Promote *req_id* from todo to doing within the functional catalog at *path*."""

    contents = path.read_text(encoding="utf-8")
    heading = f"### {req_id}"
    if heading not in contents:
        raise ValueError(f"Requirement {req_id} not found in {path}")

    before_todo, todo_header, remainder = contents.partition(_TODO_MARKER)
    if not todo_header:
        raise ValueError("Functional catalog missing todo section")

    todo_section, done_header, remainder = remainder.partition(_DONE_MARKER)
    if not done_header:
        raise ValueError("Functional catalog missing done section")

    done_section, retired_header, suffix = remainder.partition(_RETIRED_MARKER)
    if not retired_header:
        raise ValueError("Functional catalog missing retired section")

    todo_entries = _split_requirement_entries(todo_section)

    existing_primaries = [
        _extract_requirement_id(entry)
        for entry in todo_entries
        if _extract_status(entry) == "doing"
        and not _extract_amends(entry)
        and _extract_requirement_id(entry) != req_id
    ]
    if existing_primaries and not allow_parallel:
        existing = ", ".join(filter(None, existing_primaries))
        raise ValueError(
            "Another requirement is already in progress: "
            f"{existing}. Re-run with --allow-parallel to override."
        )

    entry_index = next(
        (
            idx
            for idx, entry in enumerate(todo_entries)
            if entry and entry[0].strip().startswith(f"### {req_id}")
        ),
        None,
    )

    if entry_index is None:
        if heading in done_section:
            raise ValueError(f"Requirement {req_id} is already done")
        if heading in suffix:
            raise ValueError(f"Requirement {req_id} is retired")
        raise ValueError(f"Requirement {req_id} not found in todo section")

    entry_lines = todo_entries[entry_index]
    entry_lines = _set_status(entry_lines, "doing")
    entry_lines = _set_amends(entry_lines, None)
    todo_entries[entry_index] = entry_lines

    updated_contents = (
        before_todo
        + todo_header
        + _format_requirement_section(todo_entries)
        + done_header
        + done_section
        + retired_header
        + suffix
    )
    updated_contents = _update_status_summary(updated_contents)
    path.write_text(updated_contents, encoding="utf-8")



def append_non_functional_requirement(
    path: Path, requirement: NonFunctionalRequirement
) -> str:
    """Append *requirement* to the non-functional catalog at *path*."""

    text = path.read_text(encoding="utf-8")
    req_id = requirement.req_id or generate_next_id(text, _NON_FUNCTIONAL_PREFIX)

    entry_lines = [
        f"### {req_id}: {requirement.title}",
        f"- Owner: {requirement.owner}",
        f"- Category: {requirement.category}",
        f"- Description: {requirement.description}",
        f"- Measurement: {requirement.measurement}",
        f"- Priority: {requirement.priority}",
        f"- Status: {requirement.status}",
        f"- Reason: {requirement.reason}",
        f"- Trace: prompts {requirement.trace_prompts}, tests {requirement.trace_tests}, scripts {requirement.trace_scripts}, monitors {requirement.trace_monitors}",
    ]
    if requirement.notes:
        entry_lines.append(f"- Notes: {requirement.notes}")
    entry_lines.append("---")

    updated = _insert_entry(text, "\n".join(entry_lines))
    updated = _update_status_summary(updated)
    path.write_text(updated, encoding="utf-8")
    return req_id


def _insert_entry(contents: str, entry: str) -> str:
    if _TODO_MARKER not in contents or _DONE_MARKER not in contents:
        raise ValueError("Catalog appears malformed; missing expected sections")
    insertion_point = contents.index(_DONE_MARKER)
    prefix = contents[:insertion_point].rstrip()
    suffix = contents[insertion_point:]
    return f"{prefix}\n\n{entry}\n\n{suffix}"


def _update_status_summary(contents: str) -> str:
    if _SUMMARY_START not in contents or _SUMMARY_END not in contents:
        return contents

    todo_section = _extract_section(contents, _TODO_MARKER, _DONE_MARKER)
    done_section = _extract_section(contents, _DONE_MARKER, _RETIRED_MARKER)
    retired_section = _extract_section(contents, _RETIRED_MARKER, None)
    todo_count, todo_statuses = _summarise_entries(todo_section)
    done_count, done_statuses = _summarise_entries(done_section)
    retired_count, retired_statuses = _summarise_entries(retired_section)

    if todo_count == 0 and done_count == 0 and retired_count == 0:
        summary_text = "_No requirements recorded yet._"
    else:
        summary_text = '; '.join([
            _format_summary("Todo", todo_count, todo_statuses),
            _format_summary("Done", done_count, done_statuses),
            _format_summary("Retired", retired_count, retired_statuses),
        ])

    return _replace_summary(contents, summary_text)


def _extract_section(contents: str, start_marker: str, end_marker: str | None) -> str:
    try:
        start_index = contents.index(start_marker) + len(start_marker)
    except ValueError:
        return ""
    if end_marker:
        try:
            end_index = contents.index(end_marker, start_index)
        except ValueError:
            end_index = len(contents)
    else:
        end_index = len(contents)
    return contents[start_index:end_index]


def _summarise_entries(section: str) -> tuple[int, Counter[str]]:
    if not section:
        return 0, Counter()
    count = 0
    statuses: Counter[str] = Counter()
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith('### '):
            count += 1
        elif stripped.startswith('- ID:'):
            count += 1
        elif stripped.startswith('- Status:'):
            status_value = stripped.split(':', 1)[1].strip()
            if status_value:
                statuses[status_value] += 1
    return count, statuses


def _format_summary(label: str, count: int, statuses: Counter[str]) -> str:
    if count == 0:
        return f"{label}: 0"
    if statuses:
        breakdown = ', '.join(f"{status}={statuses[status]}" for status in sorted(statuses))
    else:
        breakdown = 'status unspecified'
    return f"{label}: {count} ({breakdown})"


def _replace_summary(contents: str, summary_text: str) -> str:
    start_index = contents.index(_SUMMARY_START) + len(_SUMMARY_START)
    end_index = contents.index(_SUMMARY_END)
    before = contents[:start_index]
    after = contents[end_index:]
    return f"{before}\n{summary_text}\n{after}"


def append_log_entry(
    log_path: Path, req_id: str, change_summary: str, author: str, reference: str
) -> None:
    """Append a row describing the change to the requirements log."""

    timestamp = datetime.now(UTC).date().isoformat()
    row = f"| {timestamp} | {req_id} | {change_summary} | {author} | {reference} |"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{row}\n")

