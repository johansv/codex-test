from pathlib import Path

import pytest

from agentlab.utils.requirements import (
    FunctionalRequirement,
    NonFunctionalRequirement,
    append_functional_requirement,
    append_non_functional_requirement,
    generate_next_id,
)


@pytest.fixture()
def functional_catalog(tmp_path: Path) -> Path:
    content = (
        "# Functional Requirements\n\n"
        "## Active Requirements\n\n"
        "- ID: REQ-F-000\n"
        "- Title: Placeholder example\n"
        "- Owner: product\n"
        "- Narrative: Placeholder narrative\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder criterion\n"
        "- Status: proposed\n"
        "- Trace: prompts none, tests none, commits none\n\n"
        "## Satisfied Requirements\n"
    )
    path = tmp_path / "functional.md"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture()
def non_functional_catalog(tmp_path: Path) -> Path:
    content = (
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
        "## Satisfied Requirements\n"
    )
    path = tmp_path / "non-functional.md"
    path.write_text(content, encoding="utf-8")
    return path


def test_append_functional_requirement_appends_entry(functional_catalog: Path) -> None:
    requirement = FunctionalRequirement(
        title="Parse structured prompts",
        owner="product",
        narrative="As an operator, I want structured prompts so actions stay traceable.",
        acceptance_criteria=[
            "Given a prompt when it is logged then a requirement entry is created",
            "Given multiple prompts when they refer to the same capability then duplicates are avoided",
        ],
        trace_prompts="prompt-123",
        trace_tests="tests/agentlab/cli/test_requirements_cli.py",
    )

    req_id = append_functional_requirement(functional_catalog, requirement)

    text = functional_catalog.read_text(encoding="utf-8")
    assert req_id == "REQ-F-001"
    assert "- ID: REQ-F-001" in text
    assert text.index("- ID: REQ-F-001") < text.index("## Satisfied Requirements")
    assert "  * Given a prompt" in text


def test_append_non_functional_requirement_appends_entry(
    non_functional_catalog: Path,
) -> None:
    requirement = NonFunctionalRequirement(
        title="Sync catalog in under 2s",
        owner="platform",
        category="performance",
        description="Catalog updates should complete quickly for interactive sessions.",
        measurement="Manual timing via smoke test",
        trace_scripts="scripts/smoke/requirements.py",
    )

    req_id = append_non_functional_requirement(non_functional_catalog, requirement)

    text = non_functional_catalog.read_text(encoding="utf-8")
    assert req_id == "REQ-NF-001"
    assert "- ID: REQ-NF-001" in text
    assert text.index("- ID: REQ-NF-001") < text.index("## Satisfied Requirements")


def test_generate_next_id_advances_highest_number() -> None:
    contents = "REQ-F-002 and REQ-F-010 present"
    assert generate_next_id(contents, "REQ-F") == "REQ-F-011"
