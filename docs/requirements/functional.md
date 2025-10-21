# Functional Requirements

<!-- STATUS-SUMMARY:START -->
Todo: 2 (backlog=2, doing=0); Done: 32 (done=32); Retired: 0
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

> Auto-captured entries may include the placeholder acceptance bullet "Acceptance criteria to be detailed from prompt." Replace it with concrete checks during refinement.

## Todo Requirements

### REQ-F-20251010T073818-5B: Batch review orchestration
- Owner: codex
- Narrative: As a maintainer, I want batch workflows to handle multiple requirements and persist summaries so that large refactors can be prepared in one automated pass.
- Acceptance Criteria:
  * Batch CLI accepts multiple primary requirement IDs or analyzes all doing requirements in one run.
  * Command writes a machine-readable summary (e.g., JSON) capturing collisions, overlaps, and auto-reopens for later use.
  * Acknowledgement flags remain mandatory unless auto-reopen is explicitly requested.
  * Tests cover multi-requirement refactors, summary persistence, and acknowledgement enforcement.
- Priority: medium
- Status: backlog
- Reason: Needs prioritization
- Trace: prompts R16, tests none, commits none
---

## Done Requirements

### REQ-F-20251021T113857-26: Add metadata sidecar files recording provenance alongside garmin fetch outputs
- Owner: product
- Narrative: As a user, I want Garmin fetches to emit metadata sidecars so that every payload is provenance-traceable.
  - Acceptance Criteria:
    * Successful payload writes create a sibling `<endpoint>.<ext>.meta.json` capturing timestamp, Garmin Connect version, run identifier or correlation ID, endpoint name, scope, garmin_methods, payload type/size, MD5, and `status: success`.
    * When an endpoint fails, the storage layer still writes the identically named `.meta.json` with `status: error`, linking to the `.error.json` file and recording the error message/traceback and expected payload filename even if absent.
    * Metadata filenames remain consistent between success and error outcomes and continue to rely on atomic writes within the storage helper and retry flow.
    * Tests cover both success and error scenarios, asserting sidecar content includes status, existence flag, MD5 (when present), and garmin method provenance.
- Priority: medium
- Status: done
- Reason: Metadata sidecars published
- Trace: prompts Add metadata sidecar files recording provenance alongside Garmin fetch outputs, tests tests/agentlab/utils/test_storage.py; tests/agentlab/runners/test_garmin_fetcher.py, commits pending
---
### REQ-F-20251021T130040-QF: Skip detail endpoints when source items absent
- Owner: product
- Narrative: As a user, I want detail endpoints to run only when matching activities, workouts, or gear exist so that the fetcher avoids unnecessary API calls and sidecar noise.
  - Acceptance Criteria:
    * Activity detail endpoints (detail, details, splits, etc.) do not invoke Garmin APIs and produce no results when no activities are available for the requested day.
    * Workout detail/download endpoints are skipped when the workouts list is empty for the run.
    * Gear stats/activities endpoints are skipped when no gear entries are present for the run.
    * Device detail endpoints (settings, last-used, solar, alarms, primary device) are skipped when no devices are cached for the run.
    * Unit tests cover empty activity/workout/gear/device scenarios verifying that the corresponding Garmin client methods are not called.
- Priority: medium
- Status: done
- Reason: Detail endpoints gated by available items
- Trace: prompts Skip detail endpoints for empty activity/workout/gear lists, tests tests/agentlab/runners/test_garmin_fetcher.py, commits pending
---


### REQ-F-20251018T215419-X1: Garmin fetch full API coverage
- Owner: codex
- Narrative: As an operator, I want the Garmin fetcher to expose the remaining Garmin data endpoints so that the CLI can mirror the full Garmin Connect dataset.
- Acceptance Criteria:
  * Handlers exist for remaining Garmin data endpoints (activity details, badges, goals, gear, lactate, solar, etc.)
  * Endpoints integrate with per-day iteration and storage naming
  * Tests validate each new handler calls the correct Garmin client method
  * Multi-day runs reuse a single authenticated Garmin session so only one login occurs per CLI invocation
  * When login or any endpoint call raises an HTTP 429, the fetcher emits a `garmin.rate-limit` log naming the date in progress and recommending a 10-minute wait, then stops further work
- Priority: high
- Status: done
- Reason: Garmin fetcher outputs and session reuse verified
- Trace: prompts Complete Garmin data sync request, tests uv run pytest, commits none
---

### REQ-F-20251020T113659-JF: Garmin FIT activity exports
- Owner: codex
- Narrative: As an operator, I want the Garmin downloader to save original .fit files alongside processed exports so that I retain raw data for advanced analysis and third-party tooling.
- Acceptance Criteria:
  * When activity downloads run, the original .fit payload is saved with a stable per-activity filename
  * Presets and storage handle FIT outputs without overwriting existing exports
- Priority: medium
- Status: done
- Reason: Activity downloader now emits both TCX and FIT files
- Trace: prompts FIT export request, tests uv run pytest, commits none
---

### REQ-F-20251020T090147-ZS: Garmin endpoint presets
- Owner: codex
- Narrative: As an operator, I want selectable Garmin endpoint configurations so that I can run full exports or a curated daily coaching set without editing TOML each time.
- Acceptance Criteria:
  * Configuration loader supports named presets (e.g., full, coaching)
  * All endpoints preset covers every registered handler
  * Coaching preset captures data needed for personalized AI coach
  * Timeseries preset bundles all date- and range-driven endpoints for longitudinal analysis
- Priority: medium
- Status: done
- Reason: Endpoint presets and CLI selection implemented
- Trace: prompts Multiple Garmin configs request, tests uv run pytest, commits none
---

### REQ-F-20251017T170307-45: Consistent per-day date range calls
- Owner: codex
- Narrative: As an operator, I want date-range Garmin endpoints to execute per day with matching start/end arguments so that daily syncs stay scoped and avoid multi-day hangs.
- Acceptance Criteria:
  * Endpoints that accept start/end dates call them per day using identical start and end values
  * Stored scopes/filenames include the per-day identifiers
  * Regression tests verify per-day iteration for representative endpoints
- Priority: high
- Status: done
- Reason: Date-range endpoints now iterate daily with matching start/end arguments
- Trace: prompts Date range scoping issue, tests uv run pytest, commits none
---

### REQ-F-20251017T164320-L0: Activity detail pagination and naming fix
- Owner: codex
- Narrative: As an operator, I want the Garmin fetcher to iterate activity-detail endpoints per activity with IDs propagated so that long runs don’t hang and outputs stay uniquely traceable.
- Acceptance Criteria:
  * Activity detail endpoints iterate exactly once per activity by passing activityId
  * Outputs for activity-centric endpoints append _<activityId> to filenames and error files
  * Regression tests cover multiple activities and filename uniqueness
- Priority: high
- Status: done
- Reason: Activity detail endpoints iterate per activity with unique filenames
- Trace: prompts Activity detail hang report, tests uv run pytest, commits none
---

### REQ-F-20251017T162547-59: Garmin CLI job diagnostics logging
- Owner: codex
- Narrative: As an operator, I want the Garmin Fetch CLI to emit a debug snapshot of its settings and explicit login results so I can confirm jobs are configured correctly and authentication succeeds.
- Acceptance Criteria:
  * Debug runs emit a structured settings event omitting GARMIN_PASSWORD
  * Login and MFA resume attempts log explicit success/failure events
  * New telemetry uses existing correlation IDs in the JSON log stream
- Priority: medium
- Status: done
- Reason: Debug telemetry logs configuration snapshot and login outcomes
- Trace: prompts Garmin logging enhancement request, tests uv run pytest, commits none
---

### REQ-F-20251014T120146-GT: Account-safety execution policies
- Owner: codex
- Narrative: As a Garmin account holder, I want conservative pacing and retries so that the downloader avoids triggering rate limits or suspensions.
- Acceptance Criteria:
  * Default pacing applies configurable delays (5s post-login, 2s between endpoints, 1s within pagination) with ?20% jitter.
  * Execution remains single threaded and processes endpoints sequentially.
  * Each endpoint retries at most once after the first pass completes, using the same pacing controls.
  * Configuration surface exposes delay and retry settings for tuning without code changes.
- Priority: high
- Status: done
- Reason: Pacing and retry controls verified
- Trace: prompts Garmin ingestion design discussion, tests uv run pytest, commits none
---

### REQ-F-20251014T120121-GR: Resilient error handling and logging
- Owner: codex
- Narrative: As an operator, I want failures logged per endpoint without halting runs so that I still harvest partial Garmin data with useful diagnostics.
- Acceptance Criteria:
  * Each endpoint call is wrapped to log errors, write the matching <endpoint>.error.json, and continue.
  * CLI emits a success and failure summary at completion including retry outcomes.
  * Process exits with success when at least one endpoint succeeds and non-zero only when all fail.
  * Structured logs capture request context and correlation IDs for debugging.
- Priority: high
- Status: done
- Reason: Structured logging and resilient error handling verified
- Trace: prompts Garmin ingestion design discussion, tests uv run pytest, commits none
---

### REQ-F-20251014T120032-GS: Date-partitioned storage layout
- Owner: codex
- Narrative: As an operator, I want responses saved under YYYY-MM-DD folders with endpoint file names so that downstream jobs can locate daily Garmin data quickly.
- Acceptance Criteria:
  * Data writes target <root>/<YYYY-MM-DD>/<endpoint>.<ext> preserving the original response format.
  * Writes are atomic via temp files and always overwrite prior content for the same endpoint and date.
  * Failures emit <endpoint>.error.json containing structured metadata and full stack trace.
  * Re-running for the same dates replaces prior files without leaving partial artifacts.
  * CLI defaults to writing under ./out but accepts a configurable output directory argument.
  * Date ranges are processed one day at a time with isolated per-date folders.
  * CLI exposes a debug mode that logs each endpoint as it executes.
  * When an endpoint succeeds, any existing <endpoint>.error.json for that date is removed.
- Priority: high
- Status: done
- Reason: Garmin fetch storage overwrites outputs and clears stale error files
- Trace: prompts Garmin ingestion design discussion, tests tests/agentlab/utils/test_storage.py; tests/agentlab/cli/test_garmin_fetch_cli.py, commits none
---

### REQ-F-20251014T120058-GC: Endpoint configuration controls
- Owner: codex
- Narrative: As a maintainer, I want configurable defaults and overrides for Garmin endpoints so that I can tailor downloads without rewriting code.
- Acceptance Criteria:
  * Configuration file defines default endpoint enablement and is loaded automatically by the CLI.
  * Command line flags include and exclude endpoints explicitly, validating names against the supported list.
  * Unknown or disabled endpoint requests report actionable errors without starting downloads.
  * Documentation explains adjusting defaults and invoking ad hoc endpoint subsets.
- Priority: medium
- Status: done
- Reason: Garmin fetch CLI honors endpoint config with include/exclude flags
- Trace: prompts Garmin ingestion design discussion, tests tests/agentlab/cli/test_garmin_fetch_cli.py, commits none
---

### REQ-F-20251014T120001-GA: Garmin data session fetcher
- Owner: codex
- Narrative: As a data owner, I want a CLI that authenticates to Garmin Connect and fetches every explicit 0.2.30 endpoint so that my Health Coach AI receives complete daily data.
- Acceptance Criteria:
  * CLI reads Garmin credentials from environment variables (or a colocated `.env` file) and signs in without interactive prompts.
  * Program pulls every explicitly enumerated garminconnect 0.2.30 data endpoint sequentially.
  * Execution supports --date for a single day or --start-date/--end-date for ranges plus endpoint subset flags.
  * Implementation uses direct endpoint calls mirroring project demos with no reflection-based dispatch.
- Priority: high
- Status: done
- Reason: CLI now honours dotenv fallback for credentials
- Trace: prompts Garmin ingestion design discussion, tests tests/agentlab/cli/test_garmin_fetch_cli.py; tests/agentlab/runners/test_garmin_fetcher.py, commits none
---

### REQ-F-20251010T073939-HE: Wait-for-approval enforcement
- Owner: codex
- Narrative: As a maintainer, I want safeguards that block automatic mark-done operations without approval so that the wait-for-approval workflow cannot be bypassed.
- Acceptance Criteria:
  * Introduce configuration checked by CLI commands to refuse mark-done unless approval has been recorded or an explicit override is passed.
  * Codex Cloud agents must record user approval before invoking mark-done; CLI should log the approval source.
  * Tests cover refusal without approval, override flows, and approval logging.
- Priority: high
- Status: done
- Reason: Approval config enforces wait-for-approval guard
- Trace: prompts R19, tests tests/agentlab/utils/test_approvals.py; tests/agentlab/cli/test_mark_done_cli.py; tests/agentlab/cli/test_mark_done_nonfunctional_cli.py, commits none
---

### REQ-F-20251010T073826-CD: Documentation and refactor requirement alignment
- Owner: codex
- Narrative: As a maintainer, I want documentation and refactor tasks to run automated requirement checks so that catalogs stay aligned even when code logic changes minimally.
- Acceptance Criteria:
  * Provide a CLI wrapper that runs the review/batch workflow for documentation-only or refactor changes.
  * Wrapper prompts for requirement adjustments when changes affect shared components, even if no functional code paths are touched.
  * Tests cover doc-only updates, refactors, and confirmation that catalogs remain consistent.
- Priority: medium
- Status: done
- Reason: Documentation/refactor wrapper runs review and overlap checks with acknowledgement gating
- Trace: prompts R17, tests tests/agentlab/cli/test_doc_refactor_cli.py, commits none
---

### REQ-F-20251010T151527-BX: Functional auto-capture text compaction
- Owner: codex
- Narrative: As a requirements maintainer, I want auto-generated functional entries to store compact narratives and placeholders so that catalogs stay concise.
- Acceptance Criteria:
  * Auto-generated narrative capped at about 120 characters derived from the first sentence.
  * Fallback acceptance criterion uses a fixed placeholder instead of copying the full prompt.
  * Docs direct maintainers to expand the placeholder acceptance bullet during refinement.
- Priority: medium
- Status: done
- Reason: Auto-captured narrative and acceptance outputs are compact with supporting tests
- Trace: prompts R21, tests tests/reqflow/test_planner.py, commits none
---

### REQ-F-20251010T073809-JN: Non-functional lifecycle parity
- Owner: codex
- Narrative: As a maintainer, I want non-functional requirements to share the same lifecycle helpers as functional ones so that amendments and done-state tracking stay consistent across catalogs.
- Acceptance Criteria:
  * Provide mark-done and WIP guard helpers for non-functional requirements mirroring the functional workflow.
  * Closing a functional requirement clears dependent non-functional amendments automatically and vice versa.
  * Tests cover non-functional mark-done flows, amendment reopening, and synchronization with functional primaries.
- Priority: high
- Status: done
- Reason: Non-functional lifecycle helpers aligned with functional flow
- Trace: prompts R15, tests tests/agentlab/cli/test_start_nonfunctional_cli.py; tests/agentlab/cli/test_mark_done_nonfunctional_cli.py; tests/agentlab/cli/test_mark_done_cli.py; tests/reqflow/test_catalog.py, commits none
---

### REQ-F-20251010T073931-RY: Requirement drift detection
- Owner: codex
- Narrative: As a maintainer, I want automated drift detection that checks done requirements against the repository so that obsolete or inconsistent specifications are caught promptly.
- Acceptance Criteria:
  * Review tooling warns when done requirements reference missing files/tests or no longer align with the codebase.
  * Provide a prune option that flags obsolete requirements and moves them back to backlog/todo for reassessment.
  * Tests cover missing file detection, obsolete requirements, and successful drift clearance.
- Priority: medium
- Status: done
- Reason: Drift prune reuses catalog helpers for consistent resets
- Trace: prompts R18, tests tests/agentlab/cli/test_review_cli.py, commits none
---

### REQ-F-20251010T073801-G1: Automated requirements review CLI
- Owner: codex
- Narrative: As a maintainer, I want a review command that validates functional and non-functional catalogs against the codebase so that requirement changes catch conflicts and missing updates automatically.
- Acceptance Criteria:
  * CLI scans functional and non-functional catalogs for missing acknowledgements, contradictory statuses, and references to deleted files.
  * Review output highlights potential overlaps/contradictions and refuses to pass until acknowledged.
  * Command integrates with CI, failing when catalogs diverge from the repository.
  * Tests cover scenarios with contradictory requirements, missing files, and resolved acknowledgements.
- Priority: high
- Status: done
- Reason: Automated requirements review CLI available
- Trace: prompts R14, tests tests/agentlab/cli/test_review_cli.py; tests/reqflow/test_catalog.py, commits none
---

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

