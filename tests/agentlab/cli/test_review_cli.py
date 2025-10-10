from pathlib import Path

import pytest

from agentlab.cli import review

def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


@pytest.fixture()
def catalog_dir(tmp_path: Path) -> Path:
    req_dir = tmp_path / "docs" / "requirements"
    req_dir.mkdir(parents=True)

    _write(
        req_dir / "functional.md",
        "# Functional Requirements\n\n"
        "<!-- STATUS-SUMMARY:START -->\n"
        "Todo: 1 (todo=1); Done: 1 (done=1); Retired: 0\n"
        "<!-- STATUS-SUMMARY:END -->\n\n"
        "## Todo Requirements\n\n"
        "### REQ-F-100: Example todo\n"
        "- Owner: product\n"
        "- Narrative: Prepare review CLI todo scenario.\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Priority: medium\n"
        "- Status: todo\n"
        "- Reason: Ready\n"
        "- Trace: prompts none, tests none, commits none\n"
        "---\n\n"
        "## Done Requirements\n\n"
        "### REQ-F-200: Example done\n"
        "- Owner: product\n"
        "- Narrative: Complete review CLI done scenario.\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Priority: medium\n"
        "- Status: done\n"
        "- Reason: Complete\n"
        "- Trace: prompts none, tests tests/sample.py, commits none\n"
        "---\n\n"
        "## Retired Requirements\n\n",
    )

    repo_root = req_dir.parent

    (repo_root / "tests").mkdir(parents=True, exist_ok=True)
    (repo_root / "tests" / "sample.py").write_text("# sample test\n", encoding="utf-8")

    _write(
        req_dir / "non-functional.md",
        "# Non-Functional Requirements\n\n"
        "<!-- STATUS-SUMMARY:START -->\n"
        "Todo: 1 (todo=1); Done: 0; Retired: 0\n"
        "<!-- STATUS-SUMMARY:END -->\n\n"
        "## Todo Requirements\n\n"
        "### REQ-NF-300: Latency baseline\n"
        "- Owner: platform\n"
        "- Category: performance\n"
        "- Description: Validate non-functional checks.\n"
        "- Measurement: Monitored via scripts\n"
        "- Priority: medium\n"
        "- Status: todo\n"
        "- Reason: Ready\n"
        "- Trace: prompts none, tests none, scripts scripts/monitor.py, monitors none\n"
        "---\n\n"
        "## Done Requirements\n\n"
        "## Retired Requirements\n\n",
    )
    (repo_root / "scripts").mkdir(parents=True, exist_ok=True)
    (repo_root / "scripts" / "monitor.py").write_text("# monitor\n", encoding="utf-8")

    return req_dir


def test_review_cli_reports_success(catalog_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = review.main(
        [
            "--catalog-root",
            str(catalog_dir),
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "No blocking issues" in captured.out


def test_review_cli_detects_missing_files(catalog_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Remove the referenced test file to simulate drift.
    (catalog_dir.parent / "tests" / "sample.py").unlink()

    exit_code = review.main(
        [
            "--catalog-root",
            str(catalog_dir),
        ]
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "references missing tests file" in captured.err


def test_review_cli_detects_multiple_doing(catalog_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    functional = catalog_dir / "functional.md"
    text = functional.read_text(encoding="utf-8").replace(
        "- Status: todo",
        "- Status: doing",
        1,
    )
    text = text.replace(
        "## Todo Requirements\n\n",
        "## Todo Requirements\n\n"
        "### REQ-F-150: Another doing\n"
        "- Owner: product\n"
        "- Narrative: Duplicate doing entry.\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Priority: medium\n"
        "- Status: doing\n"
        "- Reason: Active\n"
        "- Trace: prompts none, tests none, commits none\n"
        "---\n\n",
        1,
    )
    functional.write_text(text, encoding="utf-8")

    exit_code = review.main(
        [
            "--catalog-root",
            str(catalog_dir),
        ]
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "multiple primary requirements" in captured.err
