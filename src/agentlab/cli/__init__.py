"""Deprecated CLI namespace; moved to reqflow.cli on 2025-10-27."""

from __future__ import annotations

import importlib
import types
import warnings

_MOVED_MODULES = {
    "amend",
    "batch",
    "bulk_amend",
    "capture",
    "dev",
    "doc_refactor",
    "mark_done",
    "mark_done_nonfunctional",
    "requirements",
    "review",
    "slice",
    "start",
    "start_nonfunctional",
}

__all__ = sorted(_MOVED_MODULES)


def __getattr__(name: str) -> types.ModuleType:
    if name in _MOVED_MODULES:
        warnings.warn(
            "agentlab.cli.* modules are deprecated; import reqflow.cli.* instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return importlib.import_module(f"reqflow.cli.{name}")
    raise AttributeError(name)
