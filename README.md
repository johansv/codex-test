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

- `uv run pytest` - execute the full test suite (requirement utilities and
  hooks are fully covered).
- `uv run ruff check src tests` - lint the project.
- `uv run python -m reqflow.cli.requirements ...` - manually add requirement
  entries when needed.
- `uv run reqflow-slice --help` - stream specific requirement entries by ID/tag with a compact summary.

## Run manifest v1.0

The L0 “run manifest” records run-level lineage, totals, and per-day status to support resume and observability.
See the schema: **[`docs/runmeta/SCHEMA.md`](docs/runmeta/SCHEMA.md)**.

**CLI operator signals (stdout):**

1. `Run manifest: <abs-path>`  
2. `Run totals: {...}`

Exit codes: **0** on success, **1** if the run was aborted/errored. Logs and progress details are written to stderr or log files; stdout is reserved for the two lines above.

---

# Harmonized CLI Usage

The two CLIs follow the same conventions:

- **Stdout** prints exactly two lines at the end of a run (see *Run manifest v1.0* above).
- **Exit codes:** `0` on success, `1` if the run was aborted/errored.
- **Outputs:** L0 payloads under `out/l0/<vendor>/<YYYY-MM-DD>/` (or `--output-dir` / `--out-root`) and a per-run manifest under `<OUT_ROOT>/runs/run_<STAMP>_<RUN_ID>.meta.json`.
- **Privacy:** No PII (emails, tokens, secrets) is written to manifests or logs.

## Garmin Fetch CLI (`agentlab-garmin-fetch`)

### Overview
Fetches daily data from Garmin Connect for a date or date range, with selectable endpoint bundles and pacing controls.

### Authentication
- Provide credentials via environment or `.env` file in repo root:
  - `GARMIN_EMAIL` - your Garmin account email
  - `GARMIN_PASSWORD` - your Garmin account password
- Optionally pass `--mfa-code` if your account requires TOTP/MFA at login.

### Time semantics
- Garmin uses **device-/vendor-local** day semantics. If you travel, the calendar day reflects the device's local timezone for that period.

### Storage layout
- Default output directory is `./out` (override with `--output-dir`).
- Day folders: `out/l0/garmin/<YYYY-MM-DD>/`
- Run manifests: `out/runs/run_<YYYYMMDDHHMM>_<RUN_ID>.meta.json`

### CLI reference
| Flag | Type / Default | Description |
|---|---|---|
| `--date` | `YYYY-MM-DD` | Fetch a single calendar day. Mutually exclusive with `--start-date/--end-date`. |
| `--start-date` | `YYYY-MM-DD` | Start of range (inclusive). |
| `--end-date` | `YYYY-MM-DD` | End of range (inclusive). Required if `--start-date` is set. |
| `--include` | repeatable string | Explicitly include endpoint(s) for this run (overrides preset/defaults). |
| `--exclude` | repeatable string | Exclude endpoint(s) for this run. |
| `--config` | path; default `assets/config/garmin-endpoints.toml` | Endpoint config file. |
| `--preset` | string | Named preset in the config (`full`, `coaching`, `timeseries`, etc.). |
| `--list-endpoints` | flag | Print supported endpoint IDs and exit. |
| `--mfa-code` | string | TOTP/MFA code when prompted. |
| `--output-dir` | path; default `out` | Root directory for outputs and run manifests. |
| `--debug` | flag | Verbose per-endpoint logs to stderr. |
| `--delay-post-login` | float; default `5.0` | Seconds to wait after login before first endpoint. |
| `--delay-between-endpoints` | float; default `2.0` | Seconds between successive endpoints. |
| `--delay-pagination` | float; default `1.0` | Seconds between paginated API calls. |
| `--delay-jitter` | float; default `0.2` | Relative jitter applied to all delays (0.2 = ±20%). |
| `--retry-limit` | int; default `1` | Retry passes for failed endpoints. |

### Examples
```bash
# Single day (yesterday)
uv run agentlab-garmin-fetch --date 2025-10-30

# One week with pacing and a preset
uv run agentlab-garmin-fetch   --start-date 2025-10-24 --end-date 2025-10-30   --preset timeseries   --delay-post-login 8 --delay-between-endpoints 3 --delay-pagination 1.5   --delay-jitter 0.3 --retry-limit 2 --debug

# Curate endpoints explicitly
uv run agentlab-garmin-fetch   --date 2025-10-30   --include sleep --include hrv --exclude activities
```

---

## Withings L0 CLI (`agentlab-withings-fetch`)

### Overview
Fetches daily **body metrics** from Withings and writes vendor-raw JSON per calendar day with metadata and a unified run manifest.

### Authentication
- Place OAuth tokens in a JSON file (default `secrets/withings_tokens.json`), or specify with `--auth-file`.
- File must contain: `access_token`, `refresh_token`, `expires_at` (ISO-8601 UTC or epoch seconds), `client_id`, `client_secret`.
- Username/password flows are **not** supported; obtain tokens via Withings app registration.

### Time semantics
- Withings uses **strict Europe/Stockholm calendar dates** (no 04:00 cutover). Records between 00:00-23:59 are written to that same date.

### Storage layout
- Default output root is `./out` (override with `--out-root`).
- Day folders: `<OUT_ROOT>/l0/withings/<YYYY-MM-DD>/` with `measures-YYYYMMDD.json` and `measures-YYYYMMDD.meta.json`.
- Run manifests: `<OUT_ROOT>/runs/run_<YYYYMMDDHHMM>_<RUN_ID>.meta.json`.

### CLI reference
| Flag | Type / Default | Description |
|---|---|---|
| `--start-date` | `YYYY-MM-DD` | Start of range (inclusive). |
| `--end-date` | `YYYY-MM-DD` | End of range (inclusive). |
| `--out-root` | path; default `./out` | Root directory for outputs and run manifests. |
| `--auth-file` | path; default `secrets/withings_tokens.json` | Path to OAuth token bundle. |
| `--skip-existing` | flag | Do not overwrite successful day outputs; mark as skipped. |
| `--resume` | flag | Resume only days with status in `{pending, partial, error}` from the latest run manifest. |
| `--dry-run` | flag | Reserved for parity; currently still writes outputs (see `--debug`). |
| `--request-delay` | float; default `1.0` | Seconds between Withings API calls. |
| `--debug` | flag | Verbose per-day progress to stderr. |
| `--transport` | module:factory | Override transport factory (advanced/testing). |

### Examples
```bash
# 3-day sync to the default data root
uv run agentlab-withings-fetch --start-date 2025-10-25 --end-date 2025-10-27

# Idempotent resume run, throttled
uv run agentlab-withings-fetch   --start-date 2025-10-20 --end-date 2025-10-31   --out-root ./out --skip-existing --resume --request-delay 1.0 --debug

# Custom auth file
uv run agentlab-withings-fetch   --start-date 2025-10-29 --end-date 2025-10-29   --auth-file ./secrets/prod-withings.json
```

---

## Project Layout

```
+-- docs/
|   +-- requirements/        # Functional & non-functional catalogs
|   +-- adr/                 # Architecture decision drafts
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
