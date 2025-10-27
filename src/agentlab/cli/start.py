"""Deprecated shim for agentlab.cli.start (moved to reqflow.cli.start on 2025-10-27)."""
from __future__ import annotations

import warnings as _warnings

from reqflow.cli import start as _module

_warnings.warn(
    "agentlab.cli.start is deprecated; use reqflow.cli.start instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export public attributes from the reqflow module
from reqflow.cli.start import *  # noqa: F401,F403

__all__ = getattr(_module, '__all__', [attr for attr in dir(_module) if not attr.startswith('_')])
