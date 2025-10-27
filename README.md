# AgentLab

AgentLab is a sandbox for experimenting with Codex agents. The workspace ships
with tooling that enforces a requirements-first workflow so every feature ties
back to an explicit contract before any code is written.

## Getting Started

1. Install dependencies once with `uv sync`.
2. Launch Codex locally through the provided wrapper:
   - On macOS/Linux: `./scripts/dev.codex.sh`
   - On Windows PowerShell: `./scripts/dev.codex.ps1`

The scripts set the repository root as the working directory and export
`CODEX_BEFORE_TASK_HOOK=python:reqflow.codex_hooks:before_task`. This hook
runs *before* Codex plans or edits, ensuring the current prompt is captured in
`docs/requirements/` and blocking execution when an existing requirement must be
updated.

## Requirements Workflow

- Every task prompt is recorded via `reqflow.codex_hooks.before_task`,
  which automatically:
  - Creates or updates entries in `docs/requirements/functional.md` or
    `docs/requirements/non-functional.md`.
  - Generates ADR drafts under `docs/adr/` when architectural keywords are
    detected.
  - Assigns priorities and appends a change log entry.
- If the hook finds an overlapping requirement, the task is marked as blocked so
  you can reconcile the existing entry before coding.
- Requirements move through statuses `backlog`, `todo`, `done`, `rejected`, and `superseded`; capture a short reason whenever the status changes.
- When commits are created, include the trailer `Refs <requirement-id>` so the
  change can be traced back to its requirement.

Manual capture (`uv run reqflow-capture --prompt "..."`) is still available,
but the hook guarantees there are no gaps.

## Hosted / Web Usage

When running Codex outside the local scripts (e.g., hosted CLI, web console,
CI), make sure the hook is enabled:

- **CLI flag**: `--before-task-hook python:reqflow.codex_hooks:before_task`
- **Environment variable**: `CODEX_BEFORE_TASK_HOOK=python:reqflow.codex_hooks:before_task`

The hosted runner must mount this repository and have dependencies installed so
`reqflow.codex_hooks` can be imported.

## Additional Commands

- `uv run pytest` � execute the full test suite (requirement utilities and
  hooks are fully covered).
- `uv run ruff check src tests` � lint the project.
- `uv run python -m reqflow.cli.requirements ...` � manually add requirement
  entries when needed.
- `uv run reqflow-slice --help` � stream specific requirement entries by ID/tag with a compact summary.

## Garmin Fetch CLI

- **Environment:** export `GARMIN_EMAIL` and `GARMIN_PASSWORD` or place them in a local `.env` (see `.env.example`). TOTP codes can be supplied at runtime with `--mfa-code`.
- **Defaults:** endpoint selections live in `assets/config/garmin-endpoints.toml`. Adjust `defaults.enabled`/`defaults.disabled` for long-term changes, or override per run with `--include`/`--exclude`.
- **Presets:** the config file now supports named presets (see the `presets` table). Use `--preset <name>` to switch between bundles like `full`, the curated `coaching` set, or the `timeseries` preset that focuses on date/range-driven metrics; the default preset is defined under `[defaults]`.
- **Pacing controls:** tune rate limiting with `--delay-post-login`, `--delay-between-endpoints`, `--delay-pagination`, `--delay-jitter`, and `--retry-limit`. Jitter is expressed as a ratio (0.2 = ±20%).
- **Observability:** runs stream JSON logs with correlation IDs and emit a JSON summary on stdout that lists successes, failures, and retry counts for each day.
- **Storage:** responses and error files land under `./out/<YYYY-MM-DD>/` by default; switch destinations with `--output-dir`.
- **Examples:**
  - Default daily sync: `uv run agentlab-garmin-fetch --date 2024-10-15`
  - Long-range throttled sync:\
    `uv run agentlab-garmin-fetch --start-date 2024-10-01 --end-date 2024-10-07 --delay-post-login 8 --delay-between-endpoints 3 --delay-pagination 1.5 --delay-jitter 0.3 --retry-limit 2 --include sleep --debug`

## Project Layout

```
+-- docs/
�   +-- requirements/        # Functional & non-functional catalogs
�   +-- adr/                 # Architecture decision drafts
+-- scripts/                 # Codex launchers, test helpers
+-- src/agentlab/            # Runtime code
+-- tests/                   # Mirrored test suite
```

For more detailed guidance, see `AGENTS.md`, which Codex consumes directly when
planning tasks.


## Approval Enforcement

Set `REQFLOW_REQUIRE_APPROVAL=true` (default) to require `--approval-source` when running mark-done
CLIs. Use `--override-wait-for-approval` for exceptional cases (the CLI logs the override in the
requirements log).
