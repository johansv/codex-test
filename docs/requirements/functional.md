# Functional Requirements

<!-- STATUS-SUMMARY:START -->
Todo: 0; Done: 13 (done=13); Retired: 0
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
- Status: backlog | todo | doing | done | rejected | superseded
- Reason: why the current status applies (e.g., superseded by REQ-F-?)
- Trace: prompts <link>, tests <path>, commits <hash>
- Notes: optional clarifications or open questions.
---
```

## Todo Requirements

## Done Requirements

### REQ-F-20251010T072114-M5: Batch workflow utilities
- Owner: codex
- Narrative: As a maintainer, I want a single command that orchestrates collision detection, related requirement surfacing, bulk reopen, and logging so that large refactors can be prepared in one predictable workflow.
- Acceptance Criteria:
  * CLI accepts a functional requirement ID and runs collision detection, functional/non-functional overlap heuristics, and bulk reopen helpers in one pass.
  * Command prints a consolidated report summarizing collisions, functional overlaps, non-functional overlaps, and reopened amendments.
  * Users can opt into auto-reopening via flags; otherwise acknowledgements mirror the manual workflow.
  * Logging remains consistent with existing helpers and the command refuses to proceed if catalogs are missing or malformed.
  * Tests cover happy path, acknowledgement prompts, auto-reopen flows, and failure scenarios.
- Priority: high
- Status: done
- Reason: Batch workflow CLI automates collision, overlap, and reopen flows
- Trace: prompts R13, tests tests/agentlab/cli/test_batch_cli.py; tests/reqflow/test_catalog.py, commits none
---

### REQ-F-20251010T065151-MG: Non-functional overlap heuristics
- Owner: codex
- Narrative: As a maintainer, I want the start workflow to surface related non-functional requirements when shared components are touched so that quality constraints aren't missed during implementation.
- Acceptance Criteria:
  * Start CLI scans the non-functional catalog for overlaps and lists candidates alongside the functional suggestions.
  * Users must acknowledge non-functional suggestions or explicitly reopen relevant entries before proceeding.
  * Helper supports reopening non-functional amendments with Amends metadata tied to the primary functional requirement.
  * Tests cover candidate detection, acknowledgement flows, and reopening behaviour for non-functional entries.
- Priority: high
- Status: done
- Reason: Start CLI surfaces non-functional overlaps with acknowledgment and amendment support
- Trace: prompts R12, tests tests/agentlab/cli/test_start_cli.py; tests/reqflow/test_catalog.py, commits none
---

### REQ-F-20251010T062944-EA: Bulk amendment reopen helper
- Owner: codex
- Narrative: As a maintainer, I want a CLI that reopens multiple requirements at once so that large refactors keep catalog updates consistent.
- Acceptance Criteria:
  * Command accepts one or more requirement IDs and reopens each as an amendment with Amends metadata tied to a supplied primary.
  * Log entries record the reopening operation once per requirement with author/reference metadata.
  * Helper validates IDs exist and refuses to proceed if any are unsuitable (e.g., already doing unless override is set).
  * Tests cover successful bulk reopen, mixed invalid IDs, and log output.
- Priority: high
- Status: done
- Reason: Bulk amendment CLI and catalog helper implemented
- Trace: prompts R11, tests tests/agentlab/cli/test_bulk_amend_cli.py; tests/reqflow/test_catalog.py, commits none
---

### REQ-F-20251009T182153-NN: Surface cross-cutting requirement candidates
- Owner: codex
- Narrative: As a maintainer, I want the workflow to suggest related requirements when a change touches shared components so that cross-cutting edits don’t miss dependent specs.
- Acceptance Criteria:
  * During implementation prep the tooling scans the catalog for requirements sharing tags, components, or keywords with the selected requirement.
  * CLI output lists candidate overlaps and prompts the user to acknowledge or reopen them as amendments.
  * Users can opt out when suggestions are irrelevant, avoiding noisy prompts.
  * Tests cover overlapping and non-overlapping scenarios to ensure relevant suggestions.
- Priority: high
- Status: done
- Reason: Related requirement surfacing implemented
- Trace: prompts R9, tests tests/agentlab/cli/test_start_cli.py, commits none
---

### REQ-F-20251009T204414-NU: Historic amendment workflow
- Owner: codex
- Narrative: As a maintainer, I want a dedicated amendment flow that reopens already-done requirements for targeted edits so that catalog history stays accurate without losing the original trace.
- Acceptance Criteria:
  * CLI command reopens done requirements into an amendment state recording who reopened and why without bypassing WIP guards.
  * Amendment mode lets editors adjust narrative, acceptance criteria, and traces while preserving prior trace details in the change log.
  * Completing the amendment returns the requirement to done, logs a correction summary, and links verifying commits/tests.
  * Tests cover reopening done requirements, editing in amendment mode, and resealing them with accurate catalog and log output.
- Priority: high
- Status: done
- Reason: Historic amendment CLI and catalog flow implemented
- Trace: prompts R10, tests tests/agentlab/cli/test_amend_cli.py; tests/reqflow/test_catalog.py, commits none
---

### REQ-F-20251009T113439-GZ: Automate catalog alignment via linked amendments
- Owner: codex
- Narrative: As a maintainer, I want done requirements amended automatically during implementation so that the catalog matches code in a single atomic update.
- Acceptance Criteria:
  * Collision detection reopens each affected done requirement, adds Amends: <primary_id>, and records the amendment in the change log.
  * CLI prompts display the collision list and show which entries are being amended with their Amends values.
  * Mark-done workflow updates the primary requirement plus all linked amendments together, including removing Amends and refreshing narratives, acceptance, and traces.
  * Tests simulate the full collision/amendment cycle and verify catalog/log updates including the Amends field.
- Priority: high
- Status: done
- Reason: Amendment automation implemented
- Trace: prompts R8, tests tests/agentlab/cli/test_start_cli.py; tests/agentlab/cli/test_mark_done_cli.py; tests/reqflow/test_catalog.py, commits none
---

### REQ-F-20251009T113432-AM: Control doing status with WIP guard
- Owner: codex
- Narrative: As a maintainer, I want a doing status with a single active slot so that only one requirement is in progress while linked amendments ride along transparently.
- Acceptance Criteria:
  * Tooling ensures only one primary requirement can hold status doing at a time unless an override is explicitly requested.
  * Reopened done requirements triggered by collisions gain an Amends: <primary_id> line while they are updated and do not consume additional WIP slots.
  * Marking the primary requirement done restores all linked amendments to done, removes the Amends metadata, and logs the transition.
  * Status summaries and change logs display doing counts and amendment associations.
  * Tests cover WIP guard enforcement, amendment tagging/clearing, and log output.
- Priority: high
- Status: done
- Reason: Doing guard and amendment handling implemented
- Trace: prompts R8, tests tests/agentlab/cli/test_start_cli.py; tests/agentlab/cli/test_mark_done_cli.py; tests/reqflow/test_catalog.py, commits none
---

### REQ-F-20251009T113425-NU: Enforce implementation gate with collision alerts
- Owner: codex
- Narrative: As a maintainer, I want every coding task to pass through a gate that confirms requirement approval and highlights dependent done entries so that scope stays agreed before implementation starts.
- Acceptance Criteria:
  * Implementation entrypoints refuse to proceed unless the selected requirement is status todo.
  * Starting implementation automatically promotes the requirement to doing and records the transition.
  * During promotion the tooling scans done requirements, reporting potential collisions with IDs and short synopses.
  * Collisions must be explicitly acknowledged before promotion succeeds, with alerts explaining that affected entries will gain Amends metadata.
  * Tests cover happy-path promotion, refusal when status is not todo, and collision acknowledgement flows.
- Priority: high
- Status: done
- Reason: Implementation gate and collision alerts available
- Trace: prompts R8, tests tests/agentlab/cli/test_start_cli.py; tests/reqflow/test_catalog.py, commits none
---

### REQ-F-20251009T095326-TT: Standardize requirement lifecycle terminology
- Owner: codex
- Narrative: As a maintainer, I want the catalogs and tooling to use a consistent backlog/todo/doing/done lifecycle so that workflow expectations stay clear for every requirement.
- Acceptance Criteria:
  * Functional and non-functional catalog templates list Backlog, Todo, Doing, Done, Rejected, Superseded.
  * CLI helpers and validation enforce the lifecycle values (backlog/todo/doing/done/rejected/superseded) for new and existing entries.
  * Status summaries, docs, and tests reflect the full lifecycle, including the in-progress Doing state.
  * Migration scripts or helpers update existing catalog entries to the standardized terminology.
- Priority: medium
- Status: done
- Reason: Lifecycle terminology enforced
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


