from pathlib import Path

import pytest

from agentlab.core.middleware import action_to_dict, auto_capture_prompt, should_block_for_manual_update


@pytest.fixture()
def catalog_dir(tmp_path: Path) -> Path:
    requirements_dir = tmp_path / "docs" / "requirements"
    requirements_dir.mkdir(parents=True)

    requirements_dir.joinpath("functional.md").write_text(
        "# Functional Requirements\n\n"
        "## Active Requirements\n\n"
        "- ID: REQ-F-000\n"
        "- Title: Placeholder example\n"
        "- Owner: product\n"
        "- Narrative: Placeholder\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Status: proposed\n"
        "- Trace: prompts none, tests none, commits none\n\n"
        "## Satisfied Requirements\n\n",
        encoding="utf-8",
    )

    requirements_dir.joinpath("non-functional.md").write_text(
        "# Non-Functional Requirements\n\n"
        "## Active Requirements\n\n"
        "- ID: REQ-NF-000\n"
        "- Title: Placeholder example\n"
        "- Owner: platform\n"
        "- Category: reliability\n"
        "- Description: Placeholder description\n"
        "- Measurement: Manual review\n"
        "- Status: proposed\n"
        "- Trace: prompts none, tests none, scripts none, monitors none\n\n"
        "## Satisfied Requirements\n\n",
        encoding="utf-8",
    )

    requirements_dir.joinpath("log.md").write_text(
        "# Requirements Change Log\n\n"
        "| Date (UTC) | Requirement ID | Change Summary | Author | Reference |\n"
        "|------------|----------------|----------------|--------|-----------|\n",
        encoding="utf-8",
    )

    return requirements_dir


def test_auto_capture_prompt_creates_requirement(catalog_dir: Path) -> None:
    action = auto_capture_prompt(
        "handle incremental prompt updates",
        reference="prompt-301",
        catalog_root=catalog_dir,
    )

    assert action.outcome == "created"
    assert action.requirement_id == "REQ-F-001"
    assert not should_block_for_manual_update(action)

    payload = action_to_dict(action)
    assert payload["outcome"] == "created"
    assert payload["kind"] == "functional"
    assert payload["adr_path"] is None


def test_auto_capture_prompt_detects_existing_requirement(catalog_dir: Path) -> None:
    functional = catalog_dir / "functional.md"
    functional.write_text(
        functional.read_text(encoding="utf-8")
        + "- ID: REQ-F-900\n"
        + "- Title: Handle incremental prompt updates\n"
        + "- Owner: product\n"
        + "- Narrative: placeholder\n"
        + "- Acceptance Criteria:\n"
        + "  * Placeholder\n"
        + "- Status: active\n"
        + "- Trace: prompts x, tests y, commits z\n\n",
        encoding="utf-8",
    )

    action = auto_capture_prompt(
        "handle incremental prompt updates",
        reference="prompt-302",
        catalog_root=catalog_dir,
    )

    assert action.outcome == "needs-update"
    assert should_block_for_manual_update(action)
