from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


DEPENDENCY_LEVELS = {"oss_only", "commercial_api", "proprietary_data"}
REQUIRED_TEST_KINDS = {
    "normal",
    "boundary",
    "insufficient_information",
    "novel",
}


def _read_object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _read_jsonl(path: Path) -> list[dict[str, Any]] | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        values = [json.loads(line) for line in lines if line.strip()]
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if not values or not all(isinstance(value, dict) for value in values):
        return None
    return values


def _is_nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_completion_contract(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "dependency_level",
        "dependencies",
        "public_sources",
        "input_assets",
        "implementation_scenario",
    }:
        return False
    dependencies = value.get("dependencies")
    sources = value.get("public_sources")
    assets = value.get("input_assets")
    return (
        value.get("dependency_level") in DEPENDENCY_LEVELS
        and isinstance(dependencies, list)
        and bool(dependencies)
        and all(_is_nonempty_text(item) for item in dependencies)
        and isinstance(sources, list)
        and bool(sources)
        and all(
            isinstance(source, dict)
            and set(source) == {"url", "finding"}
            and _is_nonempty_text(source.get("url"))
            and source["url"].startswith(("https://", "http://"))
            and _is_nonempty_text(source.get("finding"))
            for source in sources
        )
        and isinstance(assets, list)
        and bool(assets)
        and all(
            isinstance(asset, dict)
            and set(asset)
            == {"id", "kind", "location", "visibility", "sha256", "case_ids"}
            and all(
                _is_nonempty_text(asset.get(field))
                for field in ("id", "kind", "location", "visibility", "sha256")
            )
            and asset["visibility"] in {"evaluation_vault", "public"}
            and len(asset["sha256"]) == 64
            and all(character in "0123456789abcdef" for character in asset["sha256"])
            and isinstance(asset.get("case_ids"), list)
            and bool(asset["case_ids"])
            and all(_is_nonempty_text(case_id) for case_id in asset["case_ids"])
            for asset in assets
        )
        and _is_nonempty_text(value.get("implementation_scenario"))
    )


def _input_assets_match_frozen_suite(
    run_dir: Path,
    contract: Any,
    case_ids: list[str],
    tests_sha256: str | None,
) -> bool:
    if not _valid_completion_contract(contract):
        return False
    expected_cases = set(case_ids)
    for asset in contract["input_assets"]:
        if (
            asset["kind"] != "structured_json"
            or asset["visibility"] != "evaluation_vault"
            or asset["location"] != "tests.json"
            or asset["sha256"] != tests_sha256
            or set(asset["case_ids"]) != expected_cases
        ):
            return False
    return True


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def _canonical_sha256(value: Any) -> str | None:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(encoded).hexdigest()


def _implementation_receipt(run_dir: Path) -> tuple[bool, str | None]:
    manifest = _read_object(run_dir / "implementation" / "manifest.json")
    record = _read_object(run_dir / "generated-component.json")
    execution_plan = _read_object(run_dir / "execution-plan.json")
    replica = _read_object(run_dir / "replica.json")
    if (
        manifest is None
        or set(manifest) != {"schema_version", "entrypoint", "command"}
        or manifest.get("schema_version") != "replica-implementation/v1"
        or not _is_nonempty_text(manifest.get("entrypoint"))
        or manifest.get("command")
        != "replica-mvp run-replica RUN_DIR < INPUT.json"
        or record is None
        or record.get("schema_version")
        != "replica-generated-component-record/v1"
        or not isinstance(record.get("component"), dict)
        or record.get("component_sha256")
        != _canonical_sha256(record["component"])
        or record.get("request_sha256")
        != _canonical_sha256(record.get("request"))
        or execution_plan is None
        or execution_plan.get("schema_version")
        != "replica-execution-plan/v1"
        or replica is None
        or replica.get("execution_plan") != execution_plan
        or not isinstance(execution_plan.get("steps"), list)
        or len(execution_plan["steps"]) != 1
    ):
        return False, None
    step = execution_plan["steps"][0]
    expected_inputs = {
        "component_sha256": record["component_sha256"],
        "request_sha256": record["request_sha256"],
    }
    if (
        not isinstance(step, dict)
        or step.get("operation") != "execute_generated_component"
        or step.get("inputs") != expected_inputs
    ):
        return False, None
    try:
        implementation_dir = (run_dir / "implementation").resolve()
        entrypoint_value = manifest["entrypoint"]
        entrypoint = Path(entrypoint_value)
        if entrypoint.is_absolute():
            return False, None
        resolved_entrypoint = (implementation_dir / entrypoint).resolve()
        resolved_entrypoint.relative_to(implementation_dir)
    except (OSError, RuntimeError, ValueError):
        return False, None
    component = record["component"]
    language = component.get("language")
    if language == "replica-python/v1":
        source = component.get("source")
        generated_source = run_dir / "generated-component.py"
        try:
            valid = bool(
                entrypoint_value == "replica.py"
                and _is_nonempty_text(source)
                and resolved_entrypoint.is_file()
                and generated_source.is_file()
                and resolved_entrypoint.read_text(encoding="utf-8") == source
                and generated_source.read_text(encoding="utf-8") == source
            )
        except (OSError, UnicodeError):
            valid = False
        return valid, "oss-generated-python" if valid else None
    if language == "replica-expression/v1":
        implementation = _read_object(resolved_entrypoint)
        valid = bool(
            entrypoint_value == "component.json"
            and implementation == component
        )
        return valid, "oss-generated-expression" if valid else None
    return False, None


def _evaluation_artifacts(
    run_dir: Path,
    evaluation: Mapping[str, Any],
) -> tuple[set[Any], list[str], str | None, bool]:
    suite = _read_object(run_dir / "tests.json")
    lock = _read_object(run_dir / "test-suite-lock.json")
    summary = _read_object(run_dir / "evaluation-summary.json")
    outputs = _read_jsonl(run_dir / "replica_outputs.jsonl")
    results = _read_jsonl(run_dir / "results.jsonl")
    if (
        suite is None
        or lock is None
        or summary is None
        or outputs is None
        or results is None
        or not isinstance(suite.get("cases"), list)
    ):
        return set(), [], None, False
    cases = suite["cases"]
    if not cases or not all(isinstance(case, dict) for case in cases):
        return set(), [], None, False
    kinds = {case.get("kind") for case in cases}
    case_ids = [case.get("id") for case in cases]
    if not all(_is_nonempty_text(case_id) for case_id in case_ids):
        return kinds, [], None, False
    tests_sha256 = _sha256(run_dir / "tests.json")
    output_ids = [output.get("case_id") for output in outputs]
    result_ids = [result.get("case_id") for result in results]
    valid = (
        lock.get("schema_version") == "replica-test-lock/v1"
        and lock.get("status") == "FROZEN"
        and lock.get("sha256") == tests_sha256
        and lock.get("case_count") == len(case_ids)
        and summary.get("schema_version") == "replica-evaluation-summary/v1"
        and summary.get("status") == "PASSED"
        and summary.get("passed") == len(case_ids)
        and summary.get("total") == len(case_ids)
        and summary.get("test_suite_sha256") == tests_sha256
        and summary.get("outputs_sha256")
        == _sha256(run_dir / "replica_outputs.jsonl")
        and summary.get("results_sha256") == _sha256(run_dir / "results.jsonl")
        and summary.get("judge_mode") in {"independent", "same_session"}
        and _is_nonempty_text(summary.get("judge_identity"))
        and all(
            summary.get(field) == evaluation.get(field)
            for field in ("status", "passed", "total", "judge_identity", "judge_mode")
        )
        and output_ids == case_ids
        and result_ids == case_ids
        and all(set(output) == {"case_id", "output"} for output in outputs)
        and all(result.get("pass") is True for result in results)
    )
    return kinds, case_ids, tests_sha256, valid


def _completion_report_payload(
    run_dir: Path,
    contract: Any,
) -> dict[str, Any] | None:
    if not _valid_completion_contract(contract):
        return None
    suite = _read_object(run_dir / "tests.json")
    outputs = _read_jsonl(run_dir / "replica_outputs.jsonl")
    results = _read_jsonl(run_dir / "results.jsonl")
    if (
        suite is None
        or outputs is None
        or results is None
        or not isinstance(suite.get("cases"), list)
        or len(suite["cases"]) != len(outputs)
        or len(outputs) != len(results)
    ):
        return None
    cases = []
    for test_case, output, result in zip(
        suite["cases"], outputs, results, strict=True
    ):
        if (
            not isinstance(test_case, dict)
            or output.get("case_id") != test_case.get("id")
            or result.get("case_id") != test_case.get("id")
            or set(output) != {"case_id", "output"}
            or not isinstance(result.get("pass"), bool)
        ):
            return None
        cases.append(
            {
                "case_id": test_case.get("id"),
                "kind": test_case.get("kind"),
                "input": test_case.get("input"),
                "output": output["output"],
                "pass": result["pass"],
            }
        )
    return {
        "schema_version": "replica-completion-report/v1",
        "dependency_level": contract["dependency_level"],
        "dependencies": contract["dependencies"],
        "implementation_scenario": contract["implementation_scenario"],
        "public_sources": contract["public_sources"],
        "input_assets": contract["input_assets"],
        "cases": cases,
    }


def write_completion_report_artifact(
    run_dir: Path,
    contract: Any,
) -> Path | None:
    """Materialize the private, machine-verifiable completion evidence."""

    payload = _completion_report_payload(run_dir, contract)
    if payload is None:
        return None
    path = run_dir / "completion-report.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def append_completion_report_section(run_dir: Path, report_path: Path) -> None:
    """Embed the exact private evidence payload in the human-readable report."""

    payload = _read_object(run_dir / "completion-report.json")
    if payload is None:
        return
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    with report_path.open("a", encoding="utf-8", newline="\n") as report:
        report.write(
            "\n## Replica completion evidence\n\n"
            "The evaluator-vault record below contains the actual frozen inputs, "
            "final outputs, per-kind results, dependency record, and first "
            "implementation scenario.\n\n"
            f"```json\n{rendered}\n```\n"
        )


def _completion_report_matches(
    run_dir: Path,
    contract: Any,
) -> bool:
    expected = _completion_report_payload(run_dir, contract)
    actual = _read_object(run_dir / "completion-report.json")
    if expected is None or actual != expected:
        return False
    try:
        report = (run_dir / "report.md").read_text(encoding="utf-8")
    except FileNotFoundError:
        return False
    rendered = json.dumps(actual, ensure_ascii=False, indent=2, sort_keys=True)
    return (
        "## Replica completion evidence" in report
        and f"```json\n{rendered}\n```" in report
    )


def assess_replica_completion(
    run_dir: Path,
    second_pass: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    *,
    report_available: bool,
) -> dict[str, Any]:
    """Assess one executed Replica against replica-completion-standard."""

    contract = second_pass.get("completion_contract")
    contract_valid = _valid_completion_contract(contract)
    kinds, case_ids, tests_sha256, evaluation_artifacts_valid = (
        _evaluation_artifacts(run_dir, evaluation)
    )
    implementation_receipt_valid, actual_scenario = _implementation_receipt(
        run_dir
    )
    implementation_exists = bool(
        (run_dir / "replica.json").is_file()
        and implementation_receipt_valid
    )
    checks = [
        {
            "id": "public_evidence",
            "pass": bool(contract_valid and contract["public_sources"]),
        },
        {
            "id": "dependency_record",
            "pass": bool(
                contract_valid
                and contract["dependency_level"] in DEPENDENCY_LEVELS
                and contract["dependencies"]
            ),
        },
        {
            "id": "dependency_execution",
            "pass": bool(
                contract_valid
                and contract["dependency_level"] == "oss_only"
                and contract["dependencies"] == ["Python standard library"]
                and implementation_exists
            ),
        },
        {"id": "implementation", "pass": implementation_exists},
        {
            "id": "actual_input",
            "pass": _input_assets_match_frozen_suite(
                run_dir,
                contract,
                case_ids,
                tests_sha256,
            ),
        },
        {"id": "customer_output", "pass": evaluation_artifacts_valid},
        {
            "id": "novel_input",
            "pass": REQUIRED_TEST_KINDS <= kinds,
        },
        {
            "id": "separate_evaluation",
            "pass": evaluation_artifacts_valid,
        },
        {
            "id": "implementation_scenario",
            "pass": bool(
                contract_valid
                and implementation_exists
                and contract["implementation_scenario"] == actual_scenario
            ),
        },
        {
            "id": "final_report",
            "pass": bool(
                report_available
                and _completion_report_matches(run_dir, contract)
            ),
        },
    ]
    if evaluation.get("status") == "BLOCKED":
        status = "execution_blocked"
    elif evaluation.get("status") != "PASSED":
        status = "not_reproduced_on_this_path"
    elif all(check["pass"] for check in checks):
        status = "reproduced"
    elif implementation_exists and evaluation_artifacts_valid:
        status = "partially_reproduced"
    else:
        status = "not_reproduced_on_this_path"
    return {
        "schema_version": "replica-completion-assessment/v1",
        "status": status,
        "checks": checks,
    }


def assess_bundle_execution(
    plan: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    review: Mapping[str, Any],
    *,
    has_outputs: bool,
    public_example_passed: bool,
    public_assets_available: bool,
) -> dict[str, Any]:
    """Technical completion only; the narrative reporting workflow is separate."""
    gaps = list(plan["gaps"])
    if not plan["prepared_before_implementation"]:
        gaps.append("Final evaluation was prepared retrospectively; pre-implementation isolation was not established.")
    if review["status"] != "PASSED":
        gaps.append("Implementation fidelity and generalization review did not pass.")
    if not evaluation["source_unchanged"]:
        gaps.append("The implementation changed its own declared source while executing.")
    if any(d["status"] == "different" for d in evaluation.get("dependencies", [])):
        gaps.append("Observed installed dependency versions differ from the declared bundle versions.")
    if not public_example_passed:
        gaps.append("A separate reusable public example did not execute successfully.")
    if not public_assets_available:
        gaps.append("A required public input asset is unavailable or its hash changed.")
    if evaluation["status"] == "PASSED" and not gaps:
        status = "reproduced"
    elif has_outputs:
        status = "partially_reproduced"
    elif evaluation["failure_category"] in {
        "environment_error", "data_missing", "access_missing", "budget_exhausted", "research_gap",
    }:
        status = "execution_blocked"
    else:
        status = "not_reproduced_on_this_path"
    return {
        "schema_version": "replica-bundle-completion/v1", "reproduction_status": status,
        "candidate_sha256": evaluation["candidate_sha256"], "plan_sha256": evaluation["plan_sha256"],
        "evaluation": dict(evaluation), "implementation_review": dict(review), "missing_conditions": gaps,
    }
