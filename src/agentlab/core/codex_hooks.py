"""Codex middleware hook that guarantees requirements are captured before tasks run."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from agentlab.core.middleware import auto_capture_prompt, should_block_for_manual_update


def before_task(task: dict[str, Any]) -> dict[str, Any]:
    """Capture or reconcile a requirement for the provided Codex *task*.

    The hook expects ``task`` to provide at least a ``prompt`` field. Optional
    keys (``reference``, ``owner``, ``category``, ``priority`` etc.) align with
    :func:`agentlab.core.middleware.auto_capture_prompt` parameters. The returned
    dictionary mirrors the input with additional metadata:

    * ``requirement_id`` – the catalog identifier that now exists for the task
    * ``messages`` – a list of human-readable notes added by the hook
    * ``blocked`` – ``True`` when the task should pause for manual intervention
    * ``adr_path`` – draft ADR path (string) if one was generated

    The hook may raise :class:`ValueError` if no prompt is supplied.
    """

    if "prompt" not in task or not str(task["prompt"]).strip():
        raise ValueError("task payload must include a non-empty 'prompt'")

    prompt = str(task["prompt"]).strip()
    reference = str(task.get("reference", "prompt"))
    author = str(task.get("author", "codex"))
    owner = task.get("owner")
    category = task.get("category")
    priority = task.get("priority")
    force_new = bool(task.get("force_new", False))
    summary = task.get("summary")
    dry_run = bool(task.get("dry_run", False))
    catalog_override = task.get("catalog_root")
    catalog_root = Path(catalog_override) if catalog_override else None

    action = auto_capture_prompt(
        prompt,
        reference=reference,
        catalog_root=catalog_root,
        author=author,
        owner=owner,
        category=category,
        priority=priority,
        force_new=force_new,
        summary=summary,
        dry_run=dry_run,
    )

    task = dict(task)  # avoid mutating the original payload
    task["requirement_id"] = action.requirement_id
    task["priority"] = action.priority
    if action.adr_path:
        task["adr_path"] = str(action.adr_path)

    messages = list(task.get("messages", []))
    messages.append(action.message)
    task["messages"] = messages

    if should_block_for_manual_update(action):
        task["blocked"] = True

    return task
