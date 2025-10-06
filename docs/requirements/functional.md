# Functional Requirements

Maintain Codex-sourced functional requirements in this catalog.
Every entry should link back to its originating task or prompt and to verifying tests.

## How to capture a new requirement

Copy the template below, fill in each field, and place it under **Active Requirements**.
Move fulfilled items to **Satisfied Requirements** once implementation and tests merge.

```
- ID: REQ-F-###
- Title: <short name>
- Owner: <person or team responsible>
- Narrative: As a <role>, I want <capability> so that <outcome>.
- Acceptance Criteria:
  * Given <context> when <action> then <result>.
  * Include as many bullet checks as needed.
- Status: proposed | active | satisfied | retired
- Trace: prompts <link>, tests <path>, commits <hash>
- Notes: optional clarifications or open questions.
```

## Active Requirements

- ID: REQ-F-000
- Title: Placeholder example
- Owner: product
- Narrative: As a template user, I want a sample entry so that formatting stays visible.
- Acceptance Criteria:
  * Given this repo when I open the catalog then I see an example entry.
- Status: proposed
- Trace: prompts none, tests none, commits none
- Notes: replace this sample once real requirements exist.

## Satisfied Requirements

Document completed functional requirements here with the same structure
and keep entries sorted by ID.
