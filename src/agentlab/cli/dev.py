"""Developer CLI integrating automatic requirement capture."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agentlab.core.middleware import auto_capture_prompt, should_block_for_manual_update


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run development tasks with enforced requirement capture.",
    )
    parser.add_argument(
        "--prompt",
        help="Task prompt; if omitted, read from stdin.",
    )
    parser.add_argument(
        "--prompt-file",
        type=Path,
        help="File containing the prompt text.",
    )
    parser.add_argument(
        "--catalog-root",
        type=Path,
        help="Override discovery of docs/requirements directory.",
    )
    parser.add_argument(
        "--reference",
        default="prompt",
        help="Reference identifier recorded with the requirement.",
    )
    parser.add_argument(
        "--author",
        default="codex",
        help="Author recorded in the requirements log (default: codex).",
    )
    parser.add_argument(
        "--force-new",
        action="store_true",
        help="Force creation of a new requirement even if similar ones exist.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyse the prompt without modifying catalogs or logs.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    prompt = _load_prompt(args, parser)

    action = auto_capture_prompt(
        prompt,
        reference=args.reference,
        catalog_root=args.catalog_root,
        author=args.author,
        force_new=args.force_new,
        dry_run=args.dry_run,
    )

    print(action.message)

    if should_block_for_manual_update(action):
        print(
            "Halting development until the existing requirement is updated.",
            file=sys.stderr,
        )
        return 1

    if action.adr_path:
        print(f"Review ADR draft: {action.adr_path}")

    print("Proceed with implementation referencing the captured requirement.")
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
    try:
        return sys.stdin.read()
    except OSError as exc:
        parser.error(str(exc))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
