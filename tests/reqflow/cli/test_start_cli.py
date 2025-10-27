from pathlib import Path

import pytest

from reqflow.cli import start


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

    req_dir.joinpath("non-functional.md").write_text(
        "# Non-Functional Requirements\n\n"
        "<!-- STATUS-SUMMARY:START -->\n"
        "Todo: 1 (backlog=1); Done: 0; Retired: 0\n"
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
        "## Retired Requirements\n\n",
        encoding="utf-8",
    )

    return req_dir


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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

    functional = _read(catalog_dir / "functional.md")
    assert "- Status: doing" in functional
    assert "Todo: 1 (doing=1" in functional

    log_doc = _read(catalog_dir / "log.md")
    assert "Started implementation for REQ-F-100" in log_doc


def test_start_cli_blocks_when_primary_doing_exists(catalog_dir: Path) -> None:
    functional = catalog_dir / "functional.md"
    text = _read(functional).replace(
        "## Todo Requirements\n\n",
        "## Todo Requirements\n\n"
        "### REQ-F-050: Existing work in progress\n"
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
        start.main(
            [
                "--catalog-root",
                str(catalog_dir),
                "--requirement",
                "REQ-F-100",
            ]
        )
    assert exc.value.code == 2


def test_start_cli_allows_parallel_override(catalog_dir: Path) -> None:
    functional = catalog_dir / "functional.md"
    text = _read(functional).replace(
        "## Todo Requirements\n\n",
        "## Todo Requirements\n\n"
        "### REQ-F-050: Existing work in progress\n"
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

    exit_code = start.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--requirement",
            "REQ-F-100",
            "--allow-parallel",
        ]
    )
    assert exit_code == 0


def test_start_cli_requires_acknowledgement_for_collisions(
    catalog_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    functional = catalog_dir.joinpath("functional.md")
    text = _read(functional).replace(
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

    functional_doc = _read(functional)
    assert "### REQ-F-200: Completed example" in functional_doc
    assert "- Status: doing" in functional_doc
    assert "- Amends: REQ-F-100" in functional_doc

    log_doc = _read(catalog_dir / "log.md")
    assert "collisions: REQ-F-200" in log_doc
    assert "Reopened REQ-F-200 under REQ-F-100" in log_doc


def test_start_cli_requires_acknowledgement_for_related_suggestions(
    catalog_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    functional = catalog_dir / "functional.md"
    text = _read(functional).replace(
        "## Todo Requirements\n\n",
        ("## Todo Requirements\n\n"
         "### REQ-F-150: Shared component handling\n"
         "- Owner: product\n"
         "- Narrative: Ensure start CLI handles shared component prompts.\n"
         "- Acceptance Criteria:\n"
         "  * Placeholder shared component criterion\n"
         "- Priority: medium\n"
         "- Status: todo\n"
         "- Reason: pending\n"
         "- Trace: prompts none, tests none, commits none\n"
         "---\n\n") ,
        1,
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
    assert "REQ-F-150" in captured.err

    exit_code = start.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--requirement",
            "REQ-F-100",
            "--acknowledge-related",
        ]
    )
    assert exit_code == 0


def test_start_cli_reopens_related_amendments(catalog_dir: Path) -> None:
    functional = catalog_dir / "functional.md"
    text = _read(functional).replace(
        "## Todo Requirements\n\n",
        ("## Todo Requirements\n\n"
         "### REQ-F-150: Shared component handling\n"
         "- Owner: product\n"
         "- Narrative: Ensure start CLI handles shared component prompts.\n"
         "- Acceptance Criteria:\n"
         "  * Placeholder shared component criterion\n"
         "- Priority: medium\n"
         "- Status: todo\n"
         "- Reason: pending\n"
         "- Trace: prompts none, tests none, commits none\n"
         "---\n\n") ,
        1,
    )
    functional.write_text(text, encoding="utf-8")

    exit_code = start.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--requirement",
            "REQ-F-100",
            "--acknowledge-related",
            "--reopen-related",
            "REQ-F-150",
        ]
    )
    assert exit_code == 0

    functional_doc = _read(functional)
    assert "### REQ-F-150: Shared component handling" in functional_doc
    assert "- Status: doing" in functional_doc
    assert "- Amends: REQ-F-100" in functional_doc

    log_doc = _read(catalog_dir / "log.md")
    assert "related: REQ-F-150" in log_doc
    assert "Reopened REQ-F-150 under REQ-F-100" in log_doc


def test_start_cli_requires_acknowledgement_for_non_functional_suggestions(
    catalog_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    non_functional = catalog_dir / "non-functional.md"
    text = _read(non_functional).replace(
        "Maintain throughput checks for unrelated components.",
        "Ensure start CLI handles shared component traffic.",
    )
    non_functional.write_text(text, encoding="utf-8")

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
    assert "REQ-NF-300" in captured.err

    exit_code = start.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--requirement",
            "REQ-F-100",
            "--acknowledge-non-functional",
        ]
    )
    assert exit_code == 0


def test_start_cli_reopens_non_functional_amendments(catalog_dir: Path) -> None:
    non_functional = catalog_dir / "non-functional.md"
    text = _read(non_functional).replace(
        "Maintain throughput checks for unrelated components.",
        "Ensure start CLI handles shared component traffic.",
    )
    non_functional.write_text(text, encoding="utf-8")

    exit_code = start.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--requirement",
            "REQ-F-100",
            "--acknowledge-non-functional",
            "--reopen-non-functional",
            "REQ-NF-300",
        ]
    )
    assert exit_code == 0

    non_functional_doc = _read(non_functional)
    assert "- Status: doing" in non_functional_doc
    assert "- Amends: REQ-F-100" in non_functional_doc

    log_doc = _read(catalog_dir / "log.md")
    assert "Reopened REQ-NF-300 under REQ-F-100" in log_doc
