from pathlib import Path

import pytest

from agentlab.core.requirements_planner import RequirementPlanner, build_requirement_draft


@pytest.fixture()
def catalog_dir(tmp_path: Path) -> Path:
    req_dir = tmp_path / "docs" / "requirements"
    req_dir.mkdir(parents=True)

    req_dir.joinpath("functional.md").write_text(
        "# Functional Requirements\n\n"
        "## Active Requirements\n\n"
        "- ID: REQ-F-000\n"
        "- Title: Placeholder example\n"
        "- Owner: product\n"
        "- Narrative: Placeholder narrative\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Status: proposed\n"
        "- Trace: prompts none, tests none, commits none\n\n"
        "## Satisfied Requirements\n\n",
        encoding="utf-8",
    )

    req_dir.joinpath("non-functional.md").write_text(
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

    req_dir.joinpath("log.md").write_text(
        "# Requirements Change Log\n\n"
        "| Date (UTC) | Requirement ID | Change Summary | Author | Reference |\n"
        "|------------|----------------|----------------|--------|-----------|\n",
        encoding="utf-8",
    )

    return req_dir


def test_build_requirement_draft_classifies_functional() -> None:
    prompt = "add support for merging partial prompts from operators"
    draft = build_requirement_draft(prompt)
    assert draft.kind == "functional"
    assert draft.owner == "operator"
    assert draft.acceptance
    assert not draft.architectural


def test_build_requirement_draft_classifies_non_functional() -> None:
    prompt = "ensure prompt ingestion latency stays under two seconds"
    draft = build_requirement_draft(prompt)
    assert draft.kind == "non-functional"
    assert draft.category == "performance"
    assert draft.measurement is not None
    assert not draft.architectural


def test_build_requirement_draft_flags_architectural() -> None:
    prompt = "refactor the ingestion module architecture to introduce an event bus"
    draft = build_requirement_draft(prompt)
    assert draft.architectural is True


def test_requirement_planner_creates_new_requirement(tmp_path: Path, catalog_dir: Path) -> None:
    planner = RequirementPlanner(catalog_dir)
    prompt = "Handle incremental prompt updates\n- Given an incremental prompt then the system merges it"

    action = planner.ensure_requirement(
        prompt,
        reference="prompt-101",
        author="codex",
    )

    assert action.outcome == "created"
    assert action.requirement_id == "REQ-F-001"
    assert action.adr_path is None

    functional_doc = catalog_dir.joinpath("functional.md").read_text(encoding="utf-8")
    assert "- ID: REQ-F-001" in functional_doc

    log_doc = catalog_dir.joinpath("log.md").read_text(encoding="utf-8")
    assert "REQ-F-001" in log_doc
    assert "prompt-101" in log_doc


def test_requirement_planner_generates_adr_for_architectural_prompt(
    tmp_path: Path, catalog_dir: Path
) -> None:
    planner = RequirementPlanner(catalog_dir)
    prompt = "Refactor the ingestion module architecture to introduce an event bus"

    action = planner.ensure_requirement(
        prompt,
        reference="prompt-201",
        author="codex",
    )

    assert action.outcome == "created"
    assert action.requirement_id == "REQ-F-001"
    assert action.adr_path is not None
    assert action.adr_path.exists()
    assert action.adr_path.read_text(encoding="utf-8").startswith("# Refactor the ingestion")


def test_requirement_planner_detects_existing_requirement(catalog_dir: Path) -> None:
    functional = catalog_dir.joinpath("functional.md")
    functional.write_text(
        functional.read_text(encoding="utf-8")
        + "- ID: REQ-F-123\n"
        + "- Title: Handle incremental prompts\n"
        + "- Owner: product\n"
        + "- Narrative: Existing narrative\n"
        + "- Acceptance Criteria:\n"
        + "  * Existing\n"
        + "- Status: active\n"
        + "- Trace: prompts x, tests y, commits z\n\n",
        encoding="utf-8",
    )

    planner = RequirementPlanner(catalog_dir)
    prompt = "handle incremental prompts without duplication"

    action = planner.ensure_requirement(
        prompt,
        reference="prompt-102",
        author="codex",
    )

    assert action.outcome == "needs-update"
    assert action.requirement_id == "REQ-F-123"
    assert action.adr_path is None


def test_requirement_planner_dry_run_returns_without_changes(catalog_dir: Path) -> None:
    planner = RequirementPlanner(catalog_dir)
    prompt = "monitor prompt ingestion latency"

    action = planner.ensure_requirement(
        prompt,
        reference="prompt-103",
        author="codex",
        dry_run=True,
    )

    assert action.outcome == "dry-run"
    assert action.adr_path is None
    assert (
        catalog_dir.joinpath("non-functional.md").read_text(encoding="utf-8").count("REQ-NF-000")
        == 1
    )

    log_doc = catalog_dir.joinpath("log.md").read_text(encoding="utf-8")
    assert "prompt-103" not in log_doc
