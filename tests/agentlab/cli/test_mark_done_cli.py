from pathlib import Path

import pytest

from agentlab.cli import mark_done as cli


@pytest.fixture()
def catalog_dir(tmp_path: Path) -> Path:
    requirements_dir = tmp_path / "docs" / "requirements"
    requirements_dir.mkdir(parents=True)

    functional = (
        "# Functional Requirements\n\n"
        "<!-- STATUS-SUMMARY:START -->\n"
        "Todo: 1 (todo=1); Done: 0; Retired: 0\n"
        "<!-- STATUS-SUMMARY:END -->\n\n"
        "## Todo Requirements\n\n"
        "### REQ-F-123: Sample requirement\n"
        "- Owner: codex\n"
        "- Narrative: Placeholder narrative\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Priority: medium\n"
        "- Status: todo\n"
        "- Reason: awaiting implementation\n"
        "- Trace: prompts R2, tests none, commits none\n"
        "---\n\n"
        "## Done Requirements\n\n"
        "## Retired Requirements\n"
    )
    (requirements_dir / "functional.md").write_text(functional, encoding="utf-8")

    log_header = (
        "# Requirements Change Log\n\n"
        "| Date (UTC) | Requirement ID | Change Summary | Author | Reference |\n"
        "|------------|----------------|----------------|--------|-----------|\n"
    )
    (requirements_dir / "log.md").write_text(log_header, encoding="utf-8")

    return requirements_dir


def test_mark_done_cli_marks_requirement_done(
    catalog_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--author",
            "dev",
            "--reference",
            "R2",
            "--id",
            "REQ-F-123",
            "--reason",
            "Implementation merged",
            "--tests",
            "tests/agentlab/cli/test_mark_done_cli.py",
            "--commits",
            "abc123",
        ]
    )

    captured = capsys.readouterr()
    assert "Marked REQ-F-123 done" in captured.out

    catalog = (catalog_dir / "functional.md").read_text(encoding="utf-8")
    assert "- Status: done" in catalog
    assert "- Reason: Implementation merged" in catalog
    expected_trace = (
        "- Trace: prompts R2, tests tests/agentlab/cli/test_mark_done_cli.py, "
        "commits abc123"
    )
    assert expected_trace in catalog
    assert "Todo: 0" in catalog
    assert "Done: 1 (done=1)" in catalog

    log = (catalog_dir / "log.md").read_text(encoding="utf-8")
    assert "REQ-F-123" in log
    assert "Implementation merged" in log


def test_mark_done_cli_errors_when_requirement_missing(catalog_dir: Path) -> None:
    initial_catalog = (catalog_dir / "functional.md").read_text(encoding="utf-8")
    initial_log = (catalog_dir / "log.md").read_text(encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        cli.main(
            [
                "--catalog-root",
                str(catalog_dir),
                "--id",
                "REQ-F-999",
                "--reason",
                "Missing implementation",
                "--tests",
                "tests/agentlab/cli/test_mark_done_cli.py",
            ]
        )
    assert exc.value.code == 2

    catalog = (catalog_dir / "functional.md").read_text(encoding="utf-8")
    log = (catalog_dir / "log.md").read_text(encoding="utf-8")
    assert catalog == initial_catalog
    assert log == initial_log


def test_mark_done_cli_closes_amendments(catalog_dir: Path) -> None:
    functional = catalog_dir / "functional.md"
    functional.write_text(
        "# Functional Requirements\n\n"
        "<!-- STATUS-SUMMARY:START -->\n"
        "Todo: 2 (doing=2); Done: 0; Retired: 0\n"
        "<!-- STATUS-SUMMARY:END -->\n\n"
        "## Todo Requirements\n\n"
        "### REQ-F-123: Primary feature\n"
        "- Owner: codex\n"
        "- Narrative: Primary implementation in progress.\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Priority: medium\n"
        "- Status: doing\n"
        "- Reason: implementing\n"
        "- Trace: prompts R2, tests pending, commits pending\n"
        "---\n\n"
        "### REQ-F-200: Dependent cleanup\n"
        "- Owner: codex\n"
        "- Narrative: Requires amendment alongside REQ-F-123.\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Priority: medium\n"
        "- Status: doing\n"
        "- Reason: awaiting amendment\n"
        "- Amends: REQ-F-123\n"
        "- Trace: prompts none, tests pending, commits none\n"
        "---\n\n"
        "## Done Requirements\n\n"
        "## Retired Requirements\n",
        encoding="utf-8",
    )

    exit_code = cli.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--id",
            "REQ-F-123",
            "--reason",
            "Primary and amendments completed",
            "--tests",
            "tests/agentlab/cli/test_mark_done_cli.py",
        ]
    )
    assert exit_code == 0

    catalog = (catalog_dir / "functional.md").read_text(encoding="utf-8")
    assert "### REQ-F-200: Dependent cleanup" in catalog
    assert "- Amends:" not in catalog
    assert "Amendment completed under REQ-F-123" in catalog
    assert "- Trace: prompts none, tests tests/agentlab/cli/test_mark_done_cli.py, commits none" in catalog
    assert "Todo: 0" in catalog
    assert "Done: 2" in catalog

    log = (catalog_dir / "log.md").read_text(encoding="utf-8")
    assert "Closed amendment REQ-F-200" in log

