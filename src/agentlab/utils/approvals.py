"""Deprecated shim; moved to reqflow.approvals on 2025-10-27."""
from __future__ import annotations

import warnings as _warnings

from reqflow.approvals import *  # noqa: F401,F403

_warnings.warn(
    "agentlab.utils.approvals is deprecated; import reqflow.approvals instead.",
    DeprecationWarning,
    stacklevel=2,
)

