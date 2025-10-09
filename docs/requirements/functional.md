# Functional Requirements

<!-- STATUS-SUMMARY:START -->
Todo: 0; Done: 5 (done=5); Retired: 0
<!-- STATUS-SUMMARY:END -->

Maintain Codex-sourced functional requirements in this catalog.
Every entry should link back to its originating task or prompt and to verifying tests.

## How to capture a new requirement

Copy the template below, fill in each field, and place it under **Todo Requirements**.
Move fulfilled items to **Done Requirements** once implementation and tests merge.
Move rejected or replaced requirements to **Retired Requirements** so history is preserved.

```
### REQ-F-###: <short name>
- Owner: <person or team responsible>
- Narrative: As a <role>, I want <capability> so that <outcome>.
- Acceptance Criteria:
  * Given <context> when <action> then <result>.
  * Include as many bullet checks as needed.
- Priority: low | medium | high
- Status: backlog | todo | done | rejected | superseded
- Reason: why the current status applies (e.g., superseded by REQ-F-?)
- Trace: prompts <link>, tests <path>, commits <hash>
- Notes: optional clarifications or open questions.
---
```

## Todo Requirements

## Done Requirements

### REQ-F-20251009T095326-TT: Rename requirement statuses to backlog/todo/done
- Owner: codex
- Narrative: As a maintainer, I want the catalog and tooling to use backlog/todo/done so that our workflow aligns with kanban-inspired terminology.
- Acceptance Criteria:
  * Functional and non-functional templates list Backlog, Todo, Done, Rejected, Superseded.
  * Helpers, CLI defaults, and status validation use backlog/todo/done naming.
  * Existing catalog entries migrate from backlog/todo/done terminology consistently.
  * Tests and documentation referencing statuses are updated.
- Priority: medium
- Status: done
- Reason: Backlog terminology finished
- Trace: prompts R7, tests tests/reqflow/test_catalog.py, commits none
---

### REQ-F-20251007T083937-FA: CLI done transition helper
- Owner: codex
- Narrative: As a developer, I want a CLI command that marks requirements done so that catalog updates and trace data stay consistent without manual edits.
- Acceptance Criteria:
  * Command accepts a requirement ID plus reason, verifying test paths, and optional commits.
  * Functional catalog entry moves to done with status updated and trace fields refreshed.
  * Requirements change log records the transition details.
  * Mirrored CLI tests cover the behavior.
- Priority: medium
- Status: done
- Reason: Mark-done CLI implemented and tested
- Trace: prompts R2, tests tests/agentlab/cli/test_mark_done_cli.py; tests/reqflow/test_catalog.py, commits none
---

### REQ-F-20251008T130931-G0: Validate requirement capture inputs
- Owner: codex
- Narrative: As a workflow owner, I want requirement capture to enforce minimum structure so that catalog quality stays high.
- Acceptance Criteria:
  * CLI rejects functional requirements missing narrative role/capability/outcome cues.
  * CLI rejects functional requirements without at least one acceptance criterion.
  * CLI rejects functional requirements when all trace fields remain set to none.
  * Successful captures continue to write catalog entries and log updates.
  * Tests cover acceptance and failure scenarios for the validations.
  * Requirements template snippet reflects headings and separators.
- Priority: medium
- Status: done
- Reason: Capture validation guardrails implemented and tested
- Trace: prompts R3, tests tests/agentlab/cli/test_requirements_cli.py, commits none
---

### REQ-F-20251008T134255-33: Format requirement entries with headings
- Owner: codex
- Narrative: As a reviewer, I want catalog entries to start with a heading so that it is clear where each requirement begins and ends.
- Acceptance Criteria:
  * Functional requirements render with a Markdown heading containing ID and title.
  * Entries no longer list "- ID:"; the heading replaces it.
  * Entries end with a consistent separator.
  * CLI helpers and the mark-done command emit the new format.
  * Existing catalog entries migrate to the new format.
  * Tests cover the new layout for creation and completion paths.
- Priority: medium
- Status: done
- Reason: Catalog headings applied and helpers updated
- Trace: prompts R4, tests tests/agentlab/cli/test_requirements_cli.py; tests/agentlab/cli/test_mark_done_cli.py, commits none
---

### REQ-F-20251008T141440-87: Format non-functional requirement entries with headings
- Owner: codex
- Narrative: As a reviewer, I want non-functional requirements to use headings and separators so that both catalogs read consistently.
- Acceptance Criteria:
  * append_non_functional_requirement emits Markdown headings with id and title.
  * Non-functional entries end with a consistent separator.
  * Template snippet in docs/requirements/non-functional.md reflects the layout.
  * Existing catalog entries are migrated to the new format.
  * Tests covering non-functional captures assert the new headings.
  * Status summary counting still works for non-functional catalogs.
- Priority: medium
- Status: done
- Reason: Non-functional catalog headings implemented and tested
- Trace: prompts R5, tests tests/agentlab/cli/test_requirements_cli.py, commits none
---

## Retired Requirements


