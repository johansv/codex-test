from pathlib import Path

import pytest

from agentlab.cli import dev


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
        "- Narrative: Placeholder narrative\n"
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


def test_dev_cli_creates_requirement(monkeypatch: pytest.MonkeyPatch, catalog_dir: Path) -> None:
    argv = [
        "--prompt",
        "handle incremental prompt updates",
        "--catalog-root",
        str(catalog_dir),
        "--reference",
        "prompt-401",
    ]

    exit_code = dev.main(argv)
    assert exit_code == 0

    functional_doc = catalog_dir.joinpath("functional.md").read_text(encoding="utf-8")
    assert "REQ-F-001" in functional_doc


def test_dev_cli_blocks_when_requirement_exists(monkeypatch: pytest.MonkeyPatch, catalog_dir: Path) -> None:
    functional = catalog_dir / "functional.md"
    functional.write_text(
        functional.read_text(encoding="utf-8")
        + "- ID: REQ-F-300\n"
        + "- Title: Handle incremental prompt updates\n"
        + "- Owner: product\n"
        + "- Narrative: existing\n"
        + "- Acceptance Criteria:\n"
        + "  * existing\n"
        + "- Status: active\n"
        + "- Trace: prompts x, tests y, commits z\n\n",
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
