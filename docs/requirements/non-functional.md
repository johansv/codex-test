# Non-Functional Requirements

Track quality attributes, constraints, and operational expectations here.
Connect each entry to monitoring hooks, docs, or tests that validate the constraint.

## How to capture a new requirement

Use the template below whenever Codex introduces reliability, performance,
security, or other system constraints.

```
- ID: REQ-NF-###
- Title: <short name>
- Owner: <person or team responsible>
- Category: performance | reliability | security | usability | other
- Description: Concise statement of the constraint or objective.
- Measurement: How the team validates compliance (metric target, probe, checklist).
- Status: proposed | active | satisfied | retired
- Trace: prompts <link>, tests <path>, scripts <path>, monitors <link>
- Notes: Implementation guidance, owners, or follow-ups.
```

## Active Requirements

- ID: REQ-NF-000
- Title: Placeholder example
- Owner: platform
- Category: reliability
- Description: Maintain an example entry until the first real requirement replaces it.
- Measurement: Manual review of this catalog during project setup.
- Status: proposed
- Trace: prompts none, tests none, scripts none, monitors none
- Notes: Delete or repurpose when real constraints are documented.

## Satisfied Requirements

List retired or satisfied non-functional requirements here to preserve history.
Keep entries sorted by ID and update measurement notes with the proof of compliance.
