# CHATGPT_PLAYBOOK
**Purpose:** Stable instructions for ChatGPT when assisting this project.
**Audience:** ChatGPT (assistant) + Developer (single developer).
**Goal:** Efficient, low-context collaboration where ChatGPT shapes requirements and prepares Codex prompts; Codex writes & edits code.

> **Scope & Pointers**
> - This PLAYBOOK governs the prompting workflow only.
> - All functional/non-functional requirements live in `docs/requirements/*.md`.
> - Any concrete schemas/specs live outside the PLAYBOOK (e.g., `docs/runmeta/SCHEMA.md`).

## Language & Localization (Project-wide)

**Policy:**
- Assistant reply language = **the language of the user’s prompt for this project** (per message).
- **All project artifacts** (source code, file contents, comments, commit messages we suggest, docs, specs, prompts intended for files) **must be in English** unless the user explicitly instructs otherwise for a specific file.
- Do **not** auto-translate user prompts. If a user asks in another language but the output is a project file, the file content stays **English**; the surrounding explanation may follow the prompt language.
- If a conflict arises, file language (English) overrides reply language for the **artifact content** only.

---

## 0) Project snapshot (what to assume)
- For product architecture, behaviors, privacy, manifests, and other specifics, refer to `docs/requirements/*.md` or linked specs.
- Maintain the user preference defaults: structured output, concise reasoning, explicit assumptions, honest uncertainty; avoid flattery.

---

## 1) Ways of working (contract)
1. **Requirements first, then tests, then code (via Codex).**
2. ChatGPT's job:
   - Pressure-test and finalize requirements (clear, observable ACs + invariants).
   - Produce **Codex prompts** that: (a) capture/update docs, (b) generate tests, (c) implement minimal code in slices.
   - Keep changes **surgical**, reuse helpers, and avoid workflow changes unless explicitly requested.
3. Codex's job:
   - Apply the prompts, write code/tests/docs, and keep diffs minimal.
4. Refer to `docs/requirements/*.md` for alignment, observability, and any product behavior expectations.

---

## 2) Canonical invariants (pin these; don't drift)
- Product invariants (schemas, cutovers, privacy rules, etc.) live in `docs/requirements/*.md` and supporting specs like `docs/runmeta/SCHEMA.md`. Link to them rather than copying into prompts.

---

## 3) Minimal context syncing (how you keep me up-to-date)
When starting a session, paste this **AI sync snippet** (adjust N):

```
Project: Garmin/Withings ingest
Branch: <name>  |  HEAD: <short hash>  |  Python: <version>

Active REQ: <ID - Title>
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

Status: todo | Owner: codex | Priority: high | Reason: <one line>.

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
2) Update STATUS SUMMARY (todo -> todo-1, doing++).
3) Append docs/requirements/log.md: WHEN - Started REQ_ID [doing] (branch: BRANCH).
```

### 4.3 Generate tests from ACs (tests only)
```
Create tests under <target folder> mirroring the Acceptance Criteria for "<REQ_ID - Title>".

Rules:
- One small test per AC (~40 LOC each), using tmp_path for IO.
- Tiny fixtures (~30 lines) instead of big scaffolds.
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
- Check `docs/requirements/*.md` for invariants (manifests, privacy, etc.) and follow them without restating here.
- Stop when tests are green.
```

### 4.5 Docs-only pass
Focus doc prompts on process summaries or link to requirements for product details; avoid restating behavior here.

### 4.6 Mark requirement done
```
Edit requirements docs only.

Inputs:
- REQ_ID, WHEN (now), TESTS (node ids or file paths), COMMITS (short hashes)

Steps:
1) Set Status: done; update "Updated" to WHEN.
2) In "Trace", append: Finished: WHEN; Tests: TESTS; Commits: COMMITS.
3) Update STATUS SUMMARY (todo -> todo-1, doing++).
4) Append docs/requirements/log.md: WHEN - Finished REQ_ID [done].
```

---

## 5) Ready-made requirement templates (for this repo)

### 5.1 Requirement template
Use section 4.1 with the requirement text supplied in-session. For canonical acceptance criteria or schemas, point to `docs/requirements/*.md` instead of repeating them here.

---

## 6) Debugging & guardrails (what ChatGPT should always check)
- Confirm CLI entrypoints and arguments when drafting commands, but rely on requirements for expected outputs.
- Never assume internet; tests must run offline with tiny fixtures and fakes.
- Prefer reuse of existing helpers to keep diffs small.
- Surface uncertainty explicitly and link to the relevant requirement for resolution.

---

## 7) Security & privacy (process reminders)
- Follow repository security conventions; see `docs/requirements/*.md` for specific constraints.
- Use dummy tokens/IDs in fixtures and redact secrets in prompts or diffs.

---

## 8) Rate limits (process reminders)
- Mention rate-limit handling only when instructions or requirements call for it; avoid restating policies here.

---

## 9) Ready-to-paste Codex sequences (quick starts)
- Default sequence: capture requirement (4.1) -> move to doing (4.2) -> generate tests (4.3) -> implement slice (4.4) -> docs-only update (4.5) -> mark done (4.6).
- Add or remove steps only when requirements or the user request a different flow.
- Reference the requirements catalog for any feature-specific details.

---

## 10) How to ask ChatGPT (you) for help without re-explaining
- Paste the **AI sync snippet** (Section 3).
- Say what you want next (e.g., "prepare Codex prompt for tests of X", "tighten REQ for Y", "draft minimal slice for Z").
- If you need a decision (amend existing REQ vs new REQ), say "decide and justify".

---

**End of playbook.**
Commit this file to `docs/ai/CHATGPT_PLAYBOOK.md` and refer to it at the start of future sessions.
```
