"""Deprecated shim for agentlab.cli.mark_done_nonfunctional (moved to reqflow.cli.mark_done_nonfunctional on 2025-10-27)."""
from __future__ import annotations

import warnings as _warnings

from reqflow.cli import mark_done_nonfunctional as _module

_warnings.warn(
    "agentlab.cli.mark_done_nonfunctional is deprecated; use reqflow.cli.mark_done_nonfunctional instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export public attributes from the reqflow module
from reqflow.cli.mark_done_nonfunctional import *  # noqa: F401,F403

__all__ = getattr(_module, '__all__', [attr for attr in dir(_module) if not attr.startswith('_')])
