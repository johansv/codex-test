"""Utilities for managing requirement catalogs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import re

__all__ = [
    "FunctionalRequirement",
    "NonFunctionalRequirement",
    "append_functional_requirement",
    "append_non_functional_requirement",
    "append_log_entry",
    "catalog_root",
    "generate_next_id",
]

_ACTIVE_MARKER = "## Active Requirements"
_SATISFIED_MARKER = "## Satisfied Requirements"
_FUNCTIONAL_PREFIX = "REQ-F"
_NON_FUNCTIONAL_PREFIX = "REQ-NF"
_ID_PATTERN = re.compile(r"REQ-[A-Z]+-(?P<number>\d{3})")


@dataclass(slots=True)
class FunctionalRequirement:
    """Represents a functional requirement entry."""

    title: str
    owner: str
    narrative: str
    acceptance_criteria: list[str]
    status: str = "proposed"
    trace_prompts: str = "none"
    trace_tests: str = "none"
    trace_commits: str = "none"
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
    status: str = "proposed"
    trace_prompts: str = "none"
    trace_tests: str = "none"
    trace_scripts: str = "none"
    trace_monitors: str = "none"
    notes: str | None = None
    req_id: str | None = None


def catalog_root(start: Path | None = None) -> Path:
    """Return the expected root for requirement catalogs.

    Walks up from *start* (defaults to the current file) until the repository
    docs directory is located. Raises FileNotFoundError if the structure is not
    discovered.
    """

    candidate = start or Path(__file__).resolve()
    for parent in candidate.parents:
        docs_dir = parent / "docs" / "requirements"
        if docs_dir.exists():
            return docs_dir
    raise FileNotFoundError("Could not locate docs/requirements directory")


def generate_next_id(contents: str, prefix: str) -> str:
    """Return the next incremental requirement ID for *prefix*.

    Existing IDs are detected regardless of section so regenerated files remain
    consistent.
    """

    numbers = [
        int(match.group("number"))
        for match in _ID_PATTERN.finditer(contents)
        if match.group(0).startswith(prefix)
    ]
    next_number = max(numbers) + 1 if numbers else 1
    return f"{prefix}-{next_number:03d}"


def append_functional_requirement(path: Path, requirement: FunctionalRequirement) -> str:
    """Append *requirement* to the functional catalog located at *path*.

    Returns the ID assigned to the requirement.
    """

    text = path.read_text(encoding="utf-8")
    req_id = requirement.req_id or generate_next_id(text, _FUNCTIONAL_PREFIX)

    entry_lines = [
        f"- ID: {req_id}",
        f"- Title: {requirement.title}",
        f"- Owner: {requirement.owner}",
        f"- Narrative: {requirement.narrative}",
        "- Acceptance Criteria:",
    ]
    for criterion in requirement.acceptance_criteria:
        entry_lines.append(f"  * {criterion}")
    entry_lines.extend(
        [
            f"- Status: {requirement.status}",
            f"- Trace: prompts {requirement.trace_prompts}, tests {requirement.trace_tests}, commits {requirement.trace_commits}",
        ]
    )
    if requirement.notes:
        entry_lines.append(f"- Notes: {requirement.notes}")

    updated = _insert_entry(text, "\n".join(entry_lines))
    path.write_text(updated, encoding="utf-8")
    return req_id


def append_non_functional_requirement(
    path: Path, requirement: NonFunctionalRequirement
) -> str:
    """Append *requirement* to the non-functional catalog at *path*.

    Returns the ID assigned to the requirement.
    """

    text = path.read_text(encoding="utf-8")
    req_id = requirement.req_id or generate_next_id(text, _NON_FUNCTIONAL_PREFIX)

    entry_lines = [
        f"- ID: {req_id}",
        f"- Title: {requirement.title}",
        f"- Owner: {requirement.owner}",
        f"- Category: {requirement.category}",
        f"- Description: {requirement.description}",
        f"- Measurement: {requirement.measurement}",
        f"- Status: {requirement.status}",
        f"- Trace: prompts {requirement.trace_prompts}, tests {requirement.trace_tests}, scripts {requirement.trace_scripts}, monitors {requirement.trace_monitors}",
    ]
    if requirement.notes:
        entry_lines.append(f"- Notes: {requirement.notes}")

    updated = _insert_entry(text, "\n".join(entry_lines))
    path.write_text(updated, encoding="utf-8")
    return req_id


def _insert_entry(contents: str, entry: str) -> str:
    if _ACTIVE_MARKER not in contents or _SATISFIED_MARKER not in contents:
        raise ValueError("Catalog appears malformed; missing expected sections")
    insertion_point = contents.index(_SATISFIED_MARKER)
    prefix = contents[:insertion_point].rstrip()
    suffix = contents[insertion_point:]
    return f"{prefix}\n\n{entry}\n\n{suffix}"


def append_log_entry(
    log_path: Path, req_id: str, change_summary: str, author: str, reference: str
) -> None:
    """Append a row describing the change to the requirements log."""

    timestamp = datetime.now(UTC).date().isoformat()
    row = f"| {timestamp} | {req_id} | {change_summary} | {author} | {reference} |"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{row}\n")
