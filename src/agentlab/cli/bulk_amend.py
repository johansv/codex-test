"""Deprecated shim for agentlab.cli.bulk_amend (moved to reqflow.cli.bulk_amend on 2025-10-27)."""
from __future__ import annotations

import warnings as _warnings

from reqflow.cli import bulk_amend as _module

_warnings.warn(
    "agentlab.cli.bulk_amend is deprecated; use reqflow.cli.bulk_amend instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export public attributes from the reqflow module
from reqflow.cli.bulk_amend import *  # noqa: F401,F403

__all__ = getattr(_module, '__all__', [attr for attr in dir(_module) if not attr.startswith('_')])
