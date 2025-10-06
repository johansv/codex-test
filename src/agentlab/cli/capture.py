"""CLI gateway to capture requirements before executing tasks."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agentlab.core.requirements_planner import RequirementPlanner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ensure requirements are captured prior to implementation.",
    )
    parser.add_argument(
        "--prompt",
        help="Prompt or task description to analyse. If omitted, read from stdin.",
    )
    parser.add_argument(
        "--prompt-file",
        type=Path,
        help="Path to a file containing the prompt text.",
    )
    parser.add_argument(
        "--catalog-root",
        type=Path,
        help="Override auto-detection of the docs/requirements directory.",
    )
    parser.add_argument(
        "--author",
        default="codex",
        help="Author recorded in the requirements log (default: codex).",
    )
    parser.add_argument(
        "--reference",
        default="prompt",
        help="Reference or task identifier captured in the log (default: prompt).",
    )
    parser.add_argument(
        "--owner",
        help="Override inferred owner for the requirement.",
    )
    parser.add_argument(
        "--category",
        help="Override inferred category for non-functional requirements.",
    )
    parser.add_argument(
        "--priority",
        choices=["low", "medium", "high"],
        help="Override inferred priority for the requirement.",
    )
    parser.add_argument(
        "--force-new",
        action="store_true",
        help="Create a new requirement even if a similar one exists.",
    )
    parser.add_argument(
        "--summary",
        help="Custom log summary text.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyse prompt without modifying the catalog.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    prompt_text = _load_prompt(args, parser)

    try:
        planner = RequirementPlanner(args.catalog_root)
    except FileNotFoundError as exc:  # pragma: no cover - defensive guard
        parser.error(str(exc))
        return 2

    action = planner.ensure_requirement(
        prompt_text,
        reference=args.reference,
        author=args.author,
        owner=args.owner,
        category=args.category,
        priority=args.priority,
        force_new=args.force_new,
        summary=args.summary,
        dry_run=args.dry_run,
    )

    print(action.message)

    if action.outcome == "needs-update":
        return 1
    return 0


def _load_prompt(args: argparse.Namespace, parser: argparse.ArgumentParser) -> str:
    if args.prompt and args.prompt_file:
        parser.error("Provide only one of --prompt or --prompt-file.")
    if args.prompt:
        return args.prompt
    if args.prompt_file:
        return args.prompt_file.read_text(encoding="utf-8")
    if sys.stdin.isatty():
        parser.error("Provide a prompt via --prompt, --prompt-file, or piped stdin.")
    return sys.stdin.read()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
