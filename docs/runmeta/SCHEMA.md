# Run Manifest Schema Reference (runmeta/1.0)

This document describes the run-level manifest file used by L0 ingest jobs. It is a human-readable catalogue for audit, lineage, and resume flows; it does not establish product requirements.

---

## Purpose & Scope
- Track each ingest run's parameters, timing, totals, and per-day progress.
- Provide a durable resume point so tooling can restart from pending, partial, or error days.
- Offer a single artifact for operators and automation to audit outcomes without scanning logs.

---

## File Location & Atomicity
- Path pattern: `<OUT_ROOT>/runs/run_<YYYYMMDDHHMM>_<RUN_ID>.meta.json`
- Write strategy: materialise content to a temporary file in the same directory, then atomically replace the target manifest (e.g., `os.replace`); never update in place.

---

## Field Overview
| Field | Description |
| --- | --- |
| `schema_version` | Literal string `runmeta/1.0` identifying this schema. |
| `run_id` | Unique identifier supplied by the runner; matches per-day metadata. |
| `started_at` | ISO-8601 timestamp with offset for when the run began. |
| `finished_at` | ISO-8601 timestamp with offset once the run is complete; omitted until set. |
| `timezone` | Run-local timezone identifier (e.g., `Europe/Stockholm`). |
| `vendor` | Data source identifier: `"withings"` or `"garmin"`. |
| `params` | Object capturing invocation parameters: `start_date`, `end_date`, `preset`, `out_root`, `skip_existing`, `dry_run`. |
| `totals` | Object summarising the run: `days_scheduled`, `days_done`, `endpoints` (counts of `success`, `skipped`, `error`, `written`), `bytes_payload`, `duration_s`. |
| `progress` | Map keyed by `YYYY-MM-DD`, each value containing: `status` (see below), optional `endpoints` map (per-endpoint outcome with `status`, `written`, `items?`, `bytes_payload?`), optional `run` object (e.g., `{ "correlation": "<run_id>:<date>" }`). |
| `aborted` | Either `null` or an object describing a terminal abort (`code`, `message`, optional `at`, optional `last_endpoint`). |
| `notes` | Array of free-form strings for supplementary commentary. |

**Day status values:** `pending`, `done`, `partial`, `skipped`, `error`.

---

## Lifecycle State Machine
```
start_run -> start_day -> record_partial -> end_day -> abort -> finish
```
- A run typically executes: `start_run` -> (`start_day` -> `end_day`)* -> `finish`.
- `record_partial` is used when a day fails mid-flight; the same day may later transition to `end_day`.
- `abort` finalises the run if unrecoverable conditions occur; afterwards the manifest remains immutable except for reading.

---

## CLI Operator Signals (Reference)
- Upon completion (success or failure) the CLI prints exactly:
  1. `Run manifest: <abs-path>`
  2. `Run totals: {...}`
- Exit codes: `0` for successful completion, `1` when aborted or error.

---

## Time Semantics (Reference)
- Withings: days align to Europe/Stockholm calendar dates (no 04:00 cutover).
- Garmin: day partitioning follows vendor/device local semantics and can vary with travel.

---

## Privacy Note
- Manifests are PII-free by convention: never include emails, usernames, tokens, secrets, or similar sensitive content.

---

## Examples

### Minimal Successful Manifest
```json
{
  "schema_version": "runmeta/1.0",
  "run_id": "garmin-20251030-01",
  "vendor": "garmin",
  "started_at": "2025-10-30T06:45:12+01:00",
  "finished_at": "2025-10-30T06:52:40+01:00",
  "timezone": "Europe/Stockholm",
  "params": {
    "start_date": "2025-10-29",
    "end_date": "2025-10-29",
    "preset": "daily",
    "out_root": "out",
    "skip_existing": false,
    "dry_run": false
  },
  "totals": {
    "days_scheduled": 1,
    "days_done": 1,
    "endpoints": { "success": 12, "skipped": 0, "error": 0, "written": 12 },
    "bytes_payload": 1832456,
    "duration_s": 448
  },
  "progress": {
    "2025-10-29": {
      "status": "done",
      "endpoints": {
        "activities-for-date": { "status": "success", "written": true, "items": 1, "bytes_payload": 24567 }
      },
      "run": { "correlation": "garmin-20251030-01:2025-10-29" }
    }
  },
  "aborted": null,
  "notes": []
}
```

### Aborted Manifest
```json
{
  "schema_version": "runmeta/1.0",
  "run_id": "withings-1761727660",
  "vendor": "withings",
  "started_at": "2025-10-29T09:40:02+01:00",
  "timezone": "Europe/Stockholm",
  "params": {
    "start_date": "2025-10-27",
    "end_date": "2025-10-29",
    "preset": "measures",
    "out_root": "out",
    "skip_existing": true,
    "dry_run": false
  },
  "totals": {
    "days_scheduled": 3,
    "days_done": 2,
    "endpoints": { "success": 6, "skipped": 1, "error": 1, "written": 7 },
    "bytes_payload": 421337,
    "duration_s": 732
  },
  "progress": {
    "2025-10-27": { "status": "done" },
    "2025-10-28": { "status": "done" },
    "2025-10-29": {
      "status": "error",
      "endpoints": {
        "measures": { "status": "error", "written": false }
      }
    }
  },
  "aborted": {
    "code": "HTTP_429",
    "message": "Rate limit exceeded",
    "at": "2025-10-29T09:48:55+01:00",
    "last_endpoint": "measures"
  },
  "notes": [
    "Retry suggested after vendor cooldown expires."
  ]
}
```
