"""Deprecated shim for agentlab.cli.doc_refactor (moved to reqflow.cli.doc_refactor on 2025-10-27)."""
from __future__ import annotations

import warnings as _warnings

from reqflow.cli import doc_refactor as _module

_warnings.warn(
    "agentlab.cli.doc_refactor is deprecated; use reqflow.cli.doc_refactor instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export public attributes from the reqflow module
from reqflow.cli.doc_refactor import *  # noqa: F401,F403

__all__ = getattr(_module, '__all__', [attr for attr in dir(_module) if not attr.startswith('_')])
