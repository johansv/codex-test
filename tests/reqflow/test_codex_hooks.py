from pathlib import Path

import re
import pytest

from reqflow.codex_hooks import before_task


@pytest.fixture()
def catalog_dir(tmp_path: Path) -> Path:
    requirements_dir = tmp_path / "docs" / "requirements"
    requirements_dir.mkdir(parents=True)

    requirements_dir.joinpath("functional.md").write_text(
        "# Functional Requirements\n\n"
        "<!-- STATUS-SUMMARY:START -->\n"
        "_No requirements recorded yet._\n"
        "<!-- STATUS-SUMMARY:END -->\n\n"
        "## Todo Requirements\n\n"
        "- ID: REQ-F-000\n"
        "- Title: Placeholder example\n"
        "- Owner: product\n"
        "- Narrative: Placeholder\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Priority: medium\n"
        "- Status: backlog\n"
        "- Trace: prompts none, tests none, commits none\n\n"
        "## Done Requirements\n\n",
        encoding="utf-8",
    )

    requirements_dir.joinpath("non-functional.md").write_text(
        "# Non-Functional Requirements\n\n"
        "<!-- STATUS-SUMMARY:START -->\n"
        "_No requirements recorded yet._\n"
        "<!-- STATUS-SUMMARY:END -->\n\n"
        "## Todo Requirements\n\n"
        "- ID: REQ-NF-000\n"
        "- Title: Placeholder example\n"
        "- Owner: platform\n"
        "- Category: reliability\n"
        "- Description: Placeholder description\n"
        "- Measurement: Manual review\n"
        "- Priority: medium\n"
        "- Status: backlog\n"
        "- Trace: prompts none, tests none, scripts none, monitors none\n\n"
        "## Done Requirements\n\n",
        encoding="utf-8",
    )

    requirements_dir.joinpath("log.md").write_text(
        "# Requirements Change Log\n\n"
        "| Date (UTC) | Requirement ID | Change Summary | Author | Reference |\n"
        "|------------|----------------|----------------|--------|-----------|\n",
        encoding="utf-8",
    )

    return requirements_dir


def test_before_task_creates_requirement_and_returns_metadata(catalog_dir: Path) -> None:
    task = {
        "prompt": "Handle incremental prompt updates",
        "reference": "prompt-501",
        "catalog_root": str(catalog_dir),
        "priority": "high",
    }

    result = before_task(task)

    assert result["requirement_id"].startswith("REQ-F-")
    assert result["priority"] == "high"
    assert result["reason"] == "pending"
    assert any("Recorded" in message and result["requirement_id"] in message for message in result["messages"])
    assert result.get("blocked") is None

    catalog = (catalog_dir / "functional.md").read_text(encoding="utf-8")
    heading = f"### {result['requirement_id']}:"
    assert any(line.startswith(heading) for line in catalog.splitlines())
    assert "- Priority: high" in catalog
    assert "- Reason: pending" in catalog


def test_before_task_marks_task_as_blocked_when_requirement_exists(catalog_dir: Path) -> None:
    functional = catalog_dir / "functional.md"
    functional.write_text(
        functional.read_text(encoding="utf-8")
        + "- ID: REQ-F-404\n"
        + "- Title: Handle incremental prompt updates\n"
        + "- Owner: product\n"
        + "- Narrative: existing\n"
        + "- Acceptance Criteria:\n"
        + "  * existing\n"
        + "- Priority: medium\n"
        + "- Status: todo\n"
        + "- Reason: pending\n"
        + "- Trace: prompts x, tests y, commits z\n\n",
        encoding="utf-8",
    )

    task = {
        "prompt": "handle incremental prompt updates",
        "reference": "prompt-502",
        "catalog_root": str(catalog_dir),
    }

    result = before_task(task)

    assert result["blocked"] is True
    assert result["requirement_id"] == "REQ-F-404"


def test_before_task_requires_prompt() -> None:
    with pytest.raises(ValueError):
        before_task({})
