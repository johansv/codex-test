from pathlib import Path

import pytest
import re

from reqflow.catalog import (
    FunctionalRequirement,
    NonFunctionalRequirement,
    append_functional_requirement,
    append_non_functional_requirement,
    begin_historic_amendment,
    generate_next_id,
)


@pytest.fixture()
def functional_catalog(tmp_path: Path) -> Path:
    content = (
        "# Functional Requirements\n\n"
        "<!-- STATUS-SUMMARY:START -->\n"
        "_No requirements recorded yet._\n"
        "<!-- STATUS-SUMMARY:END -->\n\n"
        "## Todo Requirements\n\n"
        "- ID: REQ-F-000\n"
        "- Title: Placeholder example\n"
        "- Owner: product\n"
        "- Narrative: Placeholder narrative\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder criterion\n"
        "- Priority: medium\n"
        "- Status: backlog\n"
        "- Trace: prompts none, tests none, commits none\n\n"
        "## Done Requirements\n"
    )
    path = tmp_path / "functional.md"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture()
def non_functional_catalog(tmp_path: Path) -> Path:
    content = (
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
        "## Done Requirements\n"
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
    assert req_id.startswith("REQ-F-")
    heading = f"### {req_id}: Parse structured prompts"
    assert heading in text
    assert text.index(heading) < text.index("## Done Requirements")
    assert "- Priority: medium" in text
    assert "- Reason: pending" in text
    assert "  * Given a prompt" in text
    assert "Todo: 2 (backlog=2); Done: 0; Retired: 0" in text


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
    assert req_id.startswith("REQ-NF-")
    heading = f"### {req_id}: Sync catalog in under 2s"
    assert heading in text
    assert text.index(heading) < text.index("## Done Requirements")
    assert "- Priority: medium" in text
    assert "- Reason: pending" in text
    assert "Todo: 2 (backlog=2); Done: 0; Retired: 0" in text


def test_generate_next_id_advances_highest_number() -> None:
    contents = ""
    new_id = generate_next_id(contents, "REQ-F")
    assert re.fullmatch(r"REQ-F-\d{8}T\d{6}-[0-9A-Z]{2}", new_id)


def test_begin_historic_amendment_moves_done_requirement(tmp_path: Path) -> None:
    catalog = tmp_path / "functional.md"
    catalog.write_text(
        "# Functional Requirements\n\n"
        "<!-- STATUS-SUMMARY:START -->\n"
        "Todo: 0; Done: 1 (done=1); Retired: 0\n"
        "<!-- STATUS-SUMMARY:END -->\n\n"
        "## Todo Requirements\n\n"
        "## Done Requirements\n\n"
        "### REQ-F-100: Completed flow\n"
        "- Owner: product\n"
        "- Narrative: Completed feature implementation.\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Priority: medium\n"
        "- Status: done\n"
        "- Reason: implemented\n"
        "- Trace: prompts none, tests tests/dummy.py, commits none\n"
        "---\n\n"
        "## Retired Requirements\n\n",
        encoding="utf-8",
    )

    begin_historic_amendment(
        catalog,
        req_id="REQ-F-100",
        amendment_reason="Correct acceptance criteria wording",
    )

    contents = catalog.read_text(encoding="utf-8")
    todo_index = contents.index("## Todo Requirements")
    done_index = contents.index("## Done Requirements")
    todo_section = contents[todo_index:done_index]
    assert "- Status: doing" in todo_section
    assert "- Amends: REQ-F-100" in todo_section
    assert "Historic amendment in progress: Correct acceptance criteria wording" in todo_section
    assert "Todo: 1 (doing=1" in contents


def test_begin_historic_amendment_respects_wip_guard(tmp_path: Path) -> None:
    catalog = tmp_path / "functional.md"
    catalog.write_text(
        "# Functional Requirements\n\n"
        "<!-- STATUS-SUMMARY:START -->\n"
        "Todo: 1 (doing=1); Done: 1 (done=1); Retired: 0\n"
        "<!-- STATUS-SUMMARY:END -->\n\n"
        "## Todo Requirements\n\n"
        "### REQ-F-050: In progress\n"
        "- Owner: product\n"
        "- Narrative: Existing work\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Priority: medium\n"
        "- Status: doing\n"
        "- Reason: active\n"
        "- Trace: prompts none, tests none, commits none\n"
        "---\n\n"
        "## Done Requirements\n\n"
        "### REQ-F-100: Completed flow\n"
        "- Owner: product\n"
        "- Narrative: Completed feature implementation.\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Priority: medium\n"
        "- Status: done\n"
        "- Reason: implemented\n"
        "- Trace: prompts none, tests tests/dummy.py, commits none\n"
        "---\n\n"
        "## Retired Requirements\n\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Another primary requirement is already in progress"):
        begin_historic_amendment(
            catalog,
            req_id="REQ-F-100",
            amendment_reason="Fix typos",
        )


def test_begin_historic_amendment_requires_reason(tmp_path: Path) -> None:
    catalog = tmp_path / "functional.md"
    catalog.write_text(
        "# Functional Requirements\n\n"
        "<!-- STATUS-SUMMARY:START -->\n"
        "Todo: 0; Done: 1 (done=1); Retired: 0\n"
        "<!-- STATUS-SUMMARY:END -->\n\n"
        "## Todo Requirements\n\n"
        "## Done Requirements\n\n"
        "### REQ-F-100: Completed flow\n"
        "- Owner: product\n"
        "- Narrative: Completed feature implementation.\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Priority: medium\n"
        "- Status: done\n"
        "- Reason: implemented\n"
        "- Trace: prompts none, tests tests/dummy.py, commits none\n"
        "---\n\n"
        "## Retired Requirements\n\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Provide a non-empty amendment reason"):
        begin_historic_amendment(
            catalog,
            req_id="REQ-F-100",
            amendment_reason="   ",
        )
