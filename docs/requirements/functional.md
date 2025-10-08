# Functional Requirements

<!-- STATUS-SUMMARY:START -->
Active: 0; Satisfied: 3 (satisfied=3); Retired: 0
<!-- STATUS-SUMMARY:END -->

Maintain Codex-sourced functional requirements in this catalog.
Every entry should link back to its originating task or prompt and to verifying tests.

## How to capture a new requirement

Copy the template below, fill in each field, and place it under **Active Requirements**.
Move fulfilled items to **Satisfied Requirements** once implementation and tests merge.
Move rejected or replaced requirements to **Retired Requirements** so history is preserved.

```
### REQ-F-###: <short name>
- Owner: <person or team responsible>
- Narrative: As a <role>, I want <capability> so that <outcome>.
- Acceptance Criteria:
  * Given <context> when <action> then <result>.
  * Include as many bullet checks as needed.
- Priority: low | medium | high
- Status: proposed | active | satisfied | rejected | superseded
- Reason: why the current status applies (e.g., superseded by REQ-F-?)
- Trace: prompts <link>, tests <path>, commits <hash>
- Notes: optional clarifications or open questions.
---
```

## Active Requirements

## Satisfied Requirements

### REQ-F-20251007T083937-FA: CLI satisfied transition helper
- Owner: codex
- Narrative: As a developer, I want a CLI command that marks requirements satisfied so that catalog updates and trace data stay consistent without manual edits.
- Acceptance Criteria:
  * Command accepts a requirement ID plus reason, verifying test paths, and optional commits.
  * Functional catalog entry moves to satisfied with status updated and trace fields refreshed.
  * Requirements change log records the transition details.
  * Mirrored CLI tests cover the behavior.
- Priority: medium
- Status: satisfied
- Reason: Satisfaction CLI implemented and tested
- Trace: prompts R2, tests tests/agentlab/cli/test_satisfy_cli.py; tests/reqflow/test_catalog.py, commits none
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
- Status: satisfied
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
  * CLI helpers and satisfaction flows emit the new format.
  * Existing catalog entries migrate to the new format.
  * Tests cover the new layout for creation and satisfaction paths.
- Priority: medium
- Status: satisfied
- Reason: Catalog headings applied and helpers updated
- Trace: prompts R4, tests tests/agentlab/cli/test_requirements_cli.py; tests/agentlab/cli/test_satisfy_cli.py, commits none
---

## Retired Requirements
