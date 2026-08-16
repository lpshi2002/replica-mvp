from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .builder import (
    _evaluate_codex_operator,
    _resolve_second_pass_for_build,
)
from .completion import assess_replica_completion
from .generated_component import (
    MAX_GENERATION_ATTEMPTS,
    make_generation_request,
    prepare_generated_component,
)


TASK_SCHEMA = "replica-codex-operator-task/v1"
ATTEMPTS_SCHEMA = "replica-codex-operator-attempts/v1"
RESULT_SCHEMA = "replica-codex-operator-result/v1"
PUBLIC_RESULT_SCHEMA = "replica-public-result/v1"
REQUEST_NAME = "operator-request.json"
OPERATOR_NAME = "operator.json"
ATTEMPTS_NAME = "operator-attempts.json"
TASK_NAME = "task.json"
PUBLIC_ARTIFACTS = (
    "operation-selection.json",
    "replica-spec.json",
    "execution-plan.json",
    "buildability.json",
    "replica.json",
    "generated-component.json",
    "generated-component.py",
    "generation-attempts.json",
    "evaluation-summary.json",
    "experience.json",
    "implementation",
)


def _reject_nonstandard_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_nonstandard_constant,
        )
    except FileNotFoundError:
        raise ValueError(f"missing file: {path}") from None
    except ValueError as error:
        raise ValueError(f"invalid JSON in {path}: {error}") from None


def _public_completion_contract(contract: dict[str, Any]) -> dict[str, Any]:
    """Remove frozen-suite identifiers from the published contract metadata."""

    return {
        "dependency_level": contract["dependency_level"],
        "dependencies": list(contract["dependencies"]),
        "public_sources": [dict(source) for source in contract["public_sources"]],
        "input_assets": [
            {
                field: value
                for field, value in asset.items()
                if field != "case_ids"
            }
            for asset in contract["input_assets"]
        ],
        "implementation_scenario": contract["implementation_scenario"],
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _task_paths(task_dir: Path) -> dict[str, Path]:
    return {
        "task": task_dir / TASK_NAME,
        "request": task_dir / REQUEST_NAME,
        "operator": task_dir / OPERATOR_NAME,
        "attempts": task_dir / ATTEMPTS_NAME,
    }


def _validate_task_dir(task_dir: Path, workspace: Path) -> Path:
    resolved = task_dir.resolve()
    task_root = (workspace / "operator-tasks").resolve()
    if not resolved.is_relative_to(task_root):
        raise ValueError("Codex operator task must be inside the workspace")
    return resolved


def _validate_separate_roots(
    workspace: Path,
    evaluator_vault: Path,
) -> tuple[Path, Path]:
    public_root = workspace.resolve()
    private_root = evaluator_vault.resolve()
    if (
        public_root == private_root
        or public_root.is_relative_to(private_root)
        or private_root.is_relative_to(public_root)
    ):
        raise ValueError(
            "workspace and evaluator vault must be physically separate roots"
        )
    return public_root, private_root


def _validate_source_outside_workspace(source: Path, workspace: Path) -> None:
    source_path = source.absolute()
    public_root = workspace.absolute()
    resolved_source = source.resolve()
    resolved_public_root = workspace.resolve()
    if (
        source_path == public_root
        or source_path.is_relative_to(public_root)
        or resolved_source == resolved_public_root
        or resolved_source.is_relative_to(resolved_public_root)
    ):
        raise ValueError(
            "Second-pass source must be outside the public workspace"
        )


def _is_valid_attempt(value: Any, number: int) -> bool:
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "attempt",
            "language",
            "component_sha256",
            "status",
            "passed",
            "total",
        }
        or value.get("attempt") != number
        or not isinstance(value.get("language"), str)
        or not value["language"]
        or value.get("status")
        not in {
            "VALIDATION_FAILED",
            "RUNTIME_FAILED",
            "EVALUATION_FAILED",
            "PASSED",
        }
    ):
        return False
    status = value["status"]
    digest = value["component_sha256"]
    if status == "VALIDATION_FAILED":
        return (
            value["language"] == "unvalidated"
            and digest is None
            and value["passed"] is None
            and value["total"] is None
        )
    if not isinstance(digest, str) or len(digest) != 64:
        return False
    if status == "RUNTIME_FAILED":
        return value["passed"] is None and value["total"] is None
    passed = value["passed"]
    total = value["total"]
    return (
        type(passed) is int
        and type(total) is int
        and total > 0
        and (
            status == "EVALUATION_FAILED"
            and 0 <= passed < total
            or status == "PASSED"
            and passed == total
        )
    )


def _load_task(
    task_dir: Path,
    workspace: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    task_dir = _validate_task_dir(task_dir, workspace)
    paths = _task_paths(task_dir)
    task = _read_json(paths["task"])
    if (
        not isinstance(task, dict)
        or set(task)
        != {
            "schema_version",
            "status",
            "source_intake_sha256",
            "replica_id",
            "max_attempts",
        }
        or task.get("schema_version") != TASK_SCHEMA
        or task.get("status")
        not in {"AWAITING_CODEX_OPERATOR", "COMPLETED", "FAILED"}
        or not isinstance(task.get("source_intake_sha256"), str)
        or len(task["source_intake_sha256"]) != 64
        or not isinstance(task.get("replica_id"), str)
        or task.get("max_attempts") != MAX_GENERATION_ATTEMPTS
    ):
        raise ValueError("invalid Codex operator task")
    attempts_document = _read_json(paths["attempts"])
    if (
        not isinstance(attempts_document, dict)
        or set(attempts_document) != {"schema_version", "attempts"}
        or attempts_document.get("schema_version") != ATTEMPTS_SCHEMA
        or not isinstance(attempts_document.get("attempts"), list)
        or len(attempts_document["attempts"]) > MAX_GENERATION_ATTEMPTS
        or not all(
            _is_valid_attempt(attempt, number)
            for number, attempt in enumerate(
                attempts_document["attempts"],
                start=1,
            )
        )
    ):
        raise ValueError("invalid Codex operator attempts")
    attempts = attempts_document["attempts"]
    has_passed = bool(attempts) and attempts[-1]["status"] == "PASSED"
    if (
        task["status"] == "AWAITING_CODEX_OPERATOR"
        and (len(attempts) >= MAX_GENERATION_ATTEMPTS or has_passed)
        or task["status"] == "COMPLETED"
        and not has_passed
        or task["status"] == "FAILED"
        and (len(attempts) != MAX_GENERATION_ATTEMPTS or has_passed)
    ):
        raise ValueError("Codex operator task status does not match its attempts")
    return task, attempts


def _attempt_context(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    previous = None
    if attempts:
        last = attempts[-1]
        previous = {
            "language": last["language"],
            "status": last["status"],
            "passed": last["passed"],
            "total": last["total"],
        }
    return {
        "attempt": len(attempts) + 1,
        "max_attempts": MAX_GENERATION_ATTEMPTS,
        "previous_attempt": previous,
    }


def _resolve_task_contract(
    task: dict[str, Any],
    attempts: list[dict[str, Any]],
    task_dir: Path,
    evaluator_vault: Path,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    source = (
        evaluator_vault
        / "intakes"
        / task["source_intake_sha256"]
        / "source.json"
    )
    (
        _,
        intake_sha256,
        second_pass,
        _,
    ) = _resolve_second_pass_for_build(
        source,
        evaluator_vault,
    )
    if (
        intake_sha256 != task["source_intake_sha256"]
        or second_pass["replica_id"] != task["replica_id"]
    ):
        raise ValueError("Codex operator task does not match its intake")
    context = _attempt_context(attempts)
    expected_request = make_generation_request(
        second_pass,
        attempt_context=context,
    )
    request = _read_json(_task_paths(task_dir)["request"])
    if request != expected_request:
        raise ValueError("Codex operator request does not match its task")
    return source, second_pass, context


def _task_result(
    *,
    status: str,
    attempt: int,
    task_dir: Path,
    retryable: bool,
    evaluation: dict[str, Any] | None = None,
    run_dir: str | None = None,
    replica_path: str | None = None,
    report_path: str | None = None,
) -> dict[str, Any]:
    result = {
        "schema_version": RESULT_SCHEMA,
        "status": status,
        "attempt": attempt,
        "max_attempts": MAX_GENERATION_ATTEMPTS,
        "retryable": retryable,
        "task_dir": str(task_dir.resolve()),
        "request_path": str((task_dir / REQUEST_NAME).resolve()),
        "operator_path": str((task_dir / OPERATOR_NAME).resolve()),
    }
    if evaluation is not None:
        result["evaluation"] = {
            "status": evaluation["status"],
            "passed": evaluation["passed"],
            "total": evaluation["total"],
        }
    if run_dir is not None:
        result["run_dir"] = run_dir
    if replica_path is not None:
        result["replica_path"] = replica_path
    if report_path is not None:
        result["report_path"] = report_path
    return result


def _record_failed_attempt(
    *,
    task: dict[str, Any],
    attempts: list[dict[str, Any]],
    task_dir: Path,
    second_pass: dict[str, Any],
    status: str,
    language: str,
    component_sha256: str | None,
    passed: int | None,
    total: int | None,
    run_dir: str | None = None,
    replica_path: str | None = None,
) -> dict[str, Any]:
    attempt_number = len(attempts) + 1
    attempts.append(
        {
            "attempt": attempt_number,
            "language": language,
            "component_sha256": component_sha256,
            "status": status,
            "passed": passed,
            "total": total,
        }
    )
    paths = _task_paths(task_dir)
    _write_json(
        paths["attempts"],
        {
            "schema_version": ATTEMPTS_SCHEMA,
            "attempts": attempts,
        },
    )
    retryable = attempt_number < MAX_GENERATION_ATTEMPTS
    task["status"] = "AWAITING_CODEX_OPERATOR" if retryable else "FAILED"
    _write_json(paths["task"], task)
    if retryable:
        _write_json(
            paths["request"],
            make_generation_request(
                second_pass,
                attempt_context=_attempt_context(attempts),
            ),
        )
    return _task_result(
        status=status,
        attempt=attempt_number,
        task_dir=task_dir,
        retryable=retryable,
        evaluation=(
            {"status": "FAILED", "passed": passed, "total": total}
            if passed is not None and total is not None
            else None
        ),
        run_dir=run_dir,
        replica_path=replica_path,
    )


def _publish_replica(
    *,
    private_run_dir: Path,
    workspace: Path,
    second_pass: dict[str, Any],
    evaluation: dict[str, Any],
    intake_sha256: str,
    include_report: bool,
) -> tuple[Path, Path, Path | None]:
    public_run_dir = (
        workspace / "runs" / second_pass["replica_id"] / intake_sha256
    )
    if public_run_dir.exists():
        raise ValueError(f"published Replica already exists: {public_run_dir}")
    public_run_dir.mkdir(parents=True)
    try:
        for name in PUBLIC_ARTIFACTS:
            source = private_run_dir / name
            if source.is_file():
                shutil.copy2(source, public_run_dir / name)
            elif source.is_dir():
                shutil.copytree(source, public_run_dir / name)
        required = {
            "replica.json",
            "generated-component.json",
            "evaluation-summary.json",
        }
        if not required.issubset(
            path.name for path in public_run_dir.iterdir()
        ):
            raise ValueError("private evaluation did not produce a publishable Replica")
        completion = assess_replica_completion(
            private_run_dir,
            second_pass,
            evaluation,
            report_available=include_report,
        )
        _write_json(
            public_run_dir / "completion-assessment.json",
            completion,
        )
        public_result = {
            "schema_version": PUBLIC_RESULT_SCHEMA,
            "status": "BUILT_AND_PASSED",
            "reproduction_status": completion["status"],
            "source_intake_sha256": intake_sha256,
            "replica_id": second_pass["replica_id"],
            "company": second_pass["company"],
            "capability": second_pass["capability"],
            "evaluation": {
                "status": evaluation["status"],
                "passed": evaluation["passed"],
                "total": evaluation["total"],
                "judge_identity": evaluation["judge_identity"],
                "judge_mode": evaluation["judge_mode"],
            },
            "supported_scope": second_pass["supported_scope"],
            "unsupported_scope": second_pass["unsupported_scope"],
            "limitations": second_pass["limitations"],
            "artifacts": sorted(
                path.name for path in public_run_dir.iterdir()
            ),
        }
        completion_contract = second_pass.get("completion_contract")
        if isinstance(completion_contract, dict):
            public_result["completion_contract"] = (
                _public_completion_contract(completion_contract)
            )
        _write_json(public_run_dir / "replica-result.json", public_result)
        report_path = None
        if include_report:
            report_json = dict(public_result)
            report_json["schema_version"] = "replica-public-report/v1"
            _write_json(public_run_dir / "report.json", report_json)
            report_path = public_run_dir / "report.md"
            dependencies = (
                completion_contract.get("dependencies", [])
                if isinstance(completion_contract, dict)
                else []
            )
            public_sources = (
                completion_contract.get("public_sources", [])
                if isinstance(completion_contract, dict)
                else []
            )
            input_assets = (
                completion_contract.get("input_assets", [])
                if isinstance(completion_contract, dict)
                else []
            )
            dependency_level = (
                completion_contract.get("dependency_level", "미기록")
                if isinstance(completion_contract, dict)
                else "미기록"
            )
            implementation_scenario = (
                completion_contract.get("implementation_scenario", "미기록")
                if isinstance(completion_contract, dict)
                else "미기록"
            )
            report_path.write_text(
                "\n".join(
                    (
                        f"# {second_pass['company']} Replica 결과",
                        "",
                        f"- 기능: {second_pass['capability']}",
                        "- 최종 상태: BUILT_AND_PASSED",
                        f"- 재현 판정: {completion['status']}",
                        (
                            "- 비공개 고정 테스트: "
                            f"{evaluation['passed']}/{evaluation['total']} 통과"
                        ),
                        f"- 의존성 수준: {dependency_level}",
                        f"- 최초 구현 scenario: {implementation_scenario}",
                        "",
                        "## 완료 기준 판정",
                        *(
                            f"- {check['id']}: "
                            f"{'PASS' if check['pass'] else 'FAIL'}"
                            for check in completion["checks"]
                        ),
                        "",
                        "## 실제 사용 의존성",
                        *(f"- {item}" for item in dependencies),
                        *(() if dependencies else ("- 미기록",)),
                        "",
                        "## 공개 근거",
                        *(
                            f"- {item['url']}: {item['finding']}"
                            for item in public_sources
                        ),
                        *(() if public_sources else ("- 미기록",)),
                        "",
                        "## 실제 입력 자산",
                        *(
                            f"- {item['id']} — {item['kind']}: "
                            f"{item['visibility']}:{item['location']}"
                            for item in input_assets
                        ),
                        *(() if input_assets else ("- 미기록",)),
                        "",
                        "## 지원 범위",
                        *(
                            f"- {item}"
                            for item in second_pass["supported_scope"]
                        ),
                        "",
                        "## 지원하지 않는 범위",
                        *(
                            f"- {item}"
                            for item in second_pass["unsupported_scope"]
                        ),
                        "",
                        "## 한계",
                        *(f"- {item}" for item in second_pass["limitations"]),
                        "",
                        (
                            "고정 테스트 원문과 사례별 출력·채점 결과는 "
                            "evaluator vault에만 보관됩니다."
                        ),
                        "",
                    )
                ),
                encoding="utf-8",
            )
        return (
            public_run_dir,
            public_run_dir / "replica.json",
            report_path,
        )
    except Exception:
        shutil.rmtree(public_run_dir)
        raise


def prepare_codex_operator(
    source: Path,
    workspace: Path,
    evaluator_vault: Path,
) -> dict[str, Any]:
    _validate_separate_roots(workspace, evaluator_vault)
    _validate_source_outside_workspace(source, workspace)
    (
        _,
        intake_sha256,
        second_pass,
        _,
    ) = _resolve_second_pass_for_build(
        source,
        evaluator_vault,
    )
    task_dir = (
        workspace
        / "operator-tasks"
        / second_pass["replica_id"]
        / intake_sha256
    )
    paths = _task_paths(task_dir)
    if task_dir.exists():
        task, attempts = _load_task(task_dir, workspace)
        if task["status"] != "AWAITING_CODEX_OPERATOR":
            raise ValueError(
                f"Codex operator task is already {task['status'].lower()}"
            )
        _resolve_task_contract(
            task,
            attempts,
            task_dir,
            evaluator_vault,
        )
    else:
        task_dir.mkdir(parents=True)
        task = {
            "schema_version": TASK_SCHEMA,
            "status": "AWAITING_CODEX_OPERATOR",
            "source_intake_sha256": intake_sha256,
            "replica_id": second_pass["replica_id"],
            "max_attempts": MAX_GENERATION_ATTEMPTS,
        }
        attempts = []
        _write_json(paths["task"], task)
        _write_json(
            paths["attempts"],
            {
                "schema_version": ATTEMPTS_SCHEMA,
                "attempts": attempts,
            },
        )
        _write_json(
            paths["request"],
            make_generation_request(second_pass),
        )
    return {
        "schema_version": RESULT_SCHEMA,
        "status": "AWAITING_CODEX_OPERATOR",
        "attempt": len(attempts) + 1,
        "max_attempts": MAX_GENERATION_ATTEMPTS,
        "task_dir": str(task_dir.resolve()),
        "request_path": str(paths["request"].resolve()),
        "operator_path": str(paths["operator"].resolve()),
    }


def finalize_codex_operator(
    task_dir: Path,
    workspace: Path,
    evaluator_vault: Path,
    *,
    include_report: bool = False,
) -> dict[str, Any]:
    _validate_separate_roots(workspace, evaluator_vault)
    task_dir = _validate_task_dir(task_dir, workspace)
    task, attempts = _load_task(task_dir, workspace)
    if task["status"] != "AWAITING_CODEX_OPERATOR":
        raise ValueError(
            f"Codex operator task is already {task['status'].lower()}"
        )
    source, second_pass, context = _resolve_task_contract(
        task,
        attempts,
        task_dir,
        evaluator_vault,
    )
    operator_path = _task_paths(task_dir)["operator"]
    try:
        generation = _read_json(operator_path)
        component_record = prepare_generated_component(
            second_pass,
            lambda _: generation,
            attempt_context=context,
        )
    except ValueError:
        return _record_failed_attempt(
            task=task,
            attempts=attempts,
            task_dir=task_dir,
            second_pass=second_pass,
            status="VALIDATION_FAILED",
            language="unvalidated",
            component_sha256=None,
            passed=None,
            total=None,
        )

    language = component_record["component"]["language"]
    component_sha256 = component_record["component_sha256"]
    private_run_dir = (
        evaluator_vault
        / "runs"
        / task["replica_id"]
        / task["source_intake_sha256"]
    )
    if private_run_dir.exists():
        shutil.rmtree(private_run_dir)
    try:
        result = _evaluate_codex_operator(
            source,
            evaluator_vault,
            include_report=include_report,
            component_generator=lambda _: generation,
            generation_attempt_limit=1,
            prior_generation_attempts=attempts,
            initial_attempt_context=context,
        )
    except RuntimeError:
        return _record_failed_attempt(
            task=task,
            attempts=attempts,
            task_dir=task_dir,
            second_pass=second_pass,
            status="RUNTIME_FAILED",
            language=language,
            component_sha256=component_sha256,
            passed=None,
            total=None,
        )

    current_attempt = len(attempts) + 1
    if result["status"] != "BUILT_AND_PASSED":
        retryable = current_attempt < MAX_GENERATION_ATTEMPTS
        failed = _record_failed_attempt(
            task=task,
            attempts=attempts,
            task_dir=task_dir,
            second_pass=second_pass,
            status="EVALUATION_FAILED",
            language=language,
            component_sha256=component_sha256,
            passed=result["evaluation"]["passed"],
            total=result["evaluation"]["total"],
        )
        if retryable:
            shutil.rmtree(Path(result["run_dir"]))
        return failed

    public_run_dir, replica_path, report_path = _publish_replica(
        private_run_dir=Path(result["run_dir"]),
        workspace=workspace,
        second_pass=second_pass,
        evaluation=result["evaluation"],
        intake_sha256=task["source_intake_sha256"],
        include_report=include_report,
    )
    _write_json(
        _task_paths(task_dir)["attempts"],
        {
            "schema_version": ATTEMPTS_SCHEMA,
            "attempts": result["generation_attempts"],
        },
    )
    task["status"] = "COMPLETED"
    _write_json(_task_paths(task_dir)["task"], task)
    return _task_result(
        status="BUILT_AND_PASSED",
        attempt=current_attempt,
        task_dir=task_dir,
        retryable=False,
        evaluation=result["evaluation"],
        run_dir=str(public_run_dir.resolve()),
        replica_path=str(replica_path.resolve()),
        report_path=(
            str(report_path.resolve()) if report_path is not None else None
        ),
    )
