from pathlib import Path

import pytest
import re

from reqflow.cli import dev


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


def test_dev_cli_creates_requirement(monkeypatch: pytest.MonkeyPatch, catalog_dir: Path) -> None:
    argv = [
        "--prompt",
        "handle incremental prompt updates",
        "--catalog-root",
        str(catalog_dir),
        "--reference",
        "prompt-401",
        "--priority",
        "high",
    ]

    exit_code = dev.main(argv)
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


def test_dev_cli_blocks_when_requirement_exists(monkeypatch: pytest.MonkeyPatch, catalog_dir: Path) -> None:
    functional = catalog_dir / "functional.md"
    functional.write_text(
        functional.read_text(encoding="utf-8")
        + "### REQ-F-300: Handle incremental prompt updates\n"
        + "- Owner: product\n"
        + "- Narrative: existing\n"
        + "- Acceptance Criteria:\n"
        + "  * existing\n"
        + "- Priority: medium\n"
        + "- Status: todo\n"
        + "- Reason: pending\n"
        + "- Trace: prompts x, tests y, commits z\n"
        + "---\n\n",
        encoding="utf-8",
    )

    argv = [
        "--prompt",
        "handle incremental prompt updates",
        "--catalog-root",
        str(catalog_dir),
        "--reference",
        "prompt-402",
    ]

    exit_code = dev.main(argv)
    assert exit_code == 1


def test_dev_cli_requires_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit):
        dev.main([])
