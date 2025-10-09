# Non-Functional Requirements

<!-- STATUS-SUMMARY:START -->
Todo: 1 (backlog=1); Done: 0; Retired: 0
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

List retired or done non-functional requirements here to preserve history.
Keep entries sorted by ID and update measurement notes with the proof of compliance.

## Retired Requirements

Document constraints that were rejected or superseded. Note why they were
retired and link to any successor requirements.


