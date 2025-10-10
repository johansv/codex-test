"""CLI to reopen multiple requirements as amendments in one invocation."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from reqflow.catalog import (
    append_log_entry,
    bulk_reopen_functional_requirements,
    catalog_root,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reopen multiple requirements under a primary requirement, adding "
            "consistent amendment and log metadata."
        ),
    )
    parser.add_argument(
        "--catalog-root",
        type=Path,
        default=None,
        help="Override auto-detection of the docs/requirements directory.",
    )
    parser.add_argument(
        "--primary",
        required=True,
        help="Primary requirement ID the amendments will reference.",
    )
    parser.add_argument(
        "--reason",
        required=True,
        help="Summary explaining why the bulk amendment is needed.",
    )
    parser.add_argument(
        "--author",
        default="codex",
        help="Author recorded in the requirements log (default: codex).",
    )
    parser.add_argument(
        "--reference",
        default="implementation",
        help="Reference captured in the change log (default: implementation).",
    )
    parser.add_argument(
        "--summary",
        default=None,
        help="Optional change-log summary for each reopened requirement.",
    )
    parser.add_argument(
        "--allow-doing",
        action="store_true",
        help="Allow already in-progress amendments to be refreshed.",
    )
    parser.add_argument(
        "requirements",
        nargs="+",
        help="Requirement IDs to reopen as amendments.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        catalog_dir = (
            args.catalog_root
            if args.catalog_root is not None
            else catalog_root(Path.cwd())
        )
    except FileNotFoundError as exc:  # pragma: no cover - defensive guard
        parser.error(str(exc))
        return 2

    functional_path = catalog_dir / "functional.md"
    if not functional_path.exists():
        parser.error("functional catalog not found; run setup first")
        return 2

    log_path = catalog_dir / "log.md"
    if not log_path.exists():
        parser.error("log.md not found in catalog directory")
        return 2

    try:
        reopened = bulk_reopen_functional_requirements(
            functional_path,
            primary_id=args.primary,
            amendment_ids=args.requirements,
            reason=args.reason,
            allow_doing=args.allow_doing,
        )
    except ValueError as exc:
        parser.error(str(exc))
        return 2

    summary_template = args.summary or "Bulk reopened {req_id} under {primary}"
    for req_id in reopened:
        append_log_entry(
            log_path,
            req_id=req_id,
            change_summary=summary_template.format(
                req_id=req_id,
                primary=args.primary,
            ),
            author=args.author,
            reference=args.reference,
        )

    if reopened:
        print(
            "Reopened the following requirements under "
            f"{args.primary}: {', '.join(reopened)}"
        )
    else:
        print("No requirements reopened.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
