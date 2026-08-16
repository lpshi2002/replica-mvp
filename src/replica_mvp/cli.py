from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .builder import run_built_replica
from .codex_operator import finalize_codex_operator, prepare_codex_operator
from .experience import experience_input_once, experience_once
from .intake import receive_second_pass
from .project import build_project, evaluate_project, init_project, write_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="replica-mvp",
        description="Build and evaluate a public-evidence-bounded AI replica.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    intake = sub.add_parser("intake", help="Receive a second-pass result JSON.")
    intake.add_argument("source", type=Path)
    intake.add_argument("--workspace", type=Path, required=True)

    prepare_operator = sub.add_parser(
        "prepare-operator",
        help="Prepare a test-hidden task for the Codex operator skill.",
    )
    prepare_operator.add_argument("source", type=Path)
    prepare_operator.add_argument("--workspace", type=Path, required=True)
    prepare_operator.add_argument(
        "--evaluation-vault",
        type=Path,
        required=True,
        help="Private evaluator root outside the public workspace.",
    )

    finalize_operator = sub.add_parser(
        "finalize-operator",
        help="Validate and evaluate an operator written by the Codex skill.",
    )
    finalize_operator.add_argument("task", type=Path)
    finalize_operator.add_argument("--workspace", type=Path, required=True)
    finalize_operator.add_argument(
        "--evaluation-vault",
        type=Path,
        required=True,
        help="Private evaluator root used when the task was prepared.",
    )
    finalize_operator.add_argument(
        "--report",
        action="store_true",
        help="Also create report.json and report.md.",
    )

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

    run_replica = sub.add_parser(
        "run-replica",
        help="Run a built Replica with a JSON object read from stdin.",
    )
    run_replica.add_argument("path", type=Path)

    experience = sub.add_parser(
        "experience",
        help="Run a built Replica and show a human-readable result.",
    )
    experience.add_argument("path", type=Path)
    experience.add_argument(
        "--profile",
        type=Path,
        help="Override the experience.json published in the run directory.",
    )
    experience.add_argument(
        "--question",
        help="Run one question instead of starting an interactive session.",
    )
    experience.add_argument(
        "--original-observations",
        type=Path,
        help="Compare one question with a recorded original output.",
    )
    experience.add_argument(
        "--input",
        dest="input_path",
        type=Path,
        help="Run a non-conversational Replica with a JSON input file.",
    )
    experience.add_argument(
        "--output",
        type=Path,
        help="Write an HTML Replica result to a new preview file.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "intake":
            result = receive_second_pass(args.source, args.workspace)
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "prepare-operator":
            result = prepare_codex_operator(
                args.source,
                args.workspace,
                args.evaluation_vault,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "finalize-operator":
            result = finalize_codex_operator(
                args.task,
                args.workspace,
                args.evaluation_vault,
                include_report=args.report,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "init":
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
        elif args.command == "run-replica":
            replica_input = json.loads(sys.stdin.read())
            output = run_built_replica(args.path, replica_input)
            print(json.dumps(output, ensure_ascii=False, allow_nan=False))
        elif args.command == "experience":
            profile = args.profile or args.path / "experience.json"
            if args.input_path is not None:
                if (
                    args.question is not None
                    or args.profile is not None
                    or args.original_observations is not None
                ):
                    raise ValueError(
                        "--input cannot be combined with question experience"
                    )
                print(
                    experience_input_once(
                        args.path,
                        args.input_path,
                        args.output,
                    )
                )
                return 0
            if args.output is not None:
                raise ValueError("--output requires --input")
            if (
                args.original_observations is not None
                and args.question is None
            ):
                raise ValueError(
                    "original observations require a one-shot --question"
                )
            if args.question is not None:
                print(
                    experience_once(
                        args.path,
                        profile,
                        args.question,
                        args.original_observations,
                    )
                )
            else:
                while True:
                    try:
                        question = input("질문> ")
                    except EOFError:
                        break
                    if question.strip().lower() in {"/quit", "/exit"}:
                        break
                    if not question.strip():
                        continue
                    print(experience_once(args.path, profile, question))
        else:
            write_report(args.path)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0
