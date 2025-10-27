"""Deprecated shim for agentlab.cli.amend (moved to reqflow.cli.amend on 2025-10-27)."""
from __future__ import annotations

import warnings as _warnings

from reqflow.cli import amend as _module

_warnings.warn(
    "agentlab.cli.amend is deprecated; use reqflow.cli.amend instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export public attributes from the reqflow module
from reqflow.cli.amend import *  # noqa: F401,F403

__all__ = getattr(_module, '__all__', [attr for attr in dir(_module) if not attr.startswith('_')])
