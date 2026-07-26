from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .project import (
    build_project,
    evaluate_project,
    finalize_first_pass,
    init_project,
    write_report,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="replica-mvp",
        description="Build and evaluate a public-evidence-bounded AI replica.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create a five-stage Replica project.")
    init.add_argument("path", type=Path)
    init.add_argument("--name", required=True)
    init.add_argument("--company", required=True)
    init.add_argument("--url", required=True)
    init.add_argument("--capability", required=True)
    init.add_argument(
        "--evidence-level",
        choices=("direct", "public", "claim_only"),
        default="claim_only",
    )

    build = sub.add_parser("build", help="Build replica.json from evidence and spec.")
    build.add_argument("path", type=Path)

    evaluate = sub.add_parser("evaluate", help="Run test cases and write the report.")
    evaluate.add_argument("path", type=Path)
    evaluate.add_argument("--replica-command", required=True)
    evaluate.add_argument("--judge-command", required=True)
    evaluate.add_argument("--timeout", type=int, default=120)

    report = sub.add_parser("report", help="Regenerate report.md from results.jsonl.")
    report.add_argument("path", type=Path)

    finalize = sub.add_parser(
        "finalize-pass-1",
        help="Validate pass-1 checkpoints and scored claims.",
    )
    finalize.add_argument("path", type=Path, help="Company root, e.g. work/acme")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init":
            init_project(
                args.path,
                name=args.name,
                company=args.company,
                url=args.url,
                capability=args.capability,
                evidence_level=args.evidence_level,
            )
        elif args.command == "build":
            build_project(args.path)
        elif args.command == "evaluate":
            evaluate_project(
                args.path,
                replica_command=args.replica_command,
                judge_command=args.judge_command,
                timeout=args.timeout,
            )
        elif args.command == "report":
            write_report(args.path)
        else:
            finalize_first_pass(args.path)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0
