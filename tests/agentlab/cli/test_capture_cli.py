from pathlib import Path

import pytest
import re

from agentlab.cli import capture


@pytest.fixture()
def catalog_dir(tmp_path: Path) -> Path:
    requirements_dir = tmp_path / "docs" / "requirements"
    requirements_dir.mkdir(parents=True)

    requirements_dir.joinpath("functional.md").write_text(
        "# Functional Requirements\n\n"
        "<!-- STATUS-SUMMARY:START -->\n"
        "_No requirements recorded yet._\n"
        "<!-- STATUS-SUMMARY:END -->\n\n"
        "## Active Requirements\n\n"
        "- ID: REQ-F-000\n"
        "- Title: Placeholder example\n"
        "- Owner: product\n"
        "- Narrative: Placeholder narrative\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Priority: medium\n"
        "- Status: proposed\n"
        "- Reason: pending\n"
        "- Trace: prompts none, tests none, commits none\n\n"
        "## Satisfied Requirements\n\n",
        encoding="utf-8",
    )

    requirements_dir.joinpath("non-functional.md").write_text(
        "# Non-Functional Requirements\n\n"
        "<!-- STATUS-SUMMARY:START -->\n"
        "_No requirements recorded yet._\n"
        "<!-- STATUS-SUMMARY:END -->\n\n"
        "## Active Requirements\n\n"
        "- ID: REQ-NF-000\n"
        "- Title: Placeholder example\n"
        "- Owner: platform\n"
        "- Category: reliability\n"
        "- Description: Placeholder description\n"
        "- Measurement: Manual review\n"
        "- Priority: medium\n"
        "- Status: proposed\n"
        "- Reason: pending\n"
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


def test_capture_cli_creates_requirement(monkeypatch: pytest.MonkeyPatch, catalog_dir: Path) -> None:
    argv = [
        "--prompt",
        "handle incremental prompt updates",
        "--catalog-root",
        str(catalog_dir),
        "--reference",
        "prompt-201",
        "--priority",
        "high",
    ]

    exit_code = capture.main(argv)
    assert exit_code == 0

    functional_doc = catalog_dir.joinpath("functional.md").read_text(encoding="utf-8")
    match = re.search(r"- ID: (REQ-F-\d{8}T\d{6}-[0-9A-Z]{2})", functional_doc)
    assert match is not None
    req_id = match.group(1)
    assert "- Priority: high" in functional_doc
    assert "- Reason: pending" in functional_doc
    assert "Active: 2 (proposed=2); Satisfied: 0; Retired: 0" in functional_doc

    log_doc = catalog_dir.joinpath("log.md").read_text(encoding="utf-8")
    assert req_id in log_doc
    assert "prompt-201" in log_doc


def test_capture_cli_generates_adr_for_architectural_prompt(
    monkeypatch: pytest.MonkeyPatch, catalog_dir: Path
) -> None:
    argv = [
        "--prompt",
        "Refactor the ingestion module architecture to introduce an event bus",
        "--catalog-root",
        str(catalog_dir),
        "--reference",
        "prompt-203",
    ]

    exit_code = capture.main(argv)
    assert exit_code == 0

    adr_dir = catalog_dir.parent / "adr"
    assert adr_dir.exists()
    adr_files = list(adr_dir.glob("*.md"))
    assert adr_files
    assert "Refactor the ingestion" in adr_files[0].read_text(encoding="utf-8")


def test_capture_cli_detects_existing_requirement(monkeypatch: pytest.MonkeyPatch, catalog_dir: Path) -> None:
    catalog_dir.joinpath("functional.md").write_text(
        catalog_dir.joinpath("functional.md").read_text(encoding="utf-8")
        + "- ID: REQ-F-050\n"
        + "- Title: Handle incremental prompts\n"
        + "- Owner: product\n"
        + "- Narrative: Existing narrative\n"
        + "- Acceptance Criteria:\n"
        + "  * Placeholder\n"
        + "- Priority: medium\n"
        + "- Status: active\n"
        + "- Reason: pending\n"
        + "- Trace: prompts p, tests t, commits c\n\n",
        encoding="utf-8",
    )

    argv = [
        "--prompt",
        "handle incremental prompts without duplication",
        "--catalog-root",
        str(catalog_dir),
        "--reference",
        "prompt-202",
    ]

    exit_code = capture.main(argv)
    assert exit_code == 1


def test_capture_cli_requires_single_prompt_source(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit):
        capture.main([
            "--prompt",
            "one",
            "--prompt-file",
            "two",
        ])
