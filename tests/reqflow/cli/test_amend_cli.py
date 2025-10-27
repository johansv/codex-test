from pathlib import Path

import pytest

from reqflow.cli import amend


@pytest.fixture()
def catalog_dir(tmp_path: Path) -> Path:
    req_dir = tmp_path / "docs" / "requirements"
    req_dir.mkdir(parents=True)

    req_dir.joinpath("functional.md").write_text(
        "# Functional Requirements\n\n"
        "<!-- STATUS-SUMMARY:START -->\n"
        "Todo: 0; Done: 1 (done=1); Retired: 0\n"
        "<!-- STATUS-SUMMARY:END -->\n\n"
        "## Todo Requirements\n\n"
        "## Done Requirements\n\n"
        "### REQ-F-100: Completed flow\n"
        "- Owner: product\n"
        "- Narrative: Completed feature implementation.\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Priority: medium\n"
        "- Status: done\n"
        "- Reason: implemented\n"
        "- Trace: prompts none, tests tests/dummy.py, commits none\n"
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


def test_amend_cli_reopens_requirement(catalog_dir: Path) -> None:
    exit_code = amend.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--requirement",
            "REQ-F-100",
            "--reason",
            "Correct acceptance criteria",
        ]
    )
    assert exit_code == 0

    functional = _read(catalog_dir / "functional.md")
    assert "- Status: doing" in functional
    assert "- Amends: REQ-F-100" in functional
    assert "Historic amendment in progress: Correct acceptance criteria" in functional

    log_doc = _read(catalog_dir / "log.md")
    assert "Reopened REQ-F-100 for historic amendment" in log_doc


def test_amend_cli_enforces_wip_guard(catalog_dir: Path) -> None:
    functional = catalog_dir / "functional.md"
    text = _read(functional).replace(
        "## Todo Requirements\n\n",
        "## Todo Requirements\n\n"
        "### REQ-F-050: Existing work\n"
        "- Owner: product\n"
        "- Narrative: Existing implementation work.\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Priority: medium\n"
        "- Status: doing\n"
        "- Reason: actively developing\n"
        "- Trace: prompts none, tests none, commits none\n"
        "---\n\n",
        1,
    )
    functional.write_text(text, encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        amend.main(
            [
                "--catalog-root",
                str(catalog_dir),
                "--requirement",
                "REQ-F-100",
                "--reason",
                "Fix typos",
            ]
        )
    assert exc.value.code == 2


def test_amend_cli_allows_parallel_override(catalog_dir: Path) -> None:
    functional = catalog_dir / "functional.md"
    text = _read(functional).replace(
        "## Todo Requirements\n\n",
        "## Todo Requirements\n\n"
        "### REQ-F-050: Existing work\n"
        "- Owner: product\n"
        "- Narrative: Existing implementation work.\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Priority: medium\n"
        "- Status: doing\n"
        "- Reason: actively developing\n"
        "- Trace: prompts none, tests none, commits none\n"
        "---\n\n",
        1,
    )
    functional.write_text(text, encoding="utf-8")

    exit_code = amend.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--requirement",
            "REQ-F-100",
            "--reason",
            "Fix typos",
            "--allow-parallel",
        ]
    )
    assert exit_code == 0
