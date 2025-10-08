from pathlib import Path

import pytest
import re

from agentlab.cli import requirements as cli


@pytest.fixture()
def catalog_dir(tmp_path: Path) -> Path:
    requirements_dir = tmp_path / "docs" / "requirements"
    requirements_dir.mkdir(parents=True)

    functional = (
        "# Functional Requirements\n\n"
        "<!-- STATUS-SUMMARY:START -->\n"
        "Active: 1 (proposed=1); Satisfied: 0; Retired: 0\n"
        "<!-- STATUS-SUMMARY:END -->\n\n"
        "## Active Requirements\n\n"
        "### REQ-F-000: Placeholder example\n"
        "- Owner: product\n"
        "- Narrative: Placeholder narrative\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Priority: medium\n"
        "- Status: proposed\n"
        "- Reason: pending\n"
        "- Trace: prompts none, tests none, commits none\n"
        "---\n\n"
        "## Satisfied Requirements\n\n"
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
        "- Reason: pending\n"
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
            "As an operator, I want partial prompts merged so that duplicates are avoided.",
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
            "--reason",
            "initial capture",
        ]
    )

    captured = capsys.readouterr()
    match = re.search(r"Recorded (REQ-F-\d{8}T\d{6}-[0-9A-Z]{2})", captured.out)
    assert match is not None
    req_id = match.group(1)

    catalog = (catalog_dir / "functional.md").read_text(encoding="utf-8")
    assert f"### {req_id}: Handle partial prompts" in catalog
    assert "- Priority: high" in catalog
    assert "- Reason: initial capture" in catalog
    assert "Active: 2 (proposed=2); Satisfied: 0; Retired: 0" in catalog

    log = (catalog_dir / "log.md").read_text(encoding="utf-8")
    assert req_id in log
    assert "prompt-42" in log




def test_cli_rejects_functional_without_structured_narrative(
    catalog_dir: Path,
) -> None:
    catalog_path = catalog_dir / "functional.md"
    before = catalog_path.read_text(encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        cli.main(
            [
                "--catalog-root",
                str(catalog_dir),
                "functional",
                "--title",
                "Missing narrative structure",
                "--owner",
                "product",
                "--narrative",
                "This requirement has no template",
                "--acceptance",
                "Given data when processed then it is stored",
                "--trace-tests",
                "tests/agentlab/cli/test_requirements_cli.py",
            ]
        )
    assert exc.value.code == 2
    after = catalog_path.read_text(encoding="utf-8")
    assert after == before


def test_cli_rejects_functional_without_acceptance(
    catalog_dir: Path,
) -> None:
    catalog_path = catalog_dir / "functional.md"
    before = catalog_path.read_text(encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        cli.main(
            [
                "--catalog-root",
                str(catalog_dir),
                "functional",
                "--title",
                "Missing acceptance",
                "--owner",
                "product",
                "--narrative",
                "As a user, I want linting so that quality stays high.",
                "--acceptance",
                "   ",
                "--trace-tests",
                "tests/agentlab/cli/test_requirements_cli.py",
            ]
        )
    assert exc.value.code == 2
    after = catalog_path.read_text(encoding="utf-8")
    assert after == before


def test_cli_rejects_functional_without_trace_details(
    catalog_dir: Path,
) -> None:
    catalog_path = catalog_dir / "functional.md"
    before = catalog_path.read_text(encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        cli.main(
            [
                "--catalog-root",
                str(catalog_dir),
                "functional",
                "--title",
                "Missing trace",
                "--owner",
                "product",
                "--narrative",
                "As a reviewer, I want traceability so that I can audit changes.",
                "--acceptance",
                "Given inputs when validated then results are stored",
            ]
        )
    assert exc.value.code == 2
    after = catalog_path.read_text(encoding="utf-8")
    assert after == before

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
            "--reason",
            "latency target",
        ]
    )

    captured = capsys.readouterr()
    match = re.search(r"Recorded (REQ-NF-\d{8}T\d{6}-[0-9A-Z]{2})", captured.out)
    assert match is not None
    req_id = match.group(1)

    catalog = (catalog_dir / "non-functional.md").read_text(encoding="utf-8")
    assert f"- ID: {req_id}" in catalog
    assert "- Priority: low" in catalog
    assert "- Reason: latency target" in catalog
    assert "Active: 2 (proposed=2); Satisfied: 0; Retired: 0" in catalog

    log = (catalog_dir / "log.md").read_text(encoding="utf-8")
    assert req_id in log
    assert "prompt-43" in log
