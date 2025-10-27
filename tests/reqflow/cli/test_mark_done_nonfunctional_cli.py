from pathlib import Path

import pytest

from reqflow.cli import mark_done_nonfunctional


@pytest.fixture()
def catalog_dir(tmp_path: Path) -> Path:
    req_dir = tmp_path / "docs" / "requirements"
    req_dir.mkdir(parents=True)

    req_dir.joinpath("non-functional.md").write_text(
        "# Non-Functional Requirements\n\n"
        "<!-- STATUS-SUMMARY:START -->\n"
        "Todo: 1 (todo=1); Done: 1 (done=1); Retired: 0\n"
        "<!-- STATUS-SUMMARY:END -->\n\n"
        "## Todo Requirements\n\n"
        "### REQ-NF-100: Latency budget\n"
        "- Owner: platform\n"
        "- Category: performance\n"
        "- Description: Maintain latency SLA.\n"
        "- Measurement: Synthetic monitor\n"
        "- Priority: medium\n"
        "- Status: todo\n"
        "- Reason: pending\n"
        "- Trace: prompts none, tests none, scripts scripts/latency.py, monitors monitors/latency.json\n"
        "---\n\n"
        "## Done Requirements\n\n"
        "### REQ-NF-200: Historical record\n"
        "- Owner: platform\n"
        "- Category: performance\n"
        "- Description: Completed baseline\n"
        "- Measurement: Synthetic monitor\n"
        "- Priority: medium\n"
        "- Status: done\n"
        "- Reason: implemented\n"
        "- Trace: prompts none, tests tests/existing.py, scripts scripts/historical.py, monitors monitors/history.json\n"
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

    repo_root = req_dir.parent
    (repo_root / "scripts").mkdir(parents=True, exist_ok=True)
    (repo_root / "scripts" / "latency.py").write_text("# latency script\n", encoding="utf-8")
    (repo_root / "scripts" / "historical.py").write_text("# historical\n", encoding="utf-8")
    (repo_root / "tests").mkdir(parents=True, exist_ok=True)
    (repo_root / "tests" / "existing.py").write_text("# existing test\n", encoding="utf-8")
    (repo_root / "monitors").mkdir(parents=True, exist_ok=True)
    (repo_root / "monitors" / "latency.json").write_text("{}", encoding="utf-8")
    (repo_root / "monitors" / "history.json").write_text("{}", encoding="utf-8")

    return req_dir


@pytest.fixture(autouse=True)
def enforce_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQFLOW_REQUIRE_APPROVAL", "true")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_mark_done_nonfunctional_updates_catalog(catalog_dir: Path) -> None:
    exit_code = mark_done_nonfunctional.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--id",
            "REQ-NF-100",
            "--reason",
            "Latency SLA validated",
            "--tests",
            "tests/latency_probe.py",
            "--scripts",
            "scripts/latency.py",
            "--monitors",
            "monitors/latency.json",
            "--approval-source",
            "platform-lead",
        ]
    )
    assert exit_code == 0

    non_functional = _read(catalog_dir / "non-functional.md")
    assert "### REQ-NF-100: Latency budget" in non_functional
    assert "- Status: done" in non_functional
    assert "Latency SLA validated" in non_functional
    assert "tests tests/latency_probe.py" in non_functional
    assert "scripts scripts/latency.py" in non_functional

    log_doc = _read(catalog_dir / "log.md")
    assert "Marked REQ-NF-100 done" in log_doc


def test_mark_done_nonfunctional_requires_artifact(catalog_dir: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        mark_done_nonfunctional.main(
            [
                "--catalog-root",
                str(catalog_dir),
                "--id",
                "REQ-NF-100",
                "--reason",
                "Missing artifacts",
                "--approval-source",
                "platform-lead",
            ]
        )
    assert exc.value.code == 2


def test_mark_done_nonfunctional_requires_approval(catalog_dir: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        mark_done_nonfunctional.main(
            [
                "--catalog-root",
                str(catalog_dir),
                "--id",
                "REQ-NF-100",
                "--reason",
                "Missing approval metadata",
                "--tests",
                "tests/latency_probe.py",
            ]
        )
    assert exc.value.code == 2


def test_mark_done_nonfunctional_supports_override(catalog_dir: Path) -> None:
    exit_code = mark_done_nonfunctional.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--id",
            "REQ-NF-100",
            "--reason",
            "Override approval granted",
            "--tests",
            "tests/latency_probe.py",
            "--override-wait-for-approval",
        ]
    )
    assert exit_code == 0
