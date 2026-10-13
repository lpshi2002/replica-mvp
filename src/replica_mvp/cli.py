from __future__ import annotations

import argparse
import contextlib
import json
import sys
import tempfile
from pathlib import Path

from .agent_execution import (
    advance_agent_execution_from_paths,
    check_agent_execution_budget,
    create_agent_execution_state_file,
)
from .agent_harness import (
    ASTRA_MODEL,
    TERRA_MODEL,
    _read_registry,
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
    resume_agent_continuity,
    retry_agent_preflight,
    start_agent_claim,
    start_agent_continuity,
)
from .agent_protocol import validate_agent_protocol_message_from_path
from .builder import run_built_replica
from .bundle_evaluation import evaluate_agent_bundle, prepare_bundle_evaluation, retry_agent_bundle
from .bundle_runtime import mountable, native_model_judge, run_json_command, web_app_session
from .company_app import company_app_session
from .codex_operator import finalize_codex_operator, prepare_codex_operator
from .experience import experience_input_once, experience_once, is_bundle_run
from .intake import receive_second_pass
from .project import build_project, evaluate_project, finalize_first_pass, init_project, write_report
from .second_pass import MODEL_RUNTIMES
from .single_agent import (
    SINGLE_FAILURE_CATEGORIES, bind_single_implementation, fail_single_implementation, prepare_single_harness,
    start_single_implementation,
)
from .web_demo import run_web_demo


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
    harness_init.add_argument("--replica-agent-model", default=ASTRA_MODEL)
    harness_init.add_argument("--operator-model", default=ASTRA_MODEL)
    harness_init.add_argument("--builder-model", default=TERRA_MODEL)
    harness_init.add_argument(
        "--model-runtime",
        choices=MODEL_RUNTIMES,
        default="codex",
    )

    single_init = sub.add_parser("single-harness-init", help="Prepare one implementation agent per researched claim.")
    single_init.add_argument("source", type=Path)
    single_init.add_argument("run_dir", type=Path)
    single_init.add_argument("--orchestrator-id", required=True)
    single_init.add_argument("--model", default=ASTRA_MODEL)
    single_init.add_argument("--reasoning-effort", default="low")
    single_init.add_argument("--model-runtime", choices=MODEL_RUNTIMES, default="codex")
    single_start = sub.add_parser("single-agent-start", help="Bind an actual single-agent spawn to its claim.")
    single_start.add_argument("registry", type=Path)
    single_start.add_argument("claim_id")
    single_start.add_argument("--agent-id", required=True)
    single_start.add_argument("--model", required=True)
    single_start.add_argument("--reasoning-effort", required=True)
    single_bind = sub.add_parser("single-agent-bind", help="Seal a single implementer's checked bundle for final evaluation.")
    single_bind.add_argument("registry", type=Path)
    single_bind.add_argument("claim_id")
    single_bind.add_argument("--agent-id", required=True)
    single_fail = sub.add_parser("single-agent-fail",
                                 help="End a claim whose implementer could not be created or could not submit.")
    single_fail.add_argument("registry", type=Path)
    single_fail.add_argument("claim_id")
    single_fail.add_argument("--category", choices=SINGLE_FAILURE_CATEGORIES, required=True)
    single_fail.add_argument("--reason", required=True)

    harness_start = sub.add_parser(
        "agent-harness-start",
        help="Register the next claim pair without waiting for active executions.",
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
    harness_spawned.add_argument("--requested-reasoning-effort", help="Explicit effort sent to the Agent spawn tool; omit when inherited.")

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

    preflight_retry = sub.add_parser(
        "agent-continuity-retry-preflight",
        help="Recover once from a recorded environment stop before any implementation action.",
    )
    preflight_retry.add_argument("registry", type=Path)
    preflight_retry.add_argument("claim_id")

    continuity_resume = sub.add_parser(
        "agent-continuity-resume", help="Resume one direct-delivery interruption with the original state and peers.",
    )
    continuity_resume.add_argument("registry", type=Path)
    continuity_resume.add_argument("claim_id")

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
        help=(
            "Evaluate a component candidate or bind a verified implementation bundle."
        ),
    )
    candidate_finalize.add_argument("registry", type=Path)
    candidate_finalize.add_argument("claim_id")
    candidate_finalize.add_argument("candidate", type=Path)
    candidate_finalize.add_argument("--bind-only", action="store_true", help="Leave a bundle ready for a separately scheduled final evaluator.")
    execution_check = sub.add_parser("agent-execution-check", help="Check the frozen development budget before the next action.")
    execution_check.add_argument("state", type=Path)

    bundle_prepare = sub.add_parser("agent-bundle-prepare", help="Freeze an additive second-pass evaluation supplement.")
    bundle_prepare.add_argument("registry", type=Path)
    bundle_prepare.add_argument("claim_id")
    bundle_prepare.add_argument("--supplement", type=Path)

    bundle_evaluate = sub.add_parser("agent-bundle-evaluate", help="Execute and evaluate the bound bundle outside Builder development tests.")
    bundle_evaluate.add_argument("registry", type=Path)
    bundle_evaluate.add_argument("claim_id")
    bundle_evaluate.add_argument("--judge-command", type=_command_arguments)
    bundle_evaluate.add_argument("--judge-identity")
    bundle_evaluate.add_argument("--judge-mode", choices=("independent", "same_session"), default="same_session")
    web_recover = sub.add_parser("agent-web-recover", help="Resume the same web bundle after an environment stop or evaluator fix; preserve history.")
    web_recover.add_argument("registry", type=Path)
    web_recover.add_argument("claim_id")
    web_recover.add_argument("--reason", required=True)
    web_recover.add_argument("--clear-usage-limit", action="store_true", help="After provider reset, archive the old gate and try again.")
    web_recover.add_argument("--model")
    bundle_check = sub.add_parser("agent-bundle-check", help="Check bundle packaging against a public claim without models or registry writes.")
    bundle_check.add_argument("run_dir", type=Path)
    bundle_check.add_argument("claim_id")
    bundle_check.add_argument("manifest", type=Path)
    register_dev = sub.add_parser("agent-development-register", help="Register existing development-demo receipts for cumulative costs.")
    register_dev.add_argument("registry", type=Path)
    register_dev.add_argument("claim_id")
    register_dev.add_argument("run_dir", type=Path)
    bundle_retry = sub.add_parser("agent-bundle-retry", help="Reopen the same pair after a failed final evaluation, preserving history and budgets.")
    bundle_retry.add_argument("registry", type=Path)
    bundle_retry.add_argument("claim_id")

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

    finalize = sub.add_parser(
        "finalize-pass-1",
        help="Validate pass-1 checkpoints and AI technology claims.",
    )
    finalize.add_argument("path", type=Path, help="Company root, e.g. work/acme")

    run_replica = sub.add_parser(
        "run-replica",
        help="Run a built Replica with a JSON object read from stdin.",
    )
    run_replica.add_argument("path", type=Path)
    run_replica.add_argument("--input-assets", type=Path, help="JSON map of runtime-relative asset names to local source paths.")
    run_replica.add_argument("--session", action="store_true", help="Run a JSON array of inputs in one bundle session.")
    run_replica.add_argument(
        "--state-dir",
        type=Path,
        help="Keep the bundle's runtime directory here and resume it on later calls.",
    )
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
        "--state-dir",
        type=Path,
        help=(
            "Keep an implementation bundle's runtime directory here so later calls continue "
            "its stored state. An interactive bundle session uses a temporary one by default."
        ),
    )
    experience.add_argument(
        "--use-model-adapter",
        action="store_true",
        help="Allow the optional external grounded-model adapter.",
    )

    serve_web = sub.add_parser("serve-web", help="Start a web-app Replica so a person can use it in a browser.")
    serve_web.add_argument("manifest", type=Path, help="Implementation manifest.json declaring a web_app runtime.")
    serve_web.add_argument("--state-dir", type=Path, help="Keep the app's working directory and saved data here.")
    serve_web.add_argument("--port", type=int, help="Loopback port (default: a free port).")
    serve_web.add_argument("--open", action="store_true", help="Open the app in the default browser.")

    serve_company = sub.add_parser("serve-company", help="Serve every bound web-app feature of a run as one company app.")
    serve_company.add_argument("registry", type=Path, help="agent-harness.json of the run.")
    serve_company.add_argument("--state-dir", type=Path, help="Saved app data (default: company-app-state in the run).")
    serve_company.add_argument("--port", type=int, help="Loopback port (default: a free port).")
    serve_company.add_argument("--open", action="store_true", help="Open the app in the default browser.")

    web_demo = sub.add_parser("web-demo", help="Run fixed cases through the web app with an AI browser tester.")
    web_demo.add_argument("plan", type=Path, help="replica-web-demo-plan/v1 JSON.")
    web_demo.add_argument("--output", type=Path, required=True, help="New directory for the saved demo result.")
    web_demo.add_argument("--manifest", type=Path, help="Candidate manifest, for a plan frozen before implementation.")
    web_demo.add_argument("--provider", choices=sorted(MODEL_RUNTIMES), default="claude")
    web_demo.add_argument("--model", help="Model for the tester and judge (default: the CLI default).")

    web_demo.add_argument("--case", action="append", dest="case_ids", help="Development only: run this case ID (repeatable).")
    web_demo.add_argument("--resume-from", type=Path, help="Previous demo directory; writes a new result, preserving old evidence.")
    web_demo.add_argument("--clear-usage-limit", action="store_true")
    for command in (web_demo, bundle_evaluate, web_recover):
        for role in ("tester", "judge", "instance", "code-review"):
            command.add_argument(f"--{role}-model", help=f"Override the {role} model; otherwise keep the default.")
    bundle_evaluate.add_argument("--clear-usage-limit", action="store_true")
    return parser


def _serve_web(manifest: Path, state_dir: Path | None, port: int | None, open_browser: bool) -> None:
    import signal
    import time
    import webbrowser

    def interrupt(signum, frame):
        raise KeyboardInterrupt

    # `kill` (SIGTERM) stops the app the same way Ctrl-C does instead of leaving it running.
    signal.signal(signal.SIGTERM, interrupt)
    with contextlib.ExitStack() as stack:
        if state_dir is None:
            state_dir = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="replica-web-"))) / "state"
            print(f"상태 디렉터리: {state_dir} (종료 시 삭제, 유지하려면 --state-dir)")
        manifest_value = json.loads(manifest.read_text(encoding="utf-8"))
        if mountable(manifest_value.get("runtime") or {}):
            # A company-app feature runs behind the same shell a person and the AI tester use.
            feature = {"id": manifest_value["claim_id"], "title": manifest_value["claim_id"],
                       "manifest": manifest.resolve(), "workspace": state_dir}
            shell, roots = stack.enter_context(company_app_session("Company app", [feature], 60, port=port or 0))
            base_url, root = shell, roots[feature["id"]]
        else:
            base_url, root = stack.enter_context(web_app_session(manifest.resolve(), 60, workspace=state_dir, port=port))
        print(f"웹 앱 실행 중: {base_url}/  (작업 디렉터리 {root}, 종료는 Ctrl-C)", flush=True)
        if open_browser:
            webbrowser.open(base_url + "/")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("종료합니다.")


def _serve_company(registry_path: Path, state_dir: Path | None, port: int | None, open_browser: bool) -> None:
    """Serve every bound, mountable feature of a company run as one app; others are listed, not served."""
    import signal
    import time
    import webbrowser

    def interrupt(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    registry = _read_registry(registry_path)
    root = registry_path.parent.resolve()
    company = (registry.get("company") or {}).get("name") or "Company app"
    state = (state_dir or root / "company-app-state").resolve()
    features, skipped = [], []
    for claim in registry["claims"]:
        bound = claim.get("implementation_result")
        if not bound or not claim.get("web_demo"):
            skipped.append((claim["claim_id"], "no bound web-app implementation"))
            continue
        manifest = root / bound["candidate_path"]
        if not mountable(json.loads(manifest.read_text(encoding="utf-8")).get("runtime") or {}):
            skipped.append((claim["claim_id"], "bundle declares no base_path_argument (built before the company app)"))
            continue
        plan = json.loads((root / claim["web_demo"]["plan_path"]).read_text(encoding="utf-8"))
        features.append({"id": claim["claim_id"], "title": plan["title"], "manifest": manifest,
                         "workspace": state / claim["claim_id"]})
    for claim_id, reason in skipped:
        print(f"제외: {claim_id} ({reason})", flush=True)
    if not features:
        raise ValueError("no bound feature of this run can be mounted in the company app")
    with company_app_session(company, features, 120, port=port or 0) as (shell, roots):
        print(f"기업 앱 실행 중: {shell}/  (기능 {len(features)}개, 상태 {state}, 종료는 Ctrl-C)", flush=True)
        if open_browser:
            webbrowser.open(shell + "/")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("종료합니다.")


def _evaluate_bundle_cli(registry_path: Path, claim_id: str, *, judge_command: list[str] | None = None,
                         judge_identity: str | None = None, judge_mode: str = "same_session",
                         phase_models: dict | None = None, clear_limit: bool = False) -> dict:
    if judge_command is None:
        registry = _read_registry(registry_path)
        provider = registry.get("model_runtime", {}).get("provider")
        if provider not in MODEL_RUNTIMES:
            raise ValueError("final evaluation requires the harness-selected model runtime")
        if judge_mode != "same_session":
            raise ValueError("the harness runtime alone does not establish an independent judge")
        return evaluate_agent_bundle(
            registry_path, claim_id, semantic_judge=lambda request: native_model_judge(provider, request),
            judge_identity=judge_identity or f"{provider}-cli-final-evaluator", judge_mode="same_session",
            phase_models=phase_models, clear_limit=clear_limit,
        )
    if not judge_identity:
        raise ValueError("a custom evaluator requires --judge-identity")
    import tempfile
    with tempfile.TemporaryDirectory(prefix="replica-final-judge-") as directory:
        return evaluate_agent_bundle(
            registry_path, claim_id,
            semantic_judge=lambda request: run_json_command(judge_command, request, Path(directory), request["timeout_seconds"]),
            judge_identity=judge_identity, judge_mode=judge_mode,
        )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    phase_models = {role: getattr(args, f"{role}_model", None) for role in ("tester", "judge", "instance", "code_review")}
    phase_models = {role: model for role, model in phase_models.items() if model}
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
                replica_agent_model=args.replica_agent_model,
                operator_model=args.operator_model,
                builder_model=args.builder_model,
                model_runtime=args.model_runtime,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "single-harness-init":
            result = prepare_single_harness(args.source, args.run_dir, orchestrator_id=args.orchestrator_id,
                                            model=args.model, reasoning_effort=args.reasoning_effort,
                                            model_runtime=args.model_runtime)
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "single-agent-start":
            result = start_single_implementation(args.registry, args.claim_id, agent_id=args.agent_id,
                                                 model=args.model, reasoning_effort=args.reasoning_effort)
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "single-agent-bind":
            result = bind_single_implementation(args.registry, args.claim_id, agent_id=args.agent_id)
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "single-agent-fail":
            result = fail_single_implementation(args.registry, args.claim_id, category=args.category,
                                                reason=args.reason)
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
                requested_reasoning_effort=args.requested_reasoning_effort,
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
        elif args.command == "agent-execution-check":
            print(json.dumps(check_agent_execution_budget(args.state), ensure_ascii=False, allow_nan=False))
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
        elif args.command == "agent-continuity-resume":
            result = resume_agent_continuity(args.registry, args.claim_id)
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "agent-continuity-retry-preflight":
            result = retry_agent_preflight(args.registry, args.claim_id)
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
            claim = next(c for c in result["claims"] if c["claim_id"] == args.claim_id)
            if claim["status"] == "IMPLEMENTATION_READY" and not args.bind_only:
                result = _evaluate_bundle_cli(args.registry, args.claim_id)
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "agent-web-recover":
            result = evaluate_agent_bundle(args.registry, args.claim_id, recovery_reason=args.reason,
                                           clear_limit=args.clear_usage_limit, model=args.model, phase_models=phase_models)
            print(json.dumps(next(c["final_result"] for c in result["claims"] if c["claim_id"] == args.claim_id), ensure_ascii=False, indent=2))
        elif args.command == "agent-bundle-check":
            from .agent_harness import REGISTRY_NAME, _claim_record, _validate_implementation_bundle, require_company_mount
            payload = json.loads((args.run_dir / "claims" / args.claim_id / "claim.json").read_text())
            manifest, artifacts = _validate_implementation_bundle(args.run_dir.resolve(), args.claim_id, args.manifest.resolve(), payload)
            registry_path = args.run_dir / REGISTRY_NAME
            if registry_path.exists():
                require_company_mount(_claim_record(_read_registry(registry_path), args.claim_id), manifest)
            print(json.dumps({"status": "passed", "files": len(artifacts), "scenario_id": manifest["scenario_id"]}))
        elif args.command == "agent-development-register":
            from .web_evaluation import register_development_run
            print(json.dumps(register_development_run(args.registry, args.claim_id, args.run_dir), ensure_ascii=False))
        elif args.command == "agent-bundle-prepare":
            result = prepare_bundle_evaluation(args.registry, args.claim_id, args.supplement)
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "agent-bundle-evaluate":
            result = _evaluate_bundle_cli(args.registry, args.claim_id, judge_command=args.judge_command,
                                         judge_identity=args.judge_identity, judge_mode=args.judge_mode,
                                         phase_models=phase_models, clear_limit=args.clear_usage_limit)
            # Per-case outputs and diagnostic reasons stay in the evaluator vault.
            print(json.dumps(next(c["final_result"] for c in result["claims"] if c["claim_id"] == args.claim_id),
                             ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "agent-bundle-retry":
            result = retry_agent_bundle(args.registry, args.claim_id)
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
                input_assets=json.loads(args.input_assets.read_text()) if args.input_assets else None,
                session=args.session,
                state_dir=args.state_dir,
            )
            print(json.dumps(output, ensure_ascii=False, allow_nan=False))
        elif args.command == "experience":
            profile = args.profile or args.path / "experience.json"
            state_options = {} if args.state_dir is None else {"state_dir": args.state_dir}
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
                        **state_options,
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
                        **state_options,
                    )
                )
            else:
                with contextlib.ExitStack() as stack:
                    # Turns of one interactive bundle session continue the same runtime state.
                    if not state_options and is_bundle_run(args.path):
                        state_options["state_dir"] = Path(
                            stack.enter_context(tempfile.TemporaryDirectory(prefix="replica-experience-"))
                        ) / "state"
                        print(f"세션 상태: {state_options['state_dir']} (종료 시 삭제, 유지하려면 --state-dir)")
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
                                **state_options,
                            )
                        )
        elif args.command == "serve-web":
            _serve_web(args.manifest, args.state_dir, args.port, args.open)
        elif args.command == "serve-company":
            _serve_company(args.registry, args.state_dir, args.port, args.open)
        elif args.command == "web-demo":
            result = run_web_demo(args.plan, args.output, manifest_path=args.manifest,
                                  provider=args.provider, model=args.model, case_ids=args.case_ids, phase_models=phase_models,
                                  resume_from=args.resume_from, clear_limit=args.clear_usage_limit)
            print(json.dumps({"output": str(args.output), "outcome": result["outcome"],
                              "costs": result["costs"]["phases"],
                              "cases": {c["case_id"]: c["execution_status"] for c in result["cases"]}},
                             ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "finalize-pass-1":
            finalize_first_pass(args.path)
        else:
            write_report(args.path)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0
