from pathlib import Path

import pytest

from reqflow.cli import bulk_amend


@pytest.fixture()
def catalog_dir(tmp_path: Path) -> Path:
    req_dir = tmp_path / "docs" / "requirements"
    req_dir.mkdir(parents=True)

    req_dir.joinpath("functional.md").write_text(
        "# Functional Requirements\n\n"
        "<!-- STATUS-SUMMARY:START -->\n"
        "Todo: 1 (doing=1); Done: 2 (done=2); Retired: 0\n"
        "<!-- STATUS-SUMMARY:END -->\n\n"
        "## Todo Requirements\n\n"
        "### REQ-F-001: Active primary\n"
        "- Owner: product\n"
        "- Narrative: Active work\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Priority: medium\n"
        "- Status: doing\n"
        "- Reason: In progress\n"
        "- Trace: prompts none, tests none, commits none\n"
        "---\n\n"
        "## Done Requirements\n\n"
        "### REQ-F-100: Completed component A\n"
        "- Owner: product\n"
        "- Narrative: Done item A\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Priority: medium\n"
        "- Status: done\n"
        "- Reason: implemented\n"
        "- Trace: prompts none, tests tests/a.py, commits none\n"
        "---\n\n"
        "### REQ-F-200: Completed component B\n"
        "- Owner: product\n"
        "- Narrative: Done item B\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Priority: medium\n"
        "- Status: done\n"
        "- Reason: implemented\n"
        "- Trace: prompts none, tests tests/b.py, commits none\n"
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


def test_bulk_amend_cli_reopens_and_logs(catalog_dir: Path) -> None:
    exit_code = bulk_amend.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--primary",
            "REQ-F-001",
            "--reason",
            "Update shared docs",
            "REQ-F-100",
            "REQ-F-200",
        ]
    )
    assert exit_code == 0

    functional = _read(catalog_dir / "functional.md")
    assert functional.count("- Amends: REQ-F-001") >= 2
    assert "Bulk amendment in progress under REQ-F-001: Update shared docs" in functional

    log_doc = _read(catalog_dir / "log.md")
    assert "Bulk reopened REQ-F-100 under REQ-F-001" in log_doc
    assert "Bulk reopened REQ-F-200 under REQ-F-001" in log_doc


def test_bulk_amend_cli_blocks_invalid_ids(catalog_dir: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        bulk_amend.main(
            [
                "--catalog-root",
                str(catalog_dir),
                "--primary",
                "REQ-F-001",
                "--reason",
                "Update shared docs",
                "REQ-F-999",
            ]
        )
    assert exc.value.code == 2


def test_bulk_amend_cli_allows_doing_override(catalog_dir: Path) -> None:
    functional = catalog_dir / "functional.md"
    text = _read(functional).replace(
        "## Todo Requirements\n\n",
        "## Todo Requirements\n\n"
        "### REQ-F-100: Already reopened\n"
        "- Owner: product\n"
        "- Narrative: Amendment work\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Priority: medium\n"
        "- Status: doing\n"
        "- Amends: REQ-F-001\n"
        "- Reason: Amendment in progress\n"
        "- Trace: prompts none, tests tests/a.py, commits none\n"
        "---\n\n",
        1,
    )
    functional.write_text(text, encoding="utf-8")

    exit_code = bulk_amend.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--primary",
            "REQ-F-001",
            "--reason",
            "Refresh metadata",
            "--allow-doing",
            "REQ-F-100",
        ]
    )
    assert exit_code == 0

    functional_doc = _read(functional)
    assert "Bulk amendment in progress under REQ-F-001: Refresh metadata" in functional_doc
