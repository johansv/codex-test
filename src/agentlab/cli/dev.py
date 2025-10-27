"""Deprecated shim for agentlab.cli.dev (moved to reqflow.cli.dev on 2025-10-27)."""
from __future__ import annotations

import warnings as _warnings

from reqflow.cli import dev as _module

_warnings.warn(
    "agentlab.cli.dev is deprecated; use reqflow.cli.dev instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export public attributes from the reqflow module
from reqflow.cli.dev import *  # noqa: F401,F403

__all__ = getattr(_module, '__all__', [attr for attr in dir(_module) if not attr.startswith('_')])
