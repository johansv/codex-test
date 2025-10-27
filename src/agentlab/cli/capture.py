"""Deprecated shim for agentlab.cli.capture (moved to reqflow.cli.capture on 2025-10-27)."""
from __future__ import annotations

import warnings as _warnings

from reqflow.cli import capture as _module

_warnings.warn(
    "agentlab.cli.capture is deprecated; use reqflow.cli.capture instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export public attributes from the reqflow module
from reqflow.cli.capture import *  # noqa: F401,F403

__all__ = getattr(_module, '__all__', [attr for attr in dir(_module) if not attr.startswith('_')])
