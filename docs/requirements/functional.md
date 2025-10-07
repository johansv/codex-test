# Functional Requirements

<!-- STATUS-SUMMARY:START -->
Active: 0; Satisfied: 1 (satisfied=1); Retired: 0
<!-- STATUS-SUMMARY:END -->

Maintain Codex-sourced functional requirements in this catalog.
Every entry should link back to its originating task or prompt and to verifying tests.

## How to capture a new requirement

Copy the template below, fill in each field, and place it under **Active Requirements**.
Move fulfilled items to **Satisfied Requirements** once implementation and tests merge.
Move rejected or replaced requirements to **Retired Requirements** so history is preserved.

```
- ID: REQ-F-###
- Title: <short name>
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
```

## Active Requirements

## Satisfied Requirements

- ID: REQ-F-20251007T083937-FA
- Title: CLI satisfied transition helper
- Owner: codex
- Narrative: As a developer, I want a CLI command that marks requirements satisfied so that catalog updates and trace data stay consistent without manual edits.
- Acceptance Criteria:
  * Command accepts a requirement ID plus reason, verifying test paths, and optional commits.
  * Functional catalog entry moves to satisfied with status updated and trace fields refreshed.
  * Requirements change log records the transition details.
  * Mirrored CLI tests cover the command behavior.
- Priority: medium
- Status: satisfied
- Reason: Satisfaction CLI implemented and tested
- Trace: prompts R2, tests tests/agentlab/cli/test_satisfy_cli.py; tests/reqflow/test_catalog.py, commits none

## Retired Requirements
