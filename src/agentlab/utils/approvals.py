"""Approval enforcement helpers for mark-done workflows."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def approval_required() -> bool:
    """Return True when mark-done operations must capture approval metadata."""

    value = os.getenv("REQFLOW_REQUIRE_APPROVAL", "true").strip().lower()
    return value in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class ApprovalContext:
    """Metadata captured for an approval event."""

    label: str
    overridden: bool = False


class ApprovalError(ValueError):
    """Raised when approval metadata is missing while enforcement is active."""


def validate_approval(
    *,
    approval_source: str | None,
    override: bool,
    command_name: str,
) -> ApprovalContext | None:
    """Validate approval metadata for *command_name* and return captured context.

    When approval is not required, the function returns ``None``. If approval is
    enforced, callers must supply either ``approval_source`` or ``override``.
    """

    if not approval_required():
        return None

    if approval_source and approval_source.strip():
        return ApprovalContext(label=approval_source.strip(), overridden=False)

    if override:
        return ApprovalContext(label="override", overridden=True)

    raise ApprovalError(
        (
            f"{command_name} requires --approval-source <value> or "
            "--override-wait-for-approval when REQFLOW_REQUIRE_APPROVAL is enabled."
        )
    )
