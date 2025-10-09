"""Reusable requirements-management toolkit for Codex workflows."""
from __future__ import annotations

from .catalog import (
    FunctionalRequirement,
    NonFunctionalRequirement,
    append_functional_requirement,
    append_non_functional_requirement,
    append_log_entry,
    catalog_root,
    generate_next_id,
    mark_functional_requirement_done,
    reopen_functional_requirement_for_amendment,
    start_functional_requirement,
)
from .planner import (
    RequirementAction,
    RequirementDraft,
    RequirementPlanner,
    build_requirement_draft,
)
from .middleware import action_to_dict, auto_capture_prompt, should_block_for_manual_update

__all__ = [
    "FunctionalRequirement",
    "NonFunctionalRequirement",
    "RequirementAction",
    "RequirementDraft",
    "RequirementPlanner",
    "action_to_dict",
    "append_functional_requirement",
    "append_log_entry",
    "append_non_functional_requirement",
    "auto_capture_prompt",
    "build_requirement_draft",
    "catalog_root",
    "generate_next_id",
    "mark_functional_requirement_done",
    "reopen_functional_requirement_for_amendment",
    "should_block_for_manual_update",
    "start_functional_requirement",
]
