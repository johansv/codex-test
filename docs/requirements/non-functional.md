# Non-Functional Requirements

<!-- STATUS-SUMMARY:START -->
Todo: 1 (backlog=1); Done: 4 (done=4); Retired: 0
<!-- STATUS-SUMMARY:END -->

Track quality attributes, constraints, and operational expectations here.
Connect each entry to monitoring hooks, docs, or tests that validate the constraint.

## How to capture a new requirement

Use the template below whenever Codex introduces reliability, performance,
security, or other system constraints. Move rejected ideas to **Retired Requirements**
so the catalog retains history.

```
### REQ-NF-###: <short name>
- Owner: <person or team responsible>
- Category: performance | reliability | security | usability | other
- Description: Concise statement of the constraint or objective.
- Measurement: How the team validates compliance (metric target, probe, checklist).
- Priority: low | medium | high
- Status: backlog | todo | doing | done | rejected | superseded
- Reason: why the current status applies (e.g., superseded by REQ-NF-?)
- Trace: prompts <link>, tests <path>, scripts <path>, monitors <link>
- Notes: Implementation guidance, owners, or follow-ups.
---
```

> Auto-captured entries may include the placeholder acceptance bullet "Acceptance criteria to be detailed from prompt." Replace it with concrete checks during refinement.

## Todo Requirements

### REQ-NF-000: Placeholder example
- Owner: platform
- Category: reliability
- Description: Maintain an example entry until the first real requirement replaces it.
- Measurement: Manual review of this catalog during project setup.
- Priority: medium
- Status: backlog
- Reason: pending
- Trace: prompts none, tests none, scripts none, monitors none
- Notes: Delete or repurpose when real constraints are documented.
---

## Done Requirements

### REQ-NF-20251017T154134-DZ: Garmin Fetch CLI documentation refresh
- Owner: codex
- Category: documentation
- Description: Document pacing controls, retry behaviour, and runtime expectations for the Garmin Fetch CLI.
- Measurement: README and related docs cover pacing flags, retries, env vars, and logging signals with updated examples.
- Priority: medium
- Status: done
- Reason: Garmin CLI documentation now covers pacing, retries, and observability
- Trace: prompts Garmin documentation sync request, tests Documentation review, scripts none, monitors none
---

### REQ-NF-20251010T151552-8U: Scoped requirement streaming in CLI
  - Owner: codex
  - Category: usability
  - Description: CLI streams only requested requirement IDs or tags plus summaries for unrelated entries to keep agent context small.
  - Measurement: Outputs limit unrelated summaries to <=250 tokens and pass slice tests for mixed selections.
  - Priority: medium
- Status: done
- Reason: Scoped slice CLI streams selected entries with tag/id filters and compact summaries
- Trace: prompts R24, tests tests/agentlab/cli/test_slice_cli.py, scripts none, monitors none
---

### REQ-NF-20251010T151543-IE: Catalog digest caching for planner and review
- Owner: codex
- Category: performance
- Description: Planner and review tooling reuse cached catalog digests to avoid rereading unchanged files.
- Measurement: Checksum-based cache and refresh flag deliver >=25% faster repeated overlap checks.
- Priority: medium
- Status: done
- Reason: Catalog digest cache accelerates planner and review with refresh controls
- Trace: prompts R23, tests tests/reqflow/test_planner.py; tests/agentlab/cli/test_review_cli.py, scripts none, monitors none
---

### REQ-NF-20251010T151535-UV: Non-functional capture summarisation
- Owner: codex
- Category: performance
- Description: Auto-generated non-functional entries store concise narratives and placeholders to keep catalog size predictable.
- Measurement: Summaries trimmed to <=140 characters and placeholder acceptance recorded for manual refinement.
- Priority: medium
- Status: done
- Reason: Auto-captured non-functional entries now summarise narratives with placeholder acceptance
- Trace: prompts R22, tests tests/reqflow/test_planner.py, scripts none, monitors none
---

List retired or done non-functional requirements here to preserve history.
Keep entries sorted by ID and update measurement notes with the proof of compliance.

## Retired Requirements

Document constraints that were rejected or superseded. Note why they were
retired and link to any successor requirements.


