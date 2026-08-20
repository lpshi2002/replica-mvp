from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, NoReturn

from .completion import (
    _valid_completion_contract,
    append_completion_report_section,
    write_completion_report_artifact,
)
from .evaluation import evaluate_frozen_suite, freeze_test_suite
from .experience import validate_experience_profile
from .generated_component import (
    ComponentGenerator,
    MAX_GENERATION_ATTEMPTS,
    execute_generated_component,
    prepare_generated_component,
    validate_generated_component_record,
)
from .grounded_conversation import (
    preflight_grounded_response,
    strengthen_grounded_response,
)
from .intake import receive_second_pass
from .operation_selection import (
    GENERATED_COMPONENT_OPERATION,
    select_codex_operator_implementation,
)
from .plan_safety import assess_plan_safety
from .python_component import PYTHON_COMPONENT_LANGUAGE
from .reporting import write_final_report


SECOND_PASS_FIELDS = {
    "schema_version",
    "replica_id",
    "company",
    "capability",
    "canonical_claim",
    "evidence_level",
    "readiness",
    "handoff",
    "input_contract",
    "output_contract",
    "acceptance_criteria",
    "implementation",
    "supported_scope",
    "unsupported_scope",
    "limitations",
    "tests",
}
SECOND_PASS_FIELDS_WITHOUT_IMPLEMENTATION = SECOND_PASS_FIELDS - {"implementation"}
SECOND_PASS_FIELDS_WITH_EXPERIENCE = SECOND_PASS_FIELDS | {"experience"}
SECOND_PASS_FIELDS_WITH_EXPERIENCE_WITHOUT_IMPLEMENTATION = (
    SECOND_PASS_FIELDS_WITH_EXPERIENCE - {"implementation"}
)
OPERATION_INPUT_FIELDS = {
    GENERATED_COMPONENT_OPERATION: {
        "component_sha256",
        "request_sha256",
    },
}


def _reject_nonstandard_constant(value: str) -> NoReturn:
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


def _load_preserved_intake(
    workspace: Path,
    digest: str,
) -> tuple[bytes, Any]:
    intake_source = workspace / "intakes" / digest / "source.json"
    try:
        source_bytes = intake_source.read_bytes()
    except FileNotFoundError:
        raise ValueError(f"missing preserved intake source: {intake_source}") from None
    if hashlib.sha256(source_bytes).hexdigest() != digest:
        raise ValueError("preserved intake source does not match its digest")
    try:
        value = json.loads(
            source_bytes.decode("utf-8-sig"),
            parse_constant=_reject_nonstandard_constant,
        )
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError(
            f"invalid JSON in preserved intake source: {error}"
        ) from None
    return source_bytes, value


def _write_json(path: Path, value: Any) -> None:
    content = (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    )
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(content)
    except FileExistsError:
        raise ValueError(f"build artifact already exists: {path}") from None


def _is_nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_text_list(value: Any, *, allow_empty: bool = True) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(_is_nonempty_text(item) for item in value)
    )


def _has_valid_implementation(
    implementation: Any,
) -> bool:
    if not isinstance(implementation, dict):
        return False
    if set(implementation) == {"operation", "configuration"}:
        operation = implementation.get("operation")
        configuration = implementation.get("configuration")
        return (
            _is_nonempty_text(operation)
            and isinstance(configuration, dict)
        )
    return (
        set(implementation) == {"strategy", "instructions"}
        and implementation.get("strategy") == "generated_component"
        and _is_nonempty_text(implementation.get("instructions"))
    )


def _validate_second_pass(
    value: Any,
    *,
    allow_missing_implementation: bool = False,
) -> dict[str, Any]:
    base_field_sets = (
        {
            frozenset(SECOND_PASS_FIELDS),
            frozenset(SECOND_PASS_FIELDS_WITHOUT_IMPLEMENTATION),
            frozenset(SECOND_PASS_FIELDS_WITH_EXPERIENCE),
            frozenset(SECOND_PASS_FIELDS_WITH_EXPERIENCE_WITHOUT_IMPLEMENTATION),
        }
        if allow_missing_implementation
        else {
            frozenset(SECOND_PASS_FIELDS),
            frozenset(SECOND_PASS_FIELDS_WITH_EXPERIENCE),
        }
    )
    valid_field_sets = base_field_sets | {
        frozenset({*fields, "completion_contract"})
        for fields in base_field_sets
    }
    if not isinstance(value, dict) or frozenset(value) not in valid_field_sets:
        raise ValueError("invalid second-pass result contract")
    input_contract = value.get("input_contract")
    output_contract = value.get("output_contract")
    has_implementation = "implementation" in value
    implementation = value.get("implementation")
    criteria = value.get("acceptance_criteria")
    tests = value.get("tests")
    required_fields = (
        input_contract.get("required")
        if isinstance(input_contract, dict)
        else None
    )
    criterion_ids = (
        [criterion.get("id") for criterion in criteria]
        if isinstance(criteria, list)
        and all(isinstance(criterion, dict) for criterion in criteria)
        else []
    )
    test_cases = tests.get("cases") if isinstance(tests, dict) else None
    covered_ids = (
        {
            criterion_id
            for case in test_cases
            if isinstance(case, dict)
            for criterion_id in case.get("criterion_ids", [])
        }
        if isinstance(test_cases, list)
        and all(
            isinstance(case, dict)
            and _is_text_list(case.get("criterion_ids"), allow_empty=False)
            for case in test_cases
        )
        else set()
    )
    if (
        value.get("schema_version") != "replica-second-pass-result/v1"
        or not all(
            _is_nonempty_text(value.get(field))
            for field in (
                "replica_id",
                "company",
                "capability",
                "canonical_claim",
            )
        )
        or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value["replica_id"])
        or value.get("evidence_level") not in {"direct", "public", "claim_only"}
        or value.get("readiness") != "ready"
        or value.get("handoff") != "build"
        or not isinstance(input_contract, dict)
        or set(input_contract) != {"type", "required"}
        or input_contract.get("type") != "object"
        or not _is_text_list(required_fields, allow_empty=False)
        or len(set(required_fields)) != len(required_fields)
        or not isinstance(output_contract, dict)
        or set(output_contract) != {"type", "format"}
        or not _is_nonempty_text(output_contract.get("type"))
        or not _is_nonempty_text(output_contract.get("format"))
        or not isinstance(criteria, list)
        or not criteria
        or not all(
            set(criterion) == {"id", "description"}
            and _is_nonempty_text(criterion.get("id"))
            and _is_nonempty_text(criterion.get("description"))
            for criterion in criteria
        )
        or len(set(criterion_ids)) != len(criterion_ids)
        or (not has_implementation and not allow_missing_implementation)
        or (
            has_implementation
            and not _has_valid_implementation(implementation)
        )
        or not _is_text_list(value.get("supported_scope"))
        or not _is_text_list(value.get("unsupported_scope"))
        or not _is_text_list(value.get("limitations"))
        or not isinstance(tests, dict)
        or set(criterion_ids) != covered_ids
        or (
            "completion_contract" in value
            and not _valid_completion_contract(value["completion_contract"])
        )
    ):
        raise ValueError("invalid second-pass result contract")
    if "experience" in value:
        try:
            experience = validate_experience_profile(value["experience"])
        except ValueError:
            raise ValueError("invalid second-pass result contract") from None
        question_field = experience["interaction"]["question_field"]
        if (
            question_field not in required_fields
            or output_contract["type"] != "object"
            or output_contract["format"] != "grounded-conversation-response"
            or experience["comparison"]["evidence_level"]
            != value["evidence_level"]
            or not (set(required_fields) - {question_field}).issubset(
                experience["runtime_input"]
            )
        ):
            raise ValueError("invalid second-pass result contract")
        for example in experience["examples"]:
            public_input = dict(experience["runtime_input"])
            public_input[question_field] = example["question"]
            public_required_input = {
                field: public_input[field]
                for field in required_fields
                if field in public_input
            }
            if any(
                isinstance(case.get("input"), dict)
                and {
                    field: case["input"][field]
                    for field in required_fields
                    if field in case["input"]
                }
                == public_required_input
                for case in test_cases
            ):
                raise ValueError("invalid second-pass result contract")
        frozen_expected_outputs = {
            json.dumps(
                assertion["value"],
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            )
            for case in test_cases
            for assertion in case.get("deterministic_assertions", [])
            if isinstance(assertion, dict)
            and assertion.get("type") == "equals"
            and "value" in assertion
        }
        if any(
            json.dumps(
                original["output"],
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            )
            in frozen_expected_outputs
            for original in experience["comparison"]["original_outputs"]
        ):
            raise ValueError("invalid second-pass result contract")
    return value


def _make_replica_spec(
    second_pass: dict[str, Any],
    intake_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": "replica-spec/v1",
        "source_intake_sha256": intake_sha256,
        "replica_id": second_pass["replica_id"],
        "canonical_claim": second_pass["canonical_claim"],
        "input_contract": second_pass["input_contract"],
        "output_contract": second_pass["output_contract"],
        "acceptance_criteria": second_pass["acceptance_criteria"],
        "evidence_policy": {
            "level": second_pass["evidence_level"],
            "allowed_fact_sources": ["second_pass_result", "runtime_input"],
            "forbidden_assumptions": [
                "private company data",
                "undocumented original implementation details",
            ],
        },
    }


def _make_execution_plan(
    second_pass: dict[str, Any],
    generated_component_record: dict[str, Any],
) -> dict[str, Any]:
    criterion_ids = [
        criterion["id"] for criterion in second_pass["acceptance_criteria"]
    ]
    is_generated_code = (
        generated_component_record["component"]["language"]
        == PYTHON_COMPONENT_LANGUAGE
    )
    inputs = {
        "component_sha256": generated_component_record["component_sha256"],
        "request_sha256": generated_component_record["request_sha256"],
    }
    return {
        "schema_version": "replica-execution-plan/v1",
        "steps": [
            {
                "id": "produce-output",
                "strategy": (
                    "generated_code"
                    if is_generated_code
                    else "generated_component"
                ),
                "operation": GENERATED_COMPONENT_OPERATION,
                "depends_on": [],
                "access": {
                    "network": False,
                    "external_credentials": [],
                },
                "limits": {
                    "timeout_seconds": 10,
                    "max_output_bytes": 1_000_000,
                },
                "inputs": inputs,
                "outputs": ["result"],
                "criterion_ids": criterion_ids,
            }
        ],
    }


def _operation_registry(
    run_dir: Path,
    replica_spec: Mapping[str, Any],
) -> Mapping[str, Any]:
    def run_generated(
        configuration: dict[str, Any],
        runtime_input: dict[str, Any],
    ) -> Any:
        if set(configuration) != {"component_sha256", "request_sha256"}:
            raise ValueError("invalid generated component configuration")
        record = validate_generated_component_record(
            _read_json(run_dir / "generated-component.json"),
            input_contract=replica_spec["input_contract"],
            output_contract=replica_spec["output_contract"],
        )
        if record["component_sha256"] != configuration["component_sha256"]:
            raise ValueError("generated component does not match its execution plan")
        if record["request_sha256"] != configuration["request_sha256"]:
            raise ValueError(
                "generated component request does not match its execution plan"
            )
        component = record["component"]
        if component["language"] == PYTHON_COMPONENT_LANGUAGE:
            source_path = run_dir / "generated-component.py"
            if (
                not source_path.is_file()
                or source_path.read_text(encoding="utf-8")
                != component["source"]
            ):
                raise ValueError(
                    "generated Python source does not match its component record"
                )
        return execute_generated_component(component, runtime_input)

    return {
        GENERATED_COMPONENT_OPERATION: run_generated,
    }


def _validate_replica(value: Any) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "schema_version",
            "source_intake_sha256",
            "replica_id",
            "replica_spec",
            "execution_plan",
        }
        or value.get("schema_version") != "replica/v1"
        or not _is_nonempty_text(value.get("source_intake_sha256"))
        or not _is_nonempty_text(value.get("replica_id"))
        or not isinstance(value.get("replica_spec"), dict)
        or not isinstance(value.get("execution_plan"), dict)
    ):
        raise ValueError("invalid built Replica")
    return value


def _require_standard_json(value: Any) -> None:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        raise ValueError("Replica input must contain only standard JSON") from None


def run_built_replica(
    run_dir: Path,
    runtime_input: dict[str, Any],
    *,
    allow_model_adapter: bool = False,
) -> Any:
    if not isinstance(runtime_input, dict):
        raise ValueError("Replica input must be a JSON object")
    _require_standard_json(runtime_input)
    replica = _validate_replica(_read_json(run_dir / "replica.json"))
    replica_spec = replica["replica_spec"]
    if (
        replica_spec.get("output_contract", {}).get("format")
        == "grounded-conversation-response"
    ):
        input_contract = replica_spec.get("input_contract")
        required_fields = (
            input_contract.get("required")
            if isinstance(input_contract, dict)
            else None
        )
        if not isinstance(required_fields, list) or not all(
            _is_nonempty_text(field) for field in required_fields
        ):
            raise ValueError("invalid built Replica input contract")
        missing_fields = [
            field for field in required_fields if field not in runtime_input
        ]
        if missing_fields:
            raise ValueError(
                "Replica input is missing required fields: "
                + ", ".join(missing_fields)
            )
    plan = replica["execution_plan"]
    registry = _operation_registry(run_dir, replica_spec)
    safety = assess_plan_safety(
        plan,
        available_operations=set(registry),
        operation_input_fields=OPERATION_INPUT_FIELDS,
        generated_component_operations={GENERATED_COMPONENT_OPERATION},
        generated_code_operations={GENERATED_COMPONENT_OPERATION},
    )
    if safety["status"] != "SAFE_TO_EXECUTE":
        raise ValueError("built Replica execution plan is unsafe")
    steps = plan["steps"]
    if len(steps) != 1:
        raise ValueError("prototype runtime requires exactly one execution step")
    step = steps[0]
    experience_path = run_dir / "experience.json"
    experience: dict[str, Any] | None = None
    output: Any = None
    if (
        replica_spec["output_contract"].get("format")
        == "grounded-conversation-response"
    ):
        if not experience_path.is_file():
            raise ValueError("grounded Replica is missing its experience profile")
        experience = validate_experience_profile(_read_json(experience_path))
        output = preflight_grounded_response(runtime_input, experience)
    if output is None:
        operation = registry[step["operation"]]
        started = time.monotonic()
        output = operation(step["inputs"], runtime_input)
        elapsed = time.monotonic() - started
        if elapsed > step["limits"]["timeout_seconds"]:
            raise RuntimeError("Replica operation exceeded its time limit")
        if experience is not None:
            output = strengthen_grounded_response(
                runtime_input,
                output,
                experience,
                allow_model_adapter=allow_model_adapter,
            )
    output_bytes = json.dumps(
        output,
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    if len(output_bytes) > step["limits"]["max_output_bytes"]:
        raise RuntimeError("Replica operation exceeded its output limit")
    return output


def _run_replica_in_subprocess(
    run_dir: Path,
    runtime_input: Any,
    *,
    timeout_seconds: int,
    max_output_bytes: int,
) -> Any:
    environment = os.environ.copy()
    environment.pop("OPENAI_API_KEY", None)
    source_root = str(Path(__file__).parents[1])
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        source_root
        if not existing_pythonpath
        else os.pathsep.join((source_root, existing_pythonpath))
    )
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "replica_mvp",
                "run-replica",
                str(run_dir),
            ],
            input=json.dumps(runtime_input, ensure_ascii=False, allow_nan=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Replica subprocess exceeded its time limit") from None
    if completed.returncode != 0:
        raise RuntimeError(
            f"Replica subprocess failed: {completed.stderr.strip()}"
        )
    if len(completed.stdout.encode("utf-8")) > max_output_bytes:
        raise RuntimeError("Replica subprocess exceeded its output limit")
    try:
        return json.loads(
            completed.stdout,
            parse_constant=_reject_nonstandard_constant,
        )
    except ValueError as error:
        raise RuntimeError(
            f"Replica subprocess returned invalid JSON: {error}"
        ) from None


def _semantic_judge_not_configured(_: dict[str, Any]) -> dict[str, Any]:
    raise RuntimeError("semantic criteria require an explicit independent Judge")


def _require_deterministic_evaluation(second_pass: dict[str, Any]) -> None:
    if any(
        case.get("semantic_criteria")
        for case in second_pass["tests"]["cases"]
        if isinstance(case, dict)
    ):
        raise ValueError(
            "semantic criteria require an independent Judge that is not "
            "configured in the Step 9 prototype"
        )


def _prepare_frozen_tests(
    tests: dict[str, Any],
) -> tuple[bytes, dict[str, Any]]:
    with TemporaryDirectory() as temporary_directory:
        temporary_root = Path(temporary_directory)
        tests_source = temporary_root / "source-tests.json"
        tests_source.write_text(
            json.dumps(
                tests,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        validation_run = temporary_root / "run"
        frozen = freeze_test_suite(tests_source, validation_run)
        return (validation_run / "tests.json").read_bytes(), frozen


def _write_build_record(
    run_dir: Path,
    *,
    second_pass: dict[str, Any],
    intake_sha256: str,
    has_generated_component: bool,
) -> dict[str, Any]:
    artifacts = {
        "second_pass": "second-pass.json",
        "operation_selection": "operation-selection.json",
        "replica_spec": "replica-spec.json",
        "execution_plan": "execution-plan.json",
        "buildability": "buildability.json",
        "replica": "replica.json",
        "tests": "tests.json",
        "test_lock": "test-suite-lock.json",
        "outputs": "replica_outputs.jsonl",
        "results": "results.jsonl",
        "evaluation_summary": "evaluation-summary.json",
        "build_record": "build-record.json",
    }
    if has_generated_component:
        artifacts["generated_component"] = "generated-component.json"
        artifacts["implementation"] = "implementation"
    if (run_dir / "generated-component.py").is_file():
        artifacts["generated_source"] = "generated-component.py"
    if (run_dir / "generation-attempts.json").is_file():
        artifacts["generation_attempts"] = "generation-attempts.json"
    if (run_dir / "experience.json").is_file():
        artifacts["experience"] = "experience.json"
    if (run_dir / "completion-report.json").is_file():
        artifacts["completion_report"] = "completion-report.json"
    record = {
        "schema_version": "replica-build-record/v1",
        "source_intake_sha256": intake_sha256,
        "replica_id": second_pass["replica_id"],
        "company": second_pass["company"],
        "capability": second_pass["capability"],
        "evidence_level": second_pass["evidence_level"],
        "readiness": second_pass["readiness"],
        "buildability_status": "BUILDABLE",
        "build_status": "SUCCEEDED",
        "blockers": [],
        "supported_scope": second_pass["supported_scope"],
        "unsupported_scope": second_pass["unsupported_scope"],
        "limitations": second_pass["limitations"],
        "artifacts": artifacts,
    }
    _write_json(run_dir / "build-record.json", record)
    return record


def _materialize_and_evaluate_run(
    run_dir: Path,
    *,
    source_bytes: bytes,
    second_pass: dict[str, Any],
    operation_selection: dict[str, Any],
    intake_sha256: str,
    replica_spec: dict[str, Any],
    execution_plan: dict[str, Any],
    safety: dict[str, Any],
    tests_bytes: bytes,
    frozen: dict[str, Any],
    include_report: bool,
    generated_component_record: dict[str, Any] | None,
    generation_attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    (run_dir / "second-pass.json").write_bytes(source_bytes)
    _write_json(run_dir / "operation-selection.json", operation_selection)
    _write_json(run_dir / "replica-spec.json", replica_spec)
    _write_json(run_dir / "execution-plan.json", execution_plan)
    buildability = {
        "schema_version": "replica-buildability/v1",
        "status": "BUILDABLE",
        "criterion_coverage": {
            "covered": len(second_pass["acceptance_criteria"]),
            "total": len(second_pass["acceptance_criteria"]),
        },
        "blockers": [],
        "safety": safety,
    }
    _write_json(run_dir / "buildability.json", buildability)
    if generated_component_record is not None:
        _write_json(
            run_dir / "generated-component.json",
            generated_component_record,
        )
        component = generated_component_record["component"]
        implementation_dir = run_dir / "implementation"
        implementation_dir.mkdir()
        entrypoint = (
            "replica.py"
            if component["language"] == PYTHON_COMPONENT_LANGUAGE
            else "component.json"
        )
        _write_json(
            implementation_dir / "manifest.json",
            {
                "schema_version": "replica-implementation/v1",
                "entrypoint": entrypoint,
                "command": "replica-mvp run-replica RUN_DIR < INPUT.json",
            },
        )
        if component["language"] == PYTHON_COMPONENT_LANGUAGE:
            (run_dir / "generated-component.py").write_text(
                component["source"],
                encoding="utf-8",
            )
            (implementation_dir / entrypoint).write_text(
                component["source"],
                encoding="utf-8",
            )
        else:
            _write_json(implementation_dir / entrypoint, component)
    replica = {
        "schema_version": "replica/v1",
        "source_intake_sha256": intake_sha256,
        "replica_id": second_pass["replica_id"],
        "replica_spec": replica_spec,
        "execution_plan": execution_plan,
    }
    _write_json(run_dir / "replica.json", replica)
    if "experience" in second_pass:
        _write_json(run_dir / "experience.json", second_pass["experience"])
    (run_dir / "tests.json").write_bytes(tests_bytes)
    _write_json(run_dir / "test-suite-lock.json", frozen)

    step_limits = execution_plan["steps"][0]["limits"]
    evaluation = evaluate_frozen_suite(
        run_dir,
        expected_test_sha256=frozen["sha256"],
        run_replica=lambda runtime_input: _run_replica_in_subprocess(
            run_dir,
            runtime_input,
            timeout_seconds=step_limits["timeout_seconds"],
            max_output_bytes=step_limits["max_output_bytes"],
        ),
        semantic_judge=_semantic_judge_not_configured,
        judge_identity="fixed-deterministic-evaluator/v1",
        judge_mode="independent",
    )
    attempts = list(generation_attempts)
    if generated_component_record is not None:
        attempts.append(
            {
                "attempt": len(attempts) + 1,
                "language": generated_component_record["component"][
                    "language"
                ],
                "component_sha256": generated_component_record[
                    "component_sha256"
                ],
                "status": evaluation["status"],
                "passed": evaluation["passed"],
                "total": evaluation["total"],
            }
        )
        _write_json(
            run_dir / "generation-attempts.json",
            {
                "schema_version": "replica-generation-attempts/v1",
                "attempts": attempts,
            },
        )
    write_completion_report_artifact(
        run_dir,
        second_pass.get("completion_contract"),
    )
    build_record = _write_build_record(
        run_dir,
        second_pass=second_pass,
        intake_sha256=intake_sha256,
        has_generated_component=generated_component_record is not None,
    )
    report = write_final_report(run_dir, build_record) if include_report else None
    if report is not None:
        append_completion_report_section(run_dir, run_dir / "report.md")
    status = (
        "BUILT_AND_PASSED"
        if evaluation["status"] == "PASSED"
        else "BUILT_WITH_FAILURES"
    )
    return {
        "schema_version": "replica-build-result/v1",
        "status": status,
        "source_intake_sha256": intake_sha256,
        "run_dir": str(run_dir.resolve()),
        "replica_path": str((run_dir / "replica.json").resolve()),
        "evaluation": evaluation,
        "report": report,
        "generation_attempts": attempts,
    }


def _resolve_second_pass_for_build(
    source: Path,
    workspace: Path,
) -> tuple[bytes, str, dict[str, Any], dict[str, Any]]:
    intake = receive_second_pass(source, workspace)
    intake_sha256 = intake["sha256"]
    source_bytes, intake_value = _load_preserved_intake(
        workspace,
        intake_sha256,
    )
    second_pass_candidate = _validate_second_pass(
        intake_value,
        allow_missing_implementation=True,
    )
    second_pass, operation_selection = select_codex_operator_implementation(
        second_pass_candidate,
        source_intake_sha256=intake_sha256,
    )
    second_pass = _validate_second_pass(second_pass)
    _require_deterministic_evaluation(second_pass)
    return source_bytes, intake_sha256, second_pass, operation_selection


def _evaluate_codex_operator(
    source: Path,
    workspace: Path,
    *,
    include_report: bool = False,
    component_generator: ComponentGenerator | None = None,
    generation_attempt_limit: int | None = None,
    prior_generation_attempts: list[dict[str, Any]] | None = None,
    initial_attempt_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    (
        source_bytes,
        intake_sha256,
        second_pass,
        operation_selection,
    ) = _resolve_second_pass_for_build(
        source,
        workspace,
    )
    run_dir = (
        workspace
        / "runs"
        / second_pass["replica_id"]
        / intake_sha256
    )
    if run_dir.exists():
        raise ValueError(f"Replica run already exists: {run_dir}")
    if component_generator is None:
        raise ValueError("Codex operator component is required")
    replica_spec = _make_replica_spec(second_pass, intake_sha256)
    tests_bytes, frozen = _prepare_frozen_tests(second_pass["tests"])
    if generation_attempt_limit is not None and (
        type(generation_attempt_limit) is not int
        or not 1 <= generation_attempt_limit <= MAX_GENERATION_ATTEMPTS
    ):
        raise ValueError("invalid generation attempt limit")
    max_attempts = (
        generation_attempt_limit
        if generation_attempt_limit is not None
        else MAX_GENERATION_ATTEMPTS
    )
    attempt_history = json.loads(
        json.dumps(
            prior_generation_attempts or [],
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    if (
        not isinstance(attempt_history, list)
        or len(attempt_history) + max_attempts > MAX_GENERATION_ATTEMPTS
    ):
        raise ValueError("invalid prior generation attempts")
    if initial_attempt_context is not None and max_attempts != 1:
        raise ValueError(
            "initial attempt context requires a single generation attempt"
        )
    previous_attempt = None

    for local_attempt in range(1, max_attempts + 1):
        attempt = len(attempt_history) + 1
        attempt_context = (
            dict(initial_attempt_context)
            if local_attempt == 1 and initial_attempt_context is not None
            else {
                "attempt": attempt,
                "max_attempts": MAX_GENERATION_ATTEMPTS,
                "previous_attempt": previous_attempt,
            }
        )
        try:
            generated_component_record = (
                prepare_generated_component(
                    second_pass,
                    component_generator,
                    attempt_context=attempt_context,
                )
                if component_generator is not None
                else None
            )
        except ValueError:
            attempt_history.append(
                {
                    "attempt": attempt,
                    "language": "unvalidated",
                    "component_sha256": None,
                    "status": "VALIDATION_FAILED",
                    "passed": None,
                    "total": None,
                }
            )
            if local_attempt == max_attempts:
                raise
            previous_attempt = {
                "language": "unvalidated",
                "status": "VALIDATION_FAILED",
                "passed": None,
                "total": None,
            }
            continue
        execution_plan = _make_execution_plan(
            second_pass,
            generated_component_record,
        )
        safety = assess_plan_safety(
            execution_plan,
            available_operations=set(OPERATION_INPUT_FIELDS),
            operation_input_fields=OPERATION_INPUT_FIELDS,
            generated_component_operations={GENERATED_COMPONENT_OPERATION},
            generated_code_operations={GENERATED_COMPONENT_OPERATION},
        )
        if safety["status"] != "SAFE_TO_EXECUTE":
            violations = ", ".join(
                violation["code"] for violation in safety["violations"]
            )
            raise ValueError(
                f"Second-pass result is not buildable: {violations}"
            )

        run_dir.mkdir(parents=True)
        try:
            result = _materialize_and_evaluate_run(
                run_dir,
                source_bytes=source_bytes,
                second_pass=second_pass,
                operation_selection=operation_selection,
                intake_sha256=intake_sha256,
                replica_spec=replica_spec,
                execution_plan=execution_plan,
                safety=safety,
                tests_bytes=tests_bytes,
                frozen=frozen,
                include_report=include_report,
                generated_component_record=generated_component_record,
                generation_attempts=attempt_history,
            )
        except RuntimeError:
            shutil.rmtree(run_dir)
            attempt_history.append(
                {
                    "attempt": attempt,
                    "language": generated_component_record["component"][
                        "language"
                    ],
                    "component_sha256": generated_component_record[
                        "component_sha256"
                    ],
                    "status": "RUNTIME_FAILED",
                    "passed": None,
                    "total": None,
                }
            )
            if local_attempt == max_attempts:
                raise RuntimeError(
                    "Replica generation failed at runtime after "
                    f"{max_attempts} attempts"
                ) from None
            previous_attempt = {
                "language": generated_component_record["component"][
                    "language"
                ],
                "status": "RUNTIME_FAILED",
                "passed": None,
                "total": None,
            }
            continue
        except Exception:
            shutil.rmtree(run_dir)
            raise
        if (
            result["status"] == "BUILT_AND_PASSED"
            or local_attempt == max_attempts
        ):
            return result

        attempt_history = result["generation_attempts"]
        previous_attempt = {
            "language": generated_component_record["component"]["language"],
            "status": "EVALUATION_FAILED",
            "passed": result["evaluation"]["passed"],
            "total": result["evaluation"]["total"],
        }
        shutil.rmtree(run_dir)

    raise RuntimeError("Replica generation attempts were exhausted")
