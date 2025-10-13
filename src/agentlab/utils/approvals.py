"""Approval enforcement helpers for mark-done workflows."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
_DEFAULT_CONFIG_RELATIVE = Path("assets") / "config" / "approval-policy.toml"


def approval_required() -> bool:
    """Return True when mark-done operations must capture approval metadata."""

    env_value = os.getenv("REQFLOW_REQUIRE_APPROVAL")
    if env_value is not None:
        parsed = _parse_bool(env_value)
        if parsed is None:
            raise ApprovalError(
                "REQFLOW_REQUIRE_APPROVAL must be boolean-like (true/false/1/0)."
            )
        return parsed

    config_path = _resolve_config_path()
    if config_path is not None:
        config_flag = _read_config_flag(config_path)
        if config_flag is not None:
            return config_flag

    return True


def _parse_bool(value: str) -> bool | None:
    normalised = value.strip().lower()
    if normalised in _TRUE_VALUES:
        return True
    if normalised in _FALSE_VALUES:
        return False
    return None


def _resolve_config_path() -> Path | None:
    override = os.getenv("REQFLOW_APPROVAL_CONFIG")
    if override:
        path = Path(override).expanduser()
        return path if path.exists() else None

    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / _DEFAULT_CONFIG_RELATIVE
        if candidate.exists():
            return candidate
    return None


def _read_config_flag(path: Path) -> bool | None:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - defensive guard
        raise ApprovalError(f"Failed to read approval config: {path}") from exc

    try:
        config = tomllib.loads(content)
    except tomllib.TOMLDecodeError as exc:
        raise ApprovalError(
            f"Invalid approval config at {path}: {exc.msg}"
        ) from exc

    for candidate in _iter_config_candidates(config):
        if candidate is None:
            continue
        if isinstance(candidate, bool):
            return candidate
        if isinstance(candidate, str):
            parsed = _parse_bool(candidate)
            if parsed is not None:
                return parsed
            raise ApprovalError(
                "Configuration value for wait-for-approval must be boolean-like."
            )
    return None


def _iter_config_candidates(config: dict[str, Any]) -> list[Any | None]:
    candidates: list[Any | None] = []

    wait_section = config.get("wait_for_approval")
    if isinstance(wait_section, dict):
        candidates.extend(
            [
                wait_section.get("require"),
                wait_section.get("require_approval"),
            ]
        )

    approval_section = config.get("approval")
    if isinstance(approval_section, dict):
        candidates.extend(
            [
                approval_section.get("require"),
                approval_section.get("require_approval"),
            ]
        )

    candidates.extend(
        [
            config.get("require"),
            config.get("require_approval"),
        ]
    )
    return candidates


@dataclass(slots=True)
class ApprovalContext:
    """Metadata captured for an approval event."""

    label: str
    overridden: bool = False


class ApprovalError(ValueError):
    """Raised when approval metadata is missing while enforcement is active."""


def validate_approval(
    *,
    approval_source: str | None,
    override: bool,
    command_name: str,
) -> ApprovalContext | None:
    """Validate approval metadata for *command_name* and return captured context.

    When approval is not required, the function returns ``None``. If approval is
    enforced, callers must supply either ``approval_source`` or ``override``.
    """

    if not approval_required():
        return None

    if approval_source and approval_source.strip():
        return ApprovalContext(label=approval_source.strip(), overridden=False)

    if override:
        return ApprovalContext(label="override", overridden=True)

    raise ApprovalError(
        (
            f"{command_name} requires --approval-source <value> or "
            "--override-wait-for-approval when approval enforcement is enabled."
        )
    )


try:  # pragma: no cover - standard library availability differs per Python version
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]
