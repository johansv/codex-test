from pathlib import Path

import pytest

from agentlab.cli import start


@pytest.fixture()
def catalog_dir(tmp_path: Path) -> Path:
    req_dir = tmp_path / "docs" / "requirements"
    req_dir.mkdir(parents=True)

    req_dir.joinpath("functional.md").write_text(
        "# Functional Requirements\n\n"
        "<!-- STATUS-SUMMARY:START -->\n"
        "_No requirements recorded yet._\n"
        "<!-- STATUS-SUMMARY:END -->\n\n"
        "## Todo Requirements\n\n"
        "### REQ-F-100: Start CLI coverage\n"
        "- Owner: product\n"
        "- Narrative: Ensure start CLI promotes todo items.\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder acceptance criterion\n"
        "- Priority: medium\n"
        "- Status: todo\n"
        "- Reason: pending\n"
        "- Trace: prompts none, tests none, commits none\n"
        "---\n\n"
        "## Done Requirements\n\n"
        "### REQ-F-200: Completed example\n"
        "- Owner: product\n"
        "- Narrative: Completed processing of legacy exports.\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder done criterion\n"
        "- Priority: medium\n"
        "- Status: done\n"
        "- Reason: implemented\n"
        "- Trace: prompts none, tests none, commits none\n"
        "---\n\n"
        "## Retired Requirements\n\n",
        encoding="utf-8",
    )

    req_dir.joinpath("log.md").write_text(
        "# Requirements Change Log\n\n"
        "| Date (UTC) | Requirement ID | Change Summary | Author | Reference |\n"
        "|------------|----------------|----------------|--------|-----------|\n",
        encoding="utf-8",
    )

    return req_dir


def test_start_cli_promotes_requirement_without_collisions(catalog_dir: Path) -> None:
    exit_code = start.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--requirement",
            "REQ-F-100",
        ]
    )
    assert exit_code == 0

    functional = catalog_dir.joinpath("functional.md").read_text(encoding="utf-8")
    assert "- Status: doing" in functional
    assert "Todo: 1 (doing=1" in functional

    log_doc = catalog_dir.joinpath("log.md").read_text(encoding="utf-8")
    assert "Started implementation for REQ-F-100" in log_doc


def test_start_cli_rejects_non_todo_requirement(catalog_dir: Path) -> None:
    functional = catalog_dir.joinpath("functional.md")
    functional.write_text(
        functional.read_text(encoding="utf-8").replace("- Status: todo", "- Status: backlog"),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit):
        start.main(
            [
                "--catalog-root",
                str(catalog_dir),
                "--requirement",
                "REQ-F-100",
            ]
        )


def test_start_cli_requires_acknowledgement_for_collisions(
    catalog_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    functional = catalog_dir.joinpath("functional.md")
    text = functional.read_text(encoding="utf-8").replace(
        "Completed processing of legacy exports.",
        "Ensure start CLI promotes todo items.",
    )
    functional.write_text(text, encoding="utf-8")

    exit_code = start.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--requirement",
            "REQ-F-100",
        ]
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "REQ-F-200" in captured.err

    exit_code = start.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--requirement",
            "REQ-F-100",
            "--acknowledge-collisions",
        ]
    )
    assert exit_code == 0
    log_doc = catalog_dir.joinpath("log.md").read_text(encoding="utf-8")
    assert "collisions: REQ-F-200" in log_doc

