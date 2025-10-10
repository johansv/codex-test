from pathlib import Path

import pytest

from agentlab.cli import batch


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
        "### REQ-F-100: Batch CLI coverage\n"
        "- Owner: product\n"
        "- Narrative: Ensure batch CLI reports overlaps.\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder acceptance criterion\n"
        "- Priority: medium\n"
        "- Status: todo\n"
        "- Reason: pending\n"
        "- Trace: prompts none, tests none, commits none\n"
        "---\n\n"
        "## Done Requirements\n\n"
        "### REQ-F-150: Shared component handling\n"
        "- Owner: product\n"
        "- Narrative: Ensure batch CLI handles shared component prompts.\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder shared component criterion\n"
        "- Priority: medium\n"
        "- Status: done\n"
        "- Reason: implemented\n"
        "- Trace: prompts none, tests none, commits none\n"
        "---\n\n"
        "### REQ-F-200: Completed example\n"
        "- Owner: product\n"
        "- Narrative: Ensure batch CLI promotes todo items.\n"
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

    req_dir.joinpath("non-functional.md").write_text(
        "# Non-Functional Requirements\n\n"
        "<!-- STATUS-SUMMARY:START -->\n"
        "Todo: 1 (backlog=1); Done: 1 (done=1); Retired: 0\n"
        "<!-- STATUS-SUMMARY:END -->\n\n"
        "## Todo Requirements\n\n"
        "### REQ-NF-300: Background throughput baseline\n"
        "- Owner: platform\n"
        "- Category: performance\n"
        "- Description: Maintain throughput checks for unrelated components.\n"
        "- Measurement: Manual review\n"
        "- Priority: medium\n"
        "- Status: backlog\n"
        "- Reason: pending\n"
        "- Trace: prompts none, tests none, scripts none, monitors none\n"
        "---\n\n"
        "## Done Requirements\n\n"
        "### REQ-NF-350: Completed perf profile\n"
        "- Owner: platform\n"
        "- Category: performance\n"
        "- Description: Completed processing of shared component throughput.\n"
        "- Measurement: Manual review\n"
        "- Priority: medium\n"
        "- Status: done\n"
        "- Reason: implemented\n"
        "- Trace: prompts none, tests none, scripts none, monitors none\n"
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


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_batch_cli_reports_without_reopening(catalog_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = batch.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--requirement",
            "REQ-F-100",
        ]
    )
    assert exit_code == 0

    functional_before = _read(catalog_dir / "functional.md")
    assert "- Status: todo" in functional_before

    captured = capsys.readouterr()
    assert "Batch preparation for REQ-F-100" in captured.out
    assert "Collisions" in captured.out


def test_batch_cli_auto_reopens_collisions_and_related(catalog_dir: Path) -> None:
    exit_code = batch.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--requirement",
            "REQ-F-100",
            "--auto-reopen-collisions",
            "--auto-reopen-related",
        ]
    )
    assert exit_code == 0

    functional = _read(catalog_dir / "functional.md")
    assert functional.count("- Amends: REQ-F-100") >= 1
    assert "- Status: doing" in functional

    log_doc = _read(catalog_dir / "log.md")
    assert "Batch preparation reopened" in log_doc
    assert "Reopened REQ-F-150" in log_doc


def test_batch_cli_auto_reopens_non_functional(catalog_dir: Path) -> None:
    # Make the non-functional item overlap strongly with the target requirement.
    non_functional = catalog_dir / "non-functional.md"
    text = _read(non_functional).replace(
        "Completed processing of shared component throughput.",
        "Ensure batch CLI handles shared component traffic.",
    )
    non_functional.write_text(text, encoding="utf-8")

    exit_code = batch.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--requirement",
            "REQ-F-100",
            "--auto-reopen-non-functional",
            "--non-functional-threshold",
            "0.2",
        ]
    )
    assert exit_code == 0

    nf_doc = _read(non_functional)
    assert "- Amends: REQ-F-100" in nf_doc
    assert "- Status: doing" in nf_doc

    log_doc = _read(catalog_dir / "log.md")
    assert "Reopened REQ-NF-350" in log_doc
