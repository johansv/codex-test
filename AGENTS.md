# Repository Guidelines

Adopt Python 3.11, uv, and pytest for consistent workflows.

## Project Structure & Module Organization
- Stage runtime code inside <code>src/agentlab/</code> by capability (e.g., <code>src/agentlab/parsers.py</code>, <code>src/agentlab/runners/</code>).
- House contracts in <code>src/agentlab/core/</code>, shared helpers in <code>src/agentlab/utils/</code>, and CLI entrypoints in <code>src/agentlab/cli/</code> registered via <code>pyproject.toml</code>.
- Mirror modules under <code>tests/</code>; keep fixtures in <code>tests/fixtures/</code>.
- Store prompts, configs, and datasets in <code>assets/</code> with provenance tracked in <code>assets/METADATA.md</code>.

## Build, Test, and Development Commands
- <code>uv sync</code> – install dependencies into the managed environment.
- <code>uv run python -m agentlab.cli.dev</code> – start the interactive agent loop for manual testing.
- <code>uv run python -m agentlab.cli.worker</code> – run the background worker for CI or hosted runs.
- <code>uv run pytest</code> – execute the automated suite; add <code>uv run coverage run -m pytest</code> before releases.
- Expose wrappers in <code>scripts/dev.*</code>, <code>scripts/test.*</code>, and <code>scripts/setup.*</code>.

## Coding Style & Naming Conventions
- Enforce 4-space indentation and a 100-character soft limit.
- Modules and functions use <code>snake_case</code>; directories use <code>kebab-case</code>; classes and protocols use <code>PascalCase</code>.
- Format with <code>uv run ruff format</code> and lint via <code>uv run ruff check src tests</code> before pushing.

## Testing Guidelines
- Pair each feature with mirrored tests named for behavior (e.g., <code>test_handles_partial_messages</code>) and keep fixtures deterministic inside <code>tests/fixtures/</code>.
- Mark long scenarios with <code>pytest.mark.slow</code> and toggle via <code>PYTEST_ADDOPTS</code>.

## Commit & Pull Request Guidelines
- Use Conventional Commits (<code>feat:</code>, <code>fix:</code>, <code>docs:</code>) with optional scopes (<code>feat(parser): …</code>) and reference issues (<code>Refs #12</code>).
- PRs supply summary, tests run, coverage notes, and supporting screenshots/logs; promote from draft after <code>uv run pytest</code> and <code>uv run ruff check</code> succeed locally.

## Agent-Specific Instructions
- Check in sanitized secrets via <code>.env.example</code> and load them with <code>python-dotenv</code> locally only.
- Document environment variables in <code>docs/environment.md</code> and publish smoke probes under <code>scripts/smoke/&lt;integration&gt;.py</code> with matching mocks in <code>tests/mocks/</code>.
