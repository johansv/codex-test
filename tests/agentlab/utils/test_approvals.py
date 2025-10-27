from __future__ import annotations

from pathlib import Path

import pytest

from reqflow import approvals


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REQFLOW_REQUIRE_APPROVAL", raising=False)
    monkeypatch.delenv("REQFLOW_APPROVAL_CONFIG", raising=False)


def test_env_variable_enables_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQFLOW_REQUIRE_APPROVAL", "true")
    assert approvals.approval_required() is True


def test_env_variable_disables_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQFLOW_REQUIRE_APPROVAL", "no")
    assert approvals.approval_required() is False


def test_invalid_env_value_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQFLOW_REQUIRE_APPROVAL", "maybe")
    with pytest.raises(approvals.ApprovalError):
        approvals.approval_required()


def test_config_override_controls_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_env(monkeypatch)
    config = tmp_path / "approval.toml"
    config.write_text("[wait_for_approval]\nrequire = false\n", encoding="utf-8")
    monkeypatch.setenv("REQFLOW_APPROVAL_CONFIG", str(config))

    assert approvals.approval_required() is False


def test_missing_config_defaults_to_true(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("REQFLOW_APPROVAL_CONFIG", "nonexistent/path.toml")
    assert approvals.approval_required() is True


def test_invalid_config_value_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_env(monkeypatch)
    config = tmp_path / "approval.toml"
    config.write_text("[wait_for_approval]\nrequire = \"maybe\"\n", encoding="utf-8")
    monkeypatch.setenv("REQFLOW_APPROVAL_CONFIG", str(config))

    with pytest.raises(approvals.ApprovalError):
        approvals.approval_required()


def test_repository_config_applies_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_env(monkeypatch)
    assert approvals.approval_required() is True
