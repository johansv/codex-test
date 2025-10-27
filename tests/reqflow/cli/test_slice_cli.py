from pathlib import Path

import pytest

from reqflow.cli import slice as slice_cli


def _write_catalog(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


@pytest.fixture()
def catalog_dir(tmp_path: Path) -> Path:
    base = tmp_path / "docs" / "requirements"
    base.mkdir(parents=True)

    _write_catalog(
        base / "functional.md",
        "# Functional Requirements\n\n"
        "## Todo Requirements\n\n"
        "### REQ-F-100: Primary\n"
        "- Owner: product\n"
        "- Narrative: placeholder\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Priority: medium\n"
        "- Status: todo\n"
        "- Tags: ingest, latency\n"
        "- Reason: pending\n"
        "- Trace: prompts none, tests none, commits none\n"
        "---\n\n"
        "### REQ-F-101: Amendment\n"
        "- Owner: product\n"
        "- Narrative: placeholder\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Priority: medium\n"
        "- Status: todo\n"
        "- Amends: REQ-F-100\n"
        "- Reason: pending\n"
        "- Trace: prompts none, tests none, commits none\n"
        "---\n\n"
        "## Done Requirements\n\n"
        "### REQ-F-200: Archived\n"
        "- Owner: product\n"
        "- Narrative: placeholder\n"
        "- Acceptance Criteria:\n"
        "  * Placeholder\n"
        "- Priority: medium\n"
        "- Status: done\n"
        "- Reason: done\n"
        "- Trace: prompts none, tests none, commits none\n"
        "---\n\n"
        "## Retired Requirements\n\n"
        "_None_\n",
    )

    _write_catalog(
        base / "non-functional.md",
        "# Non-Functional Requirements\n\n"
        "## Todo Requirements\n\n"
        "### REQ-NF-300: Latency limit\n"
        "- Owner: platform\n"
        "- Category: performance\n"
        "- Description: Maintain low latency.\n"
        "- Measurement: Monitor p95\n"
        "- Priority: medium\n"
        "- Status: todo\n"
        "- Tags: latency, reliability\n"
        "- Reason: pending\n"
        "- Trace: prompts none, tests none, scripts none, monitors none\n"
        "---\n\n"
        "## Done Requirements\n\n"
        "## Retired Requirements\n\n"
        "_None_\n",
    )
    return base


def test_slice_cli_filters_by_id_and_includes_amendments(
    catalog_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = slice_cli.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--id",
            "REQ-F-100",
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "REQ-F-100" in captured.out
    assert "REQ-F-101" in captured.out  # linked amendment
    assert "REQ-F-200" not in captured.out
    assert "Functional Requirements" in captured.out


def test_slice_cli_filters_by_tag_across_catalogs(
    catalog_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = slice_cli.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--tag",
            "latency",
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "REQ-F-100" in captured.out
    assert "REQ-NF-300" in captured.out


def test_slice_cli_handles_no_matches(
    catalog_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = slice_cli.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--id",
            "REQ-F-999",
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "No matching requirements found." in captured.out
    summary_text = captured.out.split("# Summary")[-1]
    token_count = len(summary_text.split())
    assert token_count <= 260  # small buffer for formatting
