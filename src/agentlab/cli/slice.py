"""Deprecated shim for agentlab.cli.slice (moved to reqflow.cli.slice on 2025-10-27)."""
from __future__ import annotations

import warnings as _warnings

from reqflow.cli import slice as _module

_warnings.warn(
    "agentlab.cli.slice is deprecated; use reqflow.cli.slice instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export public attributes from the reqflow module
from reqflow.cli.slice import *  # noqa: F401,F403

__all__ = getattr(_module, '__all__', [attr for attr in dir(_module) if not attr.startswith('_')])
