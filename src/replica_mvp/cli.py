from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agent_execution import (
    advance_agent_execution_from_paths,
    create_agent_execution_state_file,
)
from .agent_harness import (
    finalize_agent_candidate,
    finish_agent_continuity,
    finish_agent_harness,
    prepare_agent_harness_from_path,
    record_agent_continuity_round,
    record_agent_premature_completion,
    record_agent_spawn,
    record_agent_spawn_failure,
    record_direct_agent_message,
    record_released_agent,
    start_agent_claim,
    start_agent_continuity,
)
from .agent_protocol import validate_agent_protocol_message_from_path
from .builder import run_built_replica
from .codex_operator import finalize_codex_operator, prepare_codex_operator
from .experience import experience_input_once, experience_once
from .intake import receive_second_pass
from .project import build_project, evaluate_project, init_project, write_report


def _command_arguments(value: str) -> list[str]:
    try:
        command = json.loads(value)
    except json.JSONDecodeError as error:
        raise argparse.ArgumentTypeError(
            "command must be a JSON array of arguments"
        ) from error
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(item, str) and item for item in command)
    ):
        raise argparse.ArgumentTypeError(
            "command must be a non-empty JSON array of non-empty strings"
        )
    return command


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

    harness_init = sub.add_parser(
        "agent-harness-init",
        help="Prepare claim-pair state for a real Codex Agent harness.",
    )
    harness_init.add_argument("source", type=Path)
    harness_init.add_argument("run_dir", type=Path)
    harness_init.add_argument("--replica-agent-id", required=True)
    harness_init.add_argument("--parent-agent-id", required=True)

    harness_start = sub.add_parser(
        "agent-harness-start",
        help="Activate the next sequential claim pair.",
    )
    harness_start.add_argument("registry", type=Path)
    harness_start.add_argument("claim_id")

    harness_spawned = sub.add_parser(
        "agent-harness-spawned",
        help="Record one successful real Codex Agent spawn.",
    )
    harness_spawned.add_argument("registry", type=Path)
    harness_spawned.add_argument("claim_id")
    harness_spawned.add_argument("--role", choices=("operator", "builder"), required=True)
    harness_spawned.add_argument("--agent-id", required=True)
    harness_spawned.add_argument("--parent-agent-id", required=True)
    harness_spawned.add_argument("--requested-model", required=True)

    harness_failed = sub.add_parser(
        "agent-harness-failed",
        help="Record a required Agent spawn failure without fallback.",
    )
    harness_failed.add_argument("registry", type=Path)
    harness_failed.add_argument("claim_id")
    harness_failed.add_argument("--role", choices=("operator", "builder"), required=True)
    harness_failed.add_argument("--reason", required=True)

    harness_released = sub.add_parser(
        "agent-harness-released",
        help="Confirm an orphan sibling was interrupted and release its slot.",
    )
    harness_released.add_argument("registry", type=Path)
    harness_released.add_argument("claim_id")
    harness_released.add_argument("--agent-id", required=True)

    harness_message = sub.add_parser(
        "agent-harness-message",
        help="Record one verified direct sibling message.",
    )
    harness_message.add_argument("registry", type=Path)
    harness_message.add_argument("claim_id")
    harness_message.add_argument(
        "--direction",
        choices=("operator_to_builder", "builder_to_operator"),
        required=True,
    )
    harness_message.add_argument("--sender-agent-id", required=True)
    harness_message.add_argument("--recipient-agent-id", required=True)
    harness_message.add_argument("--nonce", required=True)

    harness_finish = sub.add_parser(
        "agent-harness-finish",
        help="Finalize Replica Agent lifecycle state after all claims.",
    )
    harness_finish.add_argument("registry", type=Path)

    protocol_validate = sub.add_parser(
        "agent-protocol-validate",
        help="Validate one claim-scoped direct Agent message artifact.",
    )
    protocol_validate.add_argument("message", type=Path)
    protocol_validate.add_argument("--claim-id", required=True)
    protocol_validate.add_argument("--operator-agent-id", required=True)
    protocol_validate.add_argument("--builder-agent-id", required=True)
    protocol_validate.add_argument("--pair-nonce", required=True)
    protocol_validate.add_argument(
        "--expected-correction-number",
        type=int,
        required=True,
    )

    execution_start = sub.add_parser(
        "agent-execution-start",
        help="Create one Operator-owned Replica execution loop.",
    )
    execution_start.add_argument("state", type=Path)
    execution_start.add_argument("claim", type=Path)
    execution_start.add_argument("--claim-id", required=True)
    execution_start.add_argument("--operator-agent-id", required=True)
    execution_start.add_argument("--builder-agent-id", required=True)
    execution_start.add_argument("--pair-nonce", required=True)

    execution_advance = sub.add_parser(
        "agent-execution-advance",
        help="Advance a Replica execution loop from one direct exchange.",
    )
    execution_advance.add_argument("state", type=Path)
    execution_advance.add_argument("instruction", type=Path)
    execution_advance.add_argument("feedback", type=Path)

    continuity_start = sub.add_parser(
        "agent-continuity-start",
        help="Start one long-lived claim session for an exact sibling pair.",
    )
    continuity_start.add_argument("registry", type=Path)
    continuity_start.add_argument("claim_id")
    continuity_start.add_argument("--operator-agent-id", required=True)
    continuity_start.add_argument("--builder-agent-id", required=True)
    continuity_start.add_argument("--nonce", required=True)

    continuity_round = sub.add_parser(
        "agent-continuity-round",
        help="Record one direct round trip for a long-lived sibling pair.",
    )
    continuity_round.add_argument("registry", type=Path)
    continuity_round.add_argument("claim_id")
    continuity_round.add_argument("--round-number", type=int, required=True)
    continuity_round.add_argument("--operator-agent-id", required=True)
    continuity_round.add_argument("--builder-agent-id", required=True)
    continuity_round.add_argument("--nonce", required=True)
    continuity_round.add_argument(
        "--operator-to-builder-direct",
        action="store_true",
        required=True,
    )
    continuity_round.add_argument(
        "--builder-to-operator-direct",
        action="store_true",
        required=True,
    )

    continuity_terminal = sub.add_parser(
        "agent-continuity-terminal",
        help="Complete a sibling pair after an explicit direct terminal.",
    )
    continuity_terminal.add_argument("registry", type=Path)
    continuity_terminal.add_argument("claim_id")
    continuity_terminal.add_argument(
        "--terminal-state",
        choices=("SUCCESS", "FAILED", "ABORTED"),
        required=True,
    )
    continuity_terminal.add_argument("--operator-agent-id", required=True)
    continuity_terminal.add_argument("--builder-agent-id", required=True)
    continuity_terminal.add_argument("--nonce", required=True)
    continuity_terminal.add_argument("--execution-state", type=Path)
    continuity_terminal.add_argument(
        "--terminal-acknowledged-directly",
        action="store_true",
        required=True,
    )

    candidate_finalize = sub.add_parser(
        "agent-candidate-finalize",
        help="Evaluate a Terra candidate and publish its final Replica result.",
    )
    candidate_finalize.add_argument("registry", type=Path)
    candidate_finalize.add_argument("claim_id")
    candidate_finalize.add_argument("candidate", type=Path)

    continuity_premature = sub.add_parser(
        "agent-continuity-premature",
        help="Abort when a bound Agent returns final before claim terminal.",
    )
    continuity_premature.add_argument("registry", type=Path)
    continuity_premature.add_argument("claim_id")
    continuity_premature.add_argument("--completed-agent-id", required=True)
    continuity_premature.add_argument("--reason", required=True)

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
    evaluate.add_argument(
        "--replica-command",
        required=True,
        type=_command_arguments,
        help="Replica command as a JSON argument array.",
    )
    evaluate.add_argument(
        "--judge-command",
        required=True,
        type=_command_arguments,
        help="Judge command as a JSON argument array.",
    )
    evaluate.add_argument("--timeout", type=int, default=120)

    report = sub.add_parser("report", help="Regenerate report.md from results.jsonl.")
    report.add_argument("path", type=Path)

    run_replica = sub.add_parser(
        "run-replica",
        help="Run a built Replica with a JSON object read from stdin.",
    )
    run_replica.add_argument("path", type=Path)
    run_replica.add_argument(
        "--use-model-adapter",
        action="store_true",
        help="Allow the optional external grounded-model adapter.",
    )

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
    experience.add_argument(
        "--use-model-adapter",
        action="store_true",
        help="Allow the optional external grounded-model adapter.",
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
        elif args.command == "agent-harness-init":
            result = prepare_agent_harness_from_path(
                args.source,
                args.run_dir,
                replica_agent_id=args.replica_agent_id,
                parent_agent_id=args.parent_agent_id,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "agent-harness-start":
            result = start_agent_claim(args.registry, args.claim_id)
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "agent-harness-spawned":
            result = record_agent_spawn(
                args.registry,
                args.claim_id,
                role=args.role,
                agent_id=args.agent_id,
                parent_agent_id=args.parent_agent_id,
                requested_model=args.requested_model,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "agent-harness-failed":
            result = record_agent_spawn_failure(
                args.registry,
                args.claim_id,
                role=args.role,
                reason=args.reason,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "agent-harness-released":
            result = record_released_agent(
                args.registry,
                args.claim_id,
                agent_id=args.agent_id,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "agent-harness-message":
            result = record_direct_agent_message(
                args.registry,
                args.claim_id,
                direction=args.direction,
                sender_agent_id=args.sender_agent_id,
                recipient_agent_id=args.recipient_agent_id,
                nonce=args.nonce,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "agent-harness-finish":
            result = finish_agent_harness(args.registry)
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "agent-protocol-validate":
            result = validate_agent_protocol_message_from_path(
                args.message,
                claim_id=args.claim_id,
                operator_agent_id=args.operator_agent_id,
                builder_agent_id=args.builder_agent_id,
                pair_nonce=args.pair_nonce,
                expected_correction_number=args.expected_correction_number,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "agent-execution-start":
            result = create_agent_execution_state_file(
                args.state,
                args.claim,
                claim_id=args.claim_id,
                operator_agent_id=args.operator_agent_id,
                builder_agent_id=args.builder_agent_id,
                pair_nonce=args.pair_nonce,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "agent-execution-advance":
            result = advance_agent_execution_from_paths(
                args.state,
                args.instruction,
                args.feedback,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "agent-continuity-start":
            result = start_agent_continuity(
                args.registry,
                args.claim_id,
                operator_agent_id=args.operator_agent_id,
                builder_agent_id=args.builder_agent_id,
                nonce=args.nonce,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "agent-continuity-round":
            result = record_agent_continuity_round(
                args.registry,
                args.claim_id,
                round_number=args.round_number,
                operator_agent_id=args.operator_agent_id,
                builder_agent_id=args.builder_agent_id,
                nonce=args.nonce,
                operator_to_builder_direct=args.operator_to_builder_direct,
                builder_to_operator_direct=args.builder_to_operator_direct,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "agent-continuity-terminal":
            result = finish_agent_continuity(
                args.registry,
                args.claim_id,
                terminal_state=args.terminal_state,
                operator_agent_id=args.operator_agent_id,
                builder_agent_id=args.builder_agent_id,
                nonce=args.nonce,
                execution_state_path=args.execution_state,
                terminal_acknowledged_directly=(
                    args.terminal_acknowledged_directly
                ),
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "agent-candidate-finalize":
            result = finalize_agent_candidate(
                args.registry,
                args.claim_id,
                args.candidate,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "agent-continuity-premature":
            result = record_agent_premature_completion(
                args.registry,
                args.claim_id,
                completed_agent_id=args.completed_agent_id,
                reason=args.reason,
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
            output = run_built_replica(
                args.path,
                replica_input,
                allow_model_adapter=args.use_model_adapter,
            )
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
                        use_model_adapter=args.use_model_adapter,
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
                        use_model_adapter=args.use_model_adapter,
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
                    print(
                        experience_once(
                            args.path,
                            profile,
                            question,
                            use_model_adapter=args.use_model_adapter,
                        )
                    )
        else:
            write_report(args.path)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0
