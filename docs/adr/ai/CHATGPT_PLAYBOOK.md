# CHATGPT_PLAYBOOK.md
**Purpose:** Stable instructions for ChatGPT when assisting this project.  
**Audience:** ChatGPT (assistant) + Johan (single developer).  
**Goal:** Efficient, low-context collaboration where ChatGPT shapes requirements and prepares Codex prompts; Codex writes & edits code.

---

## 0) Project snapshot (what to assume)
- Architecture: **L0 (vendor-raw JSON + meta)** → **L1 (normalized Parquet via DuckDB)** → higher layers (later).
- Vendors: **Garmin (garminconnect)** and **Withings** (OAuth2).
- Timezone policy: **Europe/Stockholm**, **04:00 cutover** for day bucketing.
- Run manifest: one JSON per run under `runs/`, updated at start/per-day/finish; immutable `ended_at`, `aborted`.
- Idempotency: per-day partition overwrites; `--skip-existing`; `--resume` respects run manifest.
- Privacy: no PII/tokens in artifacts or logs; secrets in `secrets/…` (git-ignored).
- Rate limiting: implement **Retry-After** + capped backoff with jitter; treat any vendor hard limit conservatively.
- User preferences: structured output, concise reasoning, explicit assumptions, honest uncertainty; avoid flattery.

---

## 1) Ways of working (contract)
1. **Requirements first, then tests, then code (via Codex).**
2. ChatGPT’s job:
   - Pressure-test and finalize requirements (clear, observable ACs + invariants).
   - Produce **Codex prompts** that: (a) capture/update docs, (b) generate tests, (c) implement minimal code in slices.
   - Keep changes **surgical**, reuse helpers, and avoid workflow changes unless explicitly requested.
3. Codex’s job:
   - Apply the prompts, write code/tests/docs, and keep diffs minimal.
4. **Alignment policy:** New sources (e.g., Withings L0) **must behave like Garmin L0** unless there’s a compelling vendor reason not to. Deviations must be stated in the requirement.
5. **Observability:** Every feature that affects ingest must surface in the run manifest and INFO logs:
   - Start: `Run manifest: {path}`
   - Finish: `Run totals: {totals}`, where totals include endpoint breakdowns.

---

## 2) Canonical invariants (pin these; don’t drift)
- **Run manifest schema (core):**
  - `run_id`, `started_at`, optional `ended_at` (immutable once set)
  - `params {start_date, end_date, preset?, skip_existing:bool, resume:bool}`
  - `env {garminconnect_version|"unknown", python_version, timezone}`
  - `progress["YYYY-MM-DD"] = {status: done|partial|skipped, endpoints_ok, endpoints_fail, endpoints_skipped, bytes_payload, duration_s, last_endpoint?}`
  - `totals = {days_done, endpoints:{written, success, error, skipped}, bytes_payload, duration_s}`
  - `written == success + error`
  - Atomic writes (temp + replace). Idempotent totals. No PII.
- **L0 meta.json (per file):**
  - `{run_id, vendor, endpoint, date, timezone:"Europe/Stockholm", day_cutover:"04:00", request:{from,to}, status:"success|error|skipped", items:int, bytes:int, wrote_at, error?:{code,msg,retry_after_s?}}`
- **Day bucketing:** measurements with local time **00:00–03:59 → previous day**, else same day.
- **Idempotency:** `--skip-existing` avoids overwriting success; `--resume` starts at first non-done day (manifest-driven).

---

## 3) Minimal context syncing (how you keep me up-to-date)
When starting a session, paste this **AI sync snippet** (adjust N):

```
Project: Garmin/Withings ingest
Branch: <name>  |  HEAD: <short hash>  |  Python: <version>

Active REQ: <ID — Title>
Contracts changed: <none|list>
Key files: <paths>

Last commits:
- <h> <date> <message>
- <h> <date> <message>

Status:
- Tests failing: <count> (paste node ids or short trace)
- Next step wanted from ChatGPT: <e.g., prep Codex prompt for tests/code/docs>
```

Optional: keep `docs/ai/AI_BRIEF.md` updated; paste first ~200 lines when asked.

---

## 4) Standard Codex prompt blocks (reuse as-is)

### 4.1 Capture a new requirement (docs only)
```
Edit only docs/requirements/functional.md and docs/requirements/log.md.

Insert a new functional requirement titled:
"<TITLE>"

Status: todo | Owner: johan | Priority: high | Reason: <one line>.

Use the content provided in this message verbatim for:
- Narrative
- Interfaces & Artifacts
- Acceptance Criteria (observable)
- Edge cases & invariants
- Test Plan (AI-owned)

Update STATUS SUMMARY counts and append a log line with current local timestamp.
No source code changes.
```

### 4.2 Move requirement to doing (when implementation starts)
```
Edit requirements docs only.

Inputs:
- REQ_ID: <id>
- WHEN: now (local)
- BRANCH: <branch>

Steps:
1) In docs/requirements/functional.md: set REQ_ID Status: doing; append Trace: Started: WHEN; Branch: BRANCH.
2) Update STATUS SUMMARY (todo−−, doing++).
3) Append docs/requirements/log.md: WHEN — Started REQ_ID [doing] (branch: BRANCH).
```

### 4.3 Generate tests from ACs (tests only)
```
Create tests under <target folder> mirroring the Acceptance Criteria for "<REQ_ID — Title>".

Rules:
- One small test per AC (≤40 LOC each), using tmp_path for IO.
- Tiny fixtures (≤30 lines) instead of big scaffolds.
- Insert the exact AC text as a docstring at the top of each test.
- Assume the future public API surface indicated in the requirement (import paths/types).
- Do NOT edit src code.
```

### 4.4 Implement minimal code to make just-added tests pass (slice)
```
Goal: Make ONLY the tests created in <folder> pass. Keep diffs surgical.

Create/Edit only the files required by the tests. Reuse existing helpers (cutover, manifest, atomic write, backoff).

Constraints:
- No new CLI flags or workflow changes unless the requirement says so.
- Implement the smallest public surface necessary; keep internal details private.
- Preserve invariants: atomic writes, idempotent totals, immutable ended_at/aborted, no PII in logs.
- Stop when tests are green.
```

### 4.5 Docs-only pass
```
Docs only. No behavior changes.

Update README or docs/README with a short section:
- What the feature does (6–8 lines).
- Paths, cutover, meta keys (brief).
- Log lines (start/finish) and privacy note.

Save docs only.
```

### 4.6 Mark requirement done
```
Edit requirements docs only.

Inputs:
- REQ_ID, WHEN (now), TESTS (node ids or file paths), COMMITS (short hashes)

Steps:
1) Set Status: done; update "Updated" to WHEN.
2) In "Trace", append: Finished: WHEN; Tests: TESTS; Commits: COMMITS.
3) Update STATUS SUMMARY (doing−−, done++).
4) Append docs/requirements/log.md: WHEN — Finished REQ_ID [done].
```

---

## 5) Ready-made requirement templates (for this repo)

### 5.1 Withings L0 ingest (aligned with Garmin L0) — drop-in text
**Title:** Withings L0 ingest for body metrics (daily raw JSON + metadata) – aligned with Garmin L0  
**Narrative:** Store vendor-raw Withings “measures” per local day under `l0/withings/YYYY-MM-DD` with `.meta.json`, aligned with the Garmin L0 workflow (CLI flags, cutover, idempotency, manifest).  
**Interfaces & Artifacts:**
- CLI: `agentlab withings fetch --start-date … --end-date … --out-root … [--dry-run] [--skip-existing] [--resume]`
- L0 path: `<out_root>/l0/withings/<YYYY-MM-DD>/measures-<page_or_ts>.json`
- Meta path: same folder, `measures-<page_or_ts>.meta.json`
- Run manifest: update per day like Garmin (`progress[day]`, `totals.endpoints.{success,error,skipped,written}`, `bytes_payload`, `duration_s`)
- Tokens: `secrets/withings_tokens.json` (OAuth2); no PII in logs/artifacts
- TZ & cutover: `Europe/Stockholm`, `04:00` local
**Acceptance Criteria (observable):**
1) Per-day JSON+meta with keys `{run_id,vendor:"withings",endpoint:"measures",date,timezone,day_cutover,request:{from,to},status,items,bytes,wrote_at,error?}`  
2) Cutover 04:00: 00:00–03:59 → previous day; else same day.  
3) Idempotency: re-run doesn’t duplicate; `--skip-existing` avoids overwriting success (optional `status:"skipped"` meta).  
4) Error capture: write `measures.error.json` + `.meta.json` on failure; manifest error counters update.  
5) Rate limits/backoff: honor Retry-After; else exponential + jitter, cap 15 min; give up after 3 attempts/day.  
6) Privacy: no email/names/tokens in artifacts/logs.  
7) `--resume`: start at first non-done day per run-manifest.  
**Edge cases & invariants:** unique file names per page/window; ISO-8601 timestamps with offset; single user.  
**Test Plan (AI-owned):**  
- `test_writes_day_folder_and_meta_success`  
- `test_cutover_0400_routes_measurements_correctly`  
- `test_skip_existing_is_idempotent`  
- `test_error_artifacts_on_failure`  
- `test_retry_after_and_backoff`  
- `test_resume_starts_from_first_incomplete_day`  
- `test_no_pii_in_artifacts_and_logs`

*(Use section 4.1 to insert this block.)*

---

## 6) Debugging & guardrails (what ChatGPT should always check)
- If a CLI appears “silent”, verify:
  1) the **entrypoint** exists in `pyproject.toml` (script vs subcommand),
  2) `--out-root` is provided, and
  3) logging is at least INFO (and prints start/finish lines).
- Never assume internet; tests must run offline with tiny fixtures and fakes.
- Prefer **reuse** of Garmin helpers (cutover, backoff, manifest, atomic write).
- Be explicit when a fact is uncertain or vendor docs may differ; propose tests to lock behavior.

---

## 7) Security & privacy (non-negotiable)
- `secrets/` git-ignored; token files `chmod 600`.
- Redact `client_secret`, `access_token`, `refresh_token` in any logs/errors.
- No emails or names in artifacts.
- In tests/fixtures, use dummy IDs/tokens.

---

## 8) Rate limits (operational defaults)
- Treat per-vendor limits conservatively; throttle client-side.
- On **429**: if `Retry-After` present, wait exactly that; else backoff with jitter, capped at 15 min; max 3 attempts/day.

---

## 9) Ready-to-paste Codex sequences (quick starts)

**Withings L0 end-to-end (first time):**
1) *Capture REQ:* use **4.1** with **5.1** content.  
2) *Set doing:* use **4.2**.  
3) *Generate tests:* use **4.3** (folder `tests/withings_l0/`).  
4) *Implement slice:* use **4.4** (create `withings.fetcher` + CLI; reuse helpers).  
5) *Docs pass:* use **4.5** (short README section).  
6) *Mark done:* use **4.6**.

**Run-manifest doc update (finish totals with breakdowns):**
Use **4.5** and explicitly include:  
`INFO Run totals: {"days_done":N,"endpoints":{"written":X,"success":A,"error":B,"skipped":C},"bytes_payload":BYTES,"duration_s":SECS}`

---

## 10) How to ask ChatGPT (you) for help without re-explaining
- Paste the **AI sync snippet** (Section 3).
- Say what you want next (e.g., “prepare Codex prompt for tests of X”, “tighten REQ for Y”, “draft minimal slice for Z”).
- If you need a decision (amend existing REQ vs new REQ), say “decide and justify”.

---

**End of playbook.**  
Commit this file to `docs/ai/CHATGPT_PLAYBOOK.md` and refer to it at the start of future sessions.
