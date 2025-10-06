from pathlib import Path

import pytest

from agentlab.cli import requirements as cli


@pytest.fixture()
def catalog_dir(tmp_path: Path) -> Path:
    requirements_dir = tmp_path / "docs" / "requirements"
    requirements_dir.mkdir(parents=True)

    functional = (
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
        "- Trace: prompts none, tests none, commits none\n\n"
        "## Satisfied Requirements\n"
    )
    (requirements_dir / "functional.md").write_text(functional, encoding="utf-8")

    non_functional = (
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
        "- Trace: prompts none, tests none, scripts none, monitors none\n\n"
        "## Satisfied Requirements\n"
    )
    (requirements_dir / "non-functional.md").write_text(non_functional, encoding="utf-8")

    log_header = (
        "# Requirements Change Log\n\n"
        "| Date (UTC) | Requirement ID | Change Summary | Author | Reference |\n"
        "|------------|----------------|----------------|--------|-----------|\n"
    )
    (requirements_dir / "log.md").write_text(log_header, encoding="utf-8")

    return requirements_dir


def test_cli_adds_functional_requirement_and_logs(catalog_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cli.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--author",
            "codex",
            "--reference",
            "prompt-42",
            "functional",
            "--title",
            "Handle partial prompts",
            "--owner",
            "product",
            "--narrative",
            "As an operator, I want partial prompts merged to avoid duplicates.",
            "--acceptance",
            "Given a partial prompt when it completes then the requirement is updated",
            "--acceptance",
            "Given repeated prompts when they match then only one requirement is added",
            "--trace-prompts",
            "prompt-42",
            "--trace-tests",
            "tests/reqflow/test_catalog.py",
            "--priority",
            "high",
        ]
    )

    captured = capsys.readouterr()
    assert "Recorded REQ-F-001" in captured.out

    catalog = (catalog_dir / "functional.md").read_text(encoding="utf-8")
    assert "- ID: REQ-F-001" in catalog
    assert "- Priority: high" in catalog
    assert "Active: 2 (proposed=2); Satisfied: 0" in catalog

    log = (catalog_dir / "log.md").read_text(encoding="utf-8")
    assert "REQ-F-001" in log
    assert "prompt-42" in log


def test_cli_adds_non_functional_requirement_and_logs(
    catalog_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--author",
            "codex",
            "--reference",
            "prompt-43",
            "non-functional",
            "--title",
            "Capture requirements under two seconds",
            "--owner",
            "platform",
            "--category",
            "performance",
            "--description",
            "Catalog updates should finish quickly to keep the loop responsive.",
            "--measurement",
            "Measured via scripts/smoke/requirements.py",
            "--trace-prompts",
            "prompt-43",
            "--priority",
            "low",
        ]
    )

    captured = capsys.readouterr()
    assert "Recorded REQ-NF-001" in captured.out

    catalog = (catalog_dir / "non-functional.md").read_text(encoding="utf-8")
    assert "- ID: REQ-NF-001" in catalog
    assert "- Priority: low" in catalog
    assert "Active: 2 (proposed=2); Satisfied: 0" in catalog

    log = (catalog_dir / "log.md").read_text(encoding="utf-8")
    assert "REQ-NF-001" in log
    assert "prompt-43" in log
