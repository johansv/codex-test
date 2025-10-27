from pathlib import Path

import pytest
import re

from reqflow.cli import capture


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
        "### REQ-F-000: Placeholder example\n"
        "- Owner: product\n"
        "- Narrative: Placeholder narrative\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Priority: medium\n"
        "- Status: backlog\n"
        "- Reason: pending\n"
        "- Trace: prompts none, tests none, commits none\n"
        "---\n\n"
        "## Done Requirements\n\n"
    ,
        encoding="utf-8",
    )
    requirements_dir.joinpath("non-functional.md").write_text(
        "# Non-Functional Requirements\n\n"
        "<!-- STATUS-SUMMARY:START -->\n"
        "_No requirements recorded yet._\n"
        "<!-- STATUS-SUMMARY:END -->\n\n"
        "## Todo Requirements\n\n"
        "### REQ-NF-000: Placeholder example\n"
        "- Owner: platform\n"
        "- Category: reliability\n"
        "- Description: Placeholder description\n"
        "- Measurement: Manual review\n"
        "- Priority: medium\n"
        "- Status: backlog\n"
        "- Reason: pending\n"
        "- Trace: prompts none, tests none, scripts none, monitors none\n"
        "---\n\n"
        "## Done Requirements\n\n"
    ,
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

    log_doc = catalog_dir.joinpath("log.md").read_text(encoding="utf-8")
    match = re.search(r"(REQ-F-\d{8}T\d{6}-[0-9A-Z]{2})", log_doc)
    assert match is not None
    req_id = match.group(1)

    functional_doc = catalog_dir.joinpath("functional.md").read_text(encoding="utf-8")
    assert f"### {req_id}:" in functional_doc
    assert "- Priority: high" in functional_doc
    assert "- Reason: pending" in functional_doc
    assert "Todo: 2 (backlog=2); Done: 0; Retired: 0" in functional_doc

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
        + "### REQ-F-050: Handle incremental prompts\n"
        + "- Owner: product\n"
        + "- Narrative: Existing narrative\n"
        + "- Acceptance Criteria:\n"
        + "  * Placeholder\n"
        + "- Priority: medium\n"
        + "- Status: todo\n"
        + "- Reason: pending\n"
        + "- Trace: prompts p, tests t, commits c\n"
        + "---\n\n",
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
