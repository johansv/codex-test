from pathlib import Path

import pytest

from reqflow.cli import start_nonfunctional


@pytest.fixture()
def catalog_dir(tmp_path: Path) -> Path:
    req_dir = tmp_path / "docs" / "requirements"
    req_dir.mkdir(parents=True)

    req_dir.joinpath("non-functional.md").write_text(
        "# Non-Functional Requirements\n\n"
        "<!-- STATUS-SUMMARY:START -->\n"
        "Todo: 1 (todo=1); Done: 0; Retired: 0\n"
        "<!-- STATUS-SUMMARY:END -->\n\n"
        "## Todo Requirements\n\n"
        "### REQ-NF-100: Baseline\n"
        "- Owner: platform\n"
        "- Category: performance\n"
        "- Description: Ensure start-nf CLI promotes todo items.\n"
        "- Measurement: Manual\n"
        "- Priority: medium\n"
        "- Status: todo\n"
        "- Reason: pending\n"
        "- Trace: prompts none, tests none, scripts none, monitors none\n"
        "---\n\n"
        "## Done Requirements\n\n"
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


def test_start_nonfunctional_promotes_requirement(catalog_dir: Path) -> None:
    exit_code = start_nonfunctional.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--requirement",
            "REQ-NF-100",
        ]
    )
    assert exit_code == 0

    non_functional = _read(catalog_dir / "non-functional.md")
    assert "- Status: doing" in non_functional
    assert "Todo: 1 (doing=1" in non_functional

    log_doc = _read(catalog_dir / "log.md")
    assert "Started non-functional implementation for REQ-NF-100" in log_doc


def test_start_nonfunctional_blocks_when_primary_exists(catalog_dir: Path) -> None:
    non_functional = catalog_dir / "non-functional.md"
    text = _read(non_functional).replace(
        "## Todo Requirements\n\n",
        "## Todo Requirements\n\n"
        "### REQ-NF-050: Existing work\n"
        "- Owner: platform\n"
        "- Category: reliability\n"
        "- Description: Existing implementation work.\n"
        "- Measurement: Manual\n"
        "- Priority: medium\n"
        "- Status: doing\n"
        "- Reason: active\n"
        "- Trace: prompts none, tests none, scripts none, monitors none\n"
        "---\n\n",
        1,
    )
    non_functional.write_text(text, encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        start_nonfunctional.main(
            [
                "--catalog-root",
                str(catalog_dir),
                "--requirement",
                "REQ-NF-100",
            ]
        )
    assert exc.value.code == 2


def test_start_nonfunctional_allows_parallel_override(catalog_dir: Path) -> None:
    non_functional = catalog_dir / "non-functional.md"
    text = _read(non_functional).replace(
        "## Todo Requirements\n\n",
        "## Todo Requirements\n\n"
        "### REQ-NF-050: Existing work\n"
        "- Owner: platform\n"
        "- Category: reliability\n"
        "- Description: Existing implementation work.\n"
        "- Measurement: Manual\n"
        "- Priority: medium\n"
        "- Status: doing\n"
        "- Reason: active\n"
        "- Trace: prompts none, tests none, scripts none, monitors none\n"
        "---\n\n",
        1,
    )
    non_functional.write_text(text, encoding="utf-8")

    exit_code = start_nonfunctional.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--requirement",
            "REQ-NF-100",
            "--allow-parallel",
        ]
    )
    assert exit_code == 0
