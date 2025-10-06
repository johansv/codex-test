"""Helpers that Codex middleware can use to capture requirements automatically."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from reqflow.planner import RequirementPlanner, RequirementAction


def auto_capture_prompt(
    prompt: str,
    *,
    reference: str,
    catalog_root: Path | None = None,
    author: str = "codex",
    owner: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    reason: str | None = None,
    force_new: bool = False,
    summary: str | None = None,
    dry_run: bool = False,
) -> RequirementAction:
    """Ensure the prompt has a recorded requirement before implementation.

    The function is intended for middleware integration: call it at the start of
    a Codex task, inspect the returned :class:`RequirementAction`, and decide
    whether the task should proceed (for example, block the workflow if
    ``outcome`` is ``"needs-update"``).
    """

    planner = RequirementPlanner(catalog_root)
    return planner.ensure_requirement(
        prompt,
        reference=reference,
        author=author,
        owner=owner,
        category=category,
        priority=priority,
        reason=reason,
        force_new=force_new,
        summary=summary,
        dry_run=dry_run,
    )


def should_block_for_manual_update(action: RequirementAction) -> bool:
    """Return True when middleware should pause for manual requirement edits."""

    return action.outcome == "needs-update"


def action_to_dict(action: RequirementAction) -> dict[str, Any]:
    """Provide a serialisable representation for logging or telemetry."""

    return {
        "outcome": action.outcome,
        "kind": action.kind,
        "requirement_id": action.requirement_id,
        "title": action.title,
        "message": action.message,
        "priority": action.priority,
        "reason": action.reason,
        "adr_path": str(action.adr_path) if action.adr_path else None,
    }
