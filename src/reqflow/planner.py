"""Planner components that ensure requirements are captured before implementation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, Literal
import re

from reqflow.catalog import (
    FunctionalRequirement,
    NonFunctionalRequirement,
    append_functional_requirement,
    append_log_entry,
    append_non_functional_requirement,
    catalog_root,
)

RequirementType = Literal["functional", "non-functional"]

_FUNCTIONAL_DEFAULT_OWNER = "product"
_NON_FUNCTIONAL_DEFAULT_OWNER = "platform"

_FUNCTIONAL_ROLES = {
    "developer": "developer",
    "operator": "operator",
    "user": "user",
}

_NON_FUNCTIONAL_SIGNALS: dict[str, tuple[str, ...]] = {
    "performance": ("performance", "latency", "throughput", "responsive", "through-put"),
    "reliability": ("availability", "reliability", "uptime", "resilience", "redundant"),
    "security": ("security", "secure", "privacy", "encryption", "auth", "authorization"),
    "usability": ("usability", "accessibility", "ux", "discoverable"),
    "other": ("compliance", "cost", "governance", "observability", "monitoring"),
}

_NON_FUNCTIONAL_MODIFIERS = {"ensure", "must", "should", "guarantee", "maintain", "enforce"}

_PRIORITY_HIGH_KEYWORDS = {"must", "critical", "urgent", "immediately", "blocker", "p0"}
_PRIORITY_LOW_KEYWORDS = {"optional", "nice to have", "eventually", "future", "later"}

_ARCHITECTURAL_KEYWORDS = {
    "architecture",
    "architectural",
    "module",
    "component",
    "interface",
    "protocol",
    "service",
    "api contract",
    "data model",
    "refactor",
    "design",
    "event bus",
    "persistence",
}

_SIMILARITY_THRESHOLD = 0.72
_DEFAULT_ACCEPTANCE_PLACEHOLDER = "Acceptance criteria to be detailed from prompt."


@dataclass(slots=True)
class RequirementDraft:
    """Structured description inferred from a prompt."""

    kind: RequirementType
    title: str
    owner: str
    narrative: str
    acceptance: list[str]
    status: str
    trace_prompts: str
    notes: str | None
    priority: str
    reason: str
    category: str | None = None
    measurement: str | None = None
    architectural: bool = False


@dataclass(slots=True)
class RequirementMatch:
    """Represents an existing requirement that may overlap with a new prompt."""

    requirement_id: str
    title: str
    similarity: float


@dataclass(slots=True)
class RequirementAction:
    """Outcome of attempting to ensure a requirement exists."""

    outcome: Literal["created", "needs-update", "dry-run"]
    kind: RequirementType
    requirement_id: str | None
    title: str
    message: str
    priority: str | None = None
    reason: str | None = None
    adr_path: Path | None = None


class RequirementPlanner:
    """Ensures requirements are recorded before implementation begins."""

    def __init__(self, root: Path | None = None) -> None:
        self._catalog_dir = catalog_root(root)

    def ensure_requirement(
        self,
        prompt: str,
        *,
        reference: str,
        author: str,
        owner: str | None = None,
        category: str | None = None,
        priority: str | None = None,
        reason: str | None = None,
        force_new: bool = False,
        summary: str | None = None,
        dry_run: bool = False,
    ) -> RequirementAction:
        draft = build_requirement_draft(prompt, owner=owner, category=category, priority=priority, reason=reason)

        existing = self._find_existing(draft)

        if existing and not force_new:
            advisory = (
                "Existing requirement appears to cover this prompt: "
                f"{existing.requirement_id} - {existing.title}. "
                "Update it manually or re-run with --force-new if a successor is required. "
                f"When committing, use the trailer 'Refs {existing.requirement_id}'."
            )
            if draft.architectural:
                advisory += " Consider drafting or updating an ADR for the architectural change."
            return RequirementAction(
                outcome="needs-update",
                kind=draft.kind,
                requirement_id=existing.requirement_id,
                title=existing.title,
                message=advisory,
                priority=draft.priority,
                reason=draft.reason,
            )

        if dry_run:
            title = draft.title if not existing else existing.title
            notice = (
                "Dry run only; no catalog changes were made. "
                f"Planned priority: {draft.priority}."
            )
            if draft.architectural:
                notice += " Architectural prompt detected; ADR recommended."
            return RequirementAction(
                outcome="dry-run",
                kind=draft.kind,
                requirement_id=existing.requirement_id if existing else None,
                title=title,
                message=notice,
                priority=draft.priority,
                reason=draft.reason,
            )

        if draft.kind == "functional":
            catalog_path = self._catalog_dir / "functional.md"
            req = FunctionalRequirement(
                title=draft.title,
                owner=draft.owner,
                narrative=draft.narrative,
                acceptance_criteria=draft.acceptance,
                priority=draft.priority,
                status=draft.status,
                trace_prompts=draft.trace_prompts,
                trace_tests="pending",
                trace_commits="pending",
                reason=draft.reason,
                notes=draft.notes,
            )
            requirement_id = append_functional_requirement(catalog_path, req)
        else:
            catalog_path = self._catalog_dir / "non-functional.md"
            req = NonFunctionalRequirement(
                title=draft.title,
                owner=draft.owner,
                category=draft.category or "other",
                description=draft.narrative,
                measurement=draft.measurement or "Define measurement",
                priority=draft.priority,
                status=draft.status,
                trace_prompts=draft.trace_prompts,
                trace_tests="pending",
                trace_scripts="pending",
                trace_monitors="pending",
                reason=draft.reason,
                notes=draft.notes,
            )
            requirement_id = append_non_functional_requirement(catalog_path, req)

        log_path = self._catalog_dir / "log.md"
        log_summary = summary or f"Captured requirement {requirement_id}: {draft.title}"
        append_log_entry(log_path, requirement_id, log_summary, author, reference)

        adr_path: Path | None = None
        if draft.architectural:
            adr_path = self._maybe_generate_adr(requirement_id, draft, reference)

        message = (
            f"Recorded {requirement_id} in {catalog_path} (priority {draft.priority})."
        )
        if adr_path:
            message += f" Drafted ADR at {adr_path}."
        message += " Update trace fields and status once implementation lands, and include the commit trailer 'Refs {requirement_id}'."

        return RequirementAction(
            outcome="created",
            kind=draft.kind,
            requirement_id=requirement_id,
            title=draft.title,
            message=message,
            priority=draft.priority,
            reason=draft.reason,
            adr_path=adr_path,
        )

    def _find_existing(self, draft: RequirementDraft) -> RequirementMatch | None:
        catalog_path = (
            self._catalog_dir / "functional.md"
            if draft.kind == "functional"
            else self._catalog_dir / "non-functional.md"
        )
        if not catalog_path.exists():
            return None
        entries = list(_load_titles(catalog_path.read_text(encoding="utf-8")))
        best: RequirementMatch | None = None
        for req_id, title in entries:
            similarity = SequenceMatcher(None, draft.title.lower(), title.lower()).ratio()
            if similarity >= _SIMILARITY_THRESHOLD and (
                best is None or similarity > best.similarity
            ):
                best = RequirementMatch(req_id, title, similarity)
        return best

    def _maybe_generate_adr(
        self,
        requirement_id: str,
        draft: RequirementDraft,
        reference: str,
    ) -> Path:
        docs_dir = self._catalog_dir.parent
        adr_dir = docs_dir / "adr"
        adr_dir.mkdir(parents=True, exist_ok=True)

        slug = _slugify(draft.title or requirement_id)
        date_prefix = datetime.now(UTC).strftime("%Y%m%d")
        candidate = adr_dir / f"adr-{date_prefix}-{slug}.md"
        counter = 1
        while candidate.exists():
            candidate = adr_dir / f"adr-{date_prefix}-{slug}-{counter}.md"
            counter += 1

        body = (
            f"# {draft.title}\n\n"
            "## Status\n\n"
            "Proposed\n\n"
            "## Context\n\n"
            f"- Requirement: {requirement_id}\n"
            f"- Prompt: {draft.trace_prompts}\n"
            f"- Reference: {reference}\n\n"
            "Describe the architectural motivation and surrounding constraints.\n\n"
            "## Decision\n\n"
            "TBD\n\n"
            "## Consequences\n\n"
            "TBD\n"
        )
        candidate.write_text(body, encoding="utf-8")
        return candidate


def build_requirement_draft(
    prompt: str,
    *,
    owner: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    reason: str | None = None,
) -> RequirementDraft:
    """Infer a structured requirement draft from *prompt*."""

    prompt = prompt.strip()
    kind = classify_prompt(prompt)
    title = synthesise_title(prompt)
    acceptance = list(extract_acceptance(prompt)) or [prompt]
    status = "backlog"
    trace_prompts = prompt[:80] + ("..." if len(prompt) > 80 else "")
    notes = "Auto-generated from prompt; refine narrative and acceptance criteria."
    architectural = is_architectural_prompt(prompt)
    resolved_priority = priority or infer_priority(prompt)
    resolved_reason = reason or "pending"

    if kind == "functional":
        inferred_owner = owner or infer_owner(prompt) or _FUNCTIONAL_DEFAULT_OWNER
        narrative = synthesise_narrative(prompt)
        return RequirementDraft(
            kind=kind,
            title=title,
            owner=inferred_owner,
            narrative=narrative,
            acceptance=acceptance,
            status=status,
            trace_prompts=trace_prompts,
            notes=notes,
            priority=resolved_priority,
            reason=resolved_reason,
            category=None,
            measurement=None,
            architectural=architectural,
        )

    inferred_owner = owner or _NON_FUNCTIONAL_DEFAULT_OWNER
    inferred_category = category or infer_category(prompt)
    measurement = synthesise_measurement(prompt)
    narrative = prompt
    return RequirementDraft(
        kind=kind,
        title=title,
        owner=inferred_owner,
        narrative=narrative,
        acceptance=acceptance,
        status=status,
        trace_prompts=trace_prompts,
        notes=notes,
        priority=resolved_priority,
        reason=resolved_reason,
        category=inferred_category,
        measurement=measurement,
        architectural=architectural,
    )


def classify_prompt(prompt: str) -> RequirementType:
    lowered = prompt.lower()
    total_score = 0
    modifier_hit = any(word in lowered for word in _NON_FUNCTIONAL_MODIFIERS)
    for keywords in _NON_FUNCTIONAL_SIGNALS.values():
        for keyword in keywords:
            if keyword in lowered:
                total_score += 1
    if total_score >= 2 or (total_score >= 1 and modifier_hit):
        return "non-functional"
    if "as a" in lowered and "i want" in lowered:
        return "functional"
    return "functional"


def infer_owner(prompt: str) -> str | None:
    lowered = prompt.lower()
    for keyword, owner in _FUNCTIONAL_ROLES.items():
        if keyword in lowered:
            return owner
    return None


def infer_category(prompt: str) -> str:
    lowered = prompt.lower()
    best_category = "other"
    best_score = 0
    for category, keywords in _NON_FUNCTIONAL_SIGNALS.items():
        score = sum(1 for keyword in keywords if keyword in lowered)
        if score > best_score:
            best_category = category
            best_score = score
    return best_category



def infer_priority(prompt: str, default: str = "medium") -> str:
    lowered = prompt.lower()
    if any(keyword in lowered for keyword in _PRIORITY_HIGH_KEYWORDS):
        return "high"
    if any(keyword in lowered for keyword in _PRIORITY_LOW_KEYWORDS):
        return "low"
    if any(modifier in lowered for modifier in _NON_FUNCTIONAL_MODIFIERS if modifier != "should"):
        return "high"
    return default




def is_architectural_prompt(prompt: str) -> bool:
    lowered = prompt.lower()
    return any(keyword in lowered for keyword in _ARCHITECTURAL_KEYWORDS)


def synthesise_title(prompt: str) -> str:
    first_sentence = prompt.splitlines()[0].strip()
    if len(first_sentence) > 80:
        first_sentence = first_sentence[:77] + "..."
    return first_sentence.capitalize()


def synthesise_narrative(prompt: str) -> str:
    owner = infer_owner(prompt) or "user"
    prefix = f"As a {owner}, I want "
    suffix = " so the capability is traceable."
    allowed = max(10, 120 - len(prefix) - len(suffix))

    raw = prompt.strip()
    if not raw:
        summary = "a documented capability"
    else:
        first_line = raw.splitlines()[0]
        sentence = re.split(r"(?<=[.!?])\s+", first_line, maxsplit=1)[0]
        summary = " ".join(sentence.split())
        if not summary:
            summary = "a documented capability"
    if len(summary) > allowed:
        trimmed = summary[:allowed].rstrip()
        if len(trimmed) < len(summary):
            trimmed = trimmed.rstrip(".:,;")
            trimmed = trimmed[: max(0, allowed - 3)].rstrip()
            summary = f"{trimmed}..."
        else:
            summary = trimmed
    return f"{prefix}{summary}{suffix}"


def synthesise_measurement(prompt: str) -> str:
    return (
        "Document success criteria derived from the prompt (auto-captured)."
        " Update with concrete metrics."
    )


def extract_acceptance(prompt: str) -> Iterable[str]:
    lines = [line.strip(" -\t") for line in prompt.splitlines() if line.strip()]
    bullets = [line for line in lines if line.startswith(("*", "-", "Given", "When", "Then"))]
    if bullets:
        yield from bullets
    else:
        yield _DEFAULT_ACCEPTANCE_PLACEHOLDER


def _load_titles(contents: str) -> Iterable[tuple[str, str]]:
    current_id: str | None = None
    current_title: str | None = None
    for raw_line in contents.splitlines():
        line = raw_line.strip()
        if line.startswith("### ") and ':' in line:
            if current_id and current_title:
                yield current_id, current_title
            heading_body = line[4:]
            requirement_id, _, title = heading_body.partition(':')
            current_id = requirement_id.strip()
            current_title = title.strip() or None
        elif line.startswith("- ID:"):
            if current_id and current_title:
                yield current_id, current_title
            current_id = line.split(":", 1)[1].strip()
            current_title = None
        elif line.startswith("- Title:") and current_id and not current_title:
            current_title = line.split(":", 1)[1].strip()
    if current_id and current_title:
        yield current_id, current_title


def _slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value or "adr"
