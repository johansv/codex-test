from pathlib import Path

import pytest

from agentlab.cli import doc_refactor


@pytest.fixture()
def catalog_dir(tmp_path: Path) -> Path:
    req_dir = tmp_path / "docs" / "requirements"
    req_dir.mkdir(parents=True)

    (req_dir / "functional.md").write_text(
        """# Functional Requirements

<!-- STATUS-SUMMARY:START -->
Todo: 1 (todo=1); Done: 1 (done=1); Retired: 0
<!-- STATUS-SUMMARY:END -->

## Todo Requirements

### REQ-F-100: Update docs
- Owner: codex
- Narrative: Update shared docs.
- Acceptance Criteria:
  * Placeholder
- Priority: medium
- Status: todo
- Reason: pending
- Trace: prompts none, tests none, commits none
---

## Done Requirements

### REQ-F-200: Previous docs
- Owner: codex
- Narrative: Update shared docs reference.
- Acceptance Criteria:
  * Placeholder
- Priority: medium
- Status: done
- Reason: done
- Trace: prompts none, tests none, commits none
---

## Retired Requirements

_None_
""",
        encoding="utf-8",
    )

    (req_dir / "non-functional.md").write_text(
        """# Non-Functional Requirements

<!-- STATUS-SUMMARY:START -->
Todo: 1 (todo=1); Done: 0; Retired: 0
<!-- STATUS-SUMMARY:END -->

## Todo Requirements

### REQ-NF-300: Docs availability
- Owner: platform
- Category: reliability
- Description: Ensure docs stay consistent.
- Measurement: Manual review
- Priority: medium
- Status: todo
- Reason: pending
- Trace: prompts none, tests none, scripts none, monitors none
---

## Done Requirements

## Retired Requirements

_None_
""",
        encoding="utf-8",
    )

    return req_dir


def test_doc_refactor_requires_acknowledgement(catalog_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = doc_refactor.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--requirement",
            "REQ-F-100",
        ]
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Overlaps detected" in captured.out


def test_doc_refactor_allows_acknowledge(catalog_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = doc_refactor.main(
        [
            "--catalog-root",
            str(catalog_dir),
            "--requirement",
            "REQ-F-100",
            "--acknowledge",
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Overlaps acknowledged" in captured.out


def test_doc_refactor_errors_when_missing_requirement(catalog_dir: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        doc_refactor.main(
            [
                "--catalog-root",
                str(catalog_dir),
                "--requirement",
                "REQ-F-999",
            ]
        )
    assert exc.value.code == 2
