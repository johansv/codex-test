# Repository Guidelines

Adopt Python 3.11, uv, and pytest for consistent workflows.

## Project Structure & Module Organization
- Stage runtime code inside <code>src/agentlab/</code> by capability (e.g., <code>src/agentlab/parsers.py</code>, <code>src/agentlab/runners/</code>).
- House contracts in <code>src/agentlab/core/</code>, shared helpers in <code>src/agentlab/utils/</code>, and CLI entrypoints in <code>src/agentlab/cli/</code> registered via <code>pyproject.toml</code>.
- Mirror modules under <code>tests/</code>; keep fixtures in <code>tests/fixtures/</code>.
- Store prompts, configs, and datasets in <code>assets/</code> with provenance tracked in <code>assets/METADATA.md</code>.

## Build, Test, and Development Commands
- <code>uv sync</code> - install dependencies into the managed environment.
- <code>uv run python -m agentlab.cli.dev</code> - start the interactive agent loop for manual testing.
- <code>uv run python -m agentlab.cli.worker</code> - run the background worker for CI or hosted runs.
- <code>uv run pytest</code> - execute the automated suite; add <code>uv run coverage run -m pytest</code> before releases.
- Expose wrappers in <code>scripts/dev.*</code>, <code>scripts/test.*</code>, and <code>scripts/setup.*</code>.

## Coding Style & Naming Conventions
- Enforce 4-space indentation and a 100-character soft limit.
- Modules and functions use <code>snake_case</code>; directories use <code>kebab-case</code>; classes and protocols use <code>PascalCase</code>.
- Format with <code>uv run ruff format</code> and lint via <code>uv run ruff check src tests</code> before pushing.

## Testing Guidelines
- Pair each feature with mirrored tests named for behavior (e.g., <code>test_handles_partial_messages</code>) and keep fixtures deterministic inside <code>tests/fixtures/</code>.
- Mark long scenarios with <code>pytest.mark.slow</code> and toggle via <code>PYTEST_ADDOPTS</code>.

## Commit & Pull Request Guidelines
- Use Conventional Commits (<code>feat:</code>, <code>fix:</code>, <code>docs:</code>) with optional scopes (<code>feat(parser): ...</code>) and reference issues (<code>Refs #12</code>).
- When suggesting commit messages, always include the matching requirement trailer (e.g., `Refs REQ-F-...`) so traceability stays intact.
- PRs supply summary, tests run, coverage notes, and supporting screenshots/logs; promote from draft after <code>uv run pytest</code> and <code>uv run ruff check</code> succeed locally.

## Agent-Specific Instructions
- Check in sanitized secrets via <code>.env.example</code> and load them with <code>python-dotenv</code> locally only.
- Document environment variables in <code>docs/environment.md</code> and publish smoke probes under <code>scripts/smoke/<integration>.py</code> with matching mocks in <code>tests/mocks/</code>.

## Requirements Workflow
1. **Requirements Phase (default)**
   - Codex captures the user prompt in dry-run mode first and proposes one or more requirements (IDs, narrative, acceptance criteria, priority, reason) without writing to disk.
   - If the prompt is vague or conflicts with existing requirements, Codex asks clarifying questions or suggests splitting into multiple requirements.
   - Once the user approves the wording, Codex records the requirement(s) with `Status: active` (or the chosen status) and the agreed `Reason`, then stops unless instructed to continue.
2. **Planning Phase (optional)**
   - After requirements are accepted, Codex can draft an implementation plan. Codex waits for user approval before moving on.
   - Users may skip this step entirely by requesting implementation immediately.
3. **Implementation Phase**
   - Codex writes code/tests only after the requirement phase (and, if used, the plan phase) is approved. All commits reference the requirement IDs.

### Workflow Controls
- **Default behavior:** Run the Requirements phase only and pause.
- **Advance to planning:** User explicitly requests "Plan implementation" (or similar wording).
- **Skip planning:** User says "Implement now" after requirements approval.
- **Run all phases automatically:** User states upfront "Run full workflow" (or equivalent); Codex proceeds through requirements -> plan -> implementation without additional confirmation.
- Requirements must carry one of the statuses `proposed`, `active`, `satisfied`, `rejected`, or `superseded`, with a short `Reason:` explaining why the status applies.
- Codex should flag requirements that look too large or too small, suggesting splits or merges before recording them when scope warrants it.
- Use the commit trailer `Refs <requirement-id>` on every related commit to keep traceability searchable.

### Catalog Updates
- Codex may persist approved requirements to the catalogs on request, even when planning or implementation is deferred; treat this as completing the requirements phase while leaving later phases pending.
- Codex can persist catalog entries as `proposed` when the user wants more review; they stay in the catalog but must not advance to planning or implementation until promoted to `active`.
- When a user requests planning or implementation for a requirement still marked `proposed`, Codex must revisit the requirement review flow and wait for an explicit status update before proceeding.
- Always write catalog and log entries through the reqflow helpers or CLI wrappers so IDs use the timestamp format and summaries stay correct; never hand-edit requirements files directly.

#### Status Definitions
- `proposed`: Catalog entry under review; keep it visible for refinement but block planning or implementation until promoted to `active`.
- `active`: Approved requirement ready for planning and implementation; keep the reason current and maintain trace fields as work progresses.
- `satisfied`: Requirement fulfilled by merged code/tests; move the entry to the satisfied section and refresh trace links to the verifying commits/tests.
- `rejected`: Decision not to pursue the requirement; document why it will not move forward.
- `superseded`: Requirement replaced by a newer one; cross-reference the successor ID in both entries.
