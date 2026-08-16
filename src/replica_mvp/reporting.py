from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


BUILD_RECORD_FIELDS = {
    "schema_version",
    "source_intake_sha256",
    "replica_id",
    "company",
    "capability",
    "evidence_level",
    "readiness",
    "buildability_status",
    "build_status",
    "blockers",
    "supported_scope",
    "unsupported_scope",
    "limitations",
    "artifacts",
}

EVALUATION_SUMMARY_FIELDS = {
    "schema_version",
    "status",
    "passed",
    "total",
    "test_suite_sha256",
    "outputs_sha256",
    "results_sha256",
    "judge_identity",
    "judge_mode",
}

SUCCESS_ARTIFACTS = {
    "tests": "tests.json",
    "test_lock": "test-suite-lock.json",
    "outputs": "replica_outputs.jsonl",
    "results": "results.jsonl",
    "evaluation_summary": "evaluation-summary.json",
}


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and item.strip() for item in value
    )


def _reject_nonstandard_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _validate_build_record(record: Any) -> None:
    if not isinstance(record, dict) or set(record) != BUILD_RECORD_FIELDS:
        raise ValueError("invalid build record")
    buildability = record.get("buildability_status")
    build_status = record.get("build_status")
    blockers = record.get("blockers")
    artifacts = record.get("artifacts")
    digest = record.get("source_intake_sha256")
    valid_text = all(
        isinstance(record.get(field), str) and record[field].strip()
        for field in ("replica_id", "company", "capability")
    )
    valid_lists = all(
        _is_string_list(record.get(field))
        for field in (
            "blockers",
            "supported_scope",
            "unsupported_scope",
            "limitations",
        )
    )
    valid_artifacts = (
        isinstance(artifacts, dict)
        and all(
            isinstance(key, str)
            and key
            and isinstance(value, str)
            and value
            for key, value in artifacts.items()
        )
    )
    non_buildable = {
        "INVALID_INPUT",
        "NOT_BUILDABLE",
        "PARTIALLY_BUILDABLE",
    }
    valid_state = (
        (
            buildability in non_buildable
            and build_status == "NOT_STARTED"
            and bool(blockers)
        )
        or (
            buildability == "BUILDABLE"
            and build_status == "FAILED"
            and record.get("readiness") == "ready"
            and bool(blockers)
        )
        or (
            buildability == "BUILDABLE"
            and build_status == "SUCCEEDED"
            and record.get("readiness") == "ready"
            and not blockers
        )
    )
    if (
        record.get("schema_version") != "replica-build-record/v1"
        or not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        or not valid_text
        or record.get("evidence_level") not in {"direct", "public", "claim_only"}
        or record.get("readiness") not in {"ready", "partial", "blocked"}
        or not valid_lists
        or not valid_artifacts
        or not valid_state
    ):
        raise ValueError("invalid build record")


def _validate_artifacts(run_dir: Path, record: dict[str, Any]) -> None:
    artifacts = record["artifacts"]
    if record["build_status"] == "SUCCEEDED" and not {
        "replica",
        *SUCCESS_ARTIFACTS,
    } <= set(artifacts):
        raise ValueError("successful build is missing required artifacts")
    if record["build_status"] == "SUCCEEDED" and any(
        artifacts[name] != expected
        for name, expected in SUCCESS_ARTIFACTS.items()
    ):
        raise ValueError("evaluation artifact paths do not match the run contract")
    if record["build_status"] == "NOT_STARTED" and "replica" in artifacts:
        raise ValueError("a non-buildable run cannot contain a Replica artifact")
    root = run_dir.resolve()
    for relative_path in artifacts.values():
        path = Path(relative_path)
        resolved = (run_dir / path).resolve()
        if path.is_absolute() or not resolved.is_relative_to(root):
            raise ValueError(f"artifact path escapes run directory: {relative_path}")
        if not resolved.exists():
            raise ValueError(f"missing artifact: {relative_path}")


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


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        raise ValueError(f"missing file: {path}") from None
    try:
        values = [
            json.loads(line, parse_constant=_reject_nonstandard_constant)
            for line in lines
            if line.strip()
        ]
    except ValueError as error:
        raise ValueError(f"invalid JSONL in {path}: {error}") from None
    if not all(isinstance(value, dict) for value in values):
        raise ValueError(f"{path} must contain JSON objects")
    return values


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        raise ValueError(f"missing file: {path}") from None


def _failure_reason(result: dict[str, Any]) -> str:
    if isinstance(result.get("reason"), str):
        return result["reason"]
    semantic = result.get("semantic")
    if isinstance(semantic, dict) and isinstance(semantic.get("reason"), str):
        return semantic["reason"]
    return "deterministic assertion failed"


def _markdown_items(values: list[str]) -> str:
    return "\n".join(f"- {value}" for value in values) or "- 없음"


def _validate_evaluation(
    run_dir: Path,
    evaluation: dict[str, Any],
    results: list[dict[str, Any]],
) -> None:
    passed = evaluation.get("passed")
    total = evaluation.get("total")
    status = evaluation.get("status")
    result_passes = [result.get("pass") for result in results]
    case_ids = [result.get("case_id") for result in results]
    digest = evaluation.get("test_suite_sha256")
    outputs_digest = evaluation.get("outputs_sha256")
    results_digest = evaluation.get("results_sha256")
    if (
        set(evaluation) != EVALUATION_SUMMARY_FIELDS
        or evaluation.get("schema_version")
        != "replica-evaluation-summary/v1"
        or type(passed) is not int
        or type(total) is not int
        or total <= 0
        or status not in {"PASSED", "FAILED"}
        or len(results) != total
        or passed < 0
        or passed > total
        or not all(isinstance(value, bool) for value in result_passes)
        or not all(isinstance(case_id, str) and case_id for case_id in case_ids)
        or len(set(case_ids)) != len(case_ids)
        or sum(result_passes) != passed
        or (status == "PASSED") != (passed == total)
        or not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        or not isinstance(outputs_digest, str)
        or len(outputs_digest) != 64
        or any(character not in "0123456789abcdef" for character in outputs_digest)
        or not isinstance(results_digest, str)
        or len(results_digest) != 64
        or any(character not in "0123456789abcdef" for character in results_digest)
        or not isinstance(evaluation.get("judge_identity"), str)
        or not evaluation["judge_identity"].strip()
        or evaluation.get("judge_mode") not in {"independent", "same_session"}
    ):
        raise ValueError("evaluation summary is inconsistent with results")
    tests = _read_json(run_dir / "tests.json")
    lock = _read_json(run_dir / "test-suite-lock.json")
    outputs = _read_jsonl(run_dir / "replica_outputs.jsonl")
    if (
        not isinstance(tests, dict)
        or tests.get("schema_version") != "replica-tests/v1"
        or not isinstance(tests.get("cases"), list)
        or not all(isinstance(case, dict) for case in tests["cases"])
    ):
        raise ValueError("frozen test suite is invalid")
    test_cases = tests["cases"]
    test_ids = [case.get("id") for case in test_cases]
    output_ids = [output.get("case_id") for output in outputs]
    actual_test_digest = _sha256(run_dir / "tests.json")
    if (
        not all(isinstance(case_id, str) and case_id for case_id in test_ids)
        or len(set(test_ids)) != len(test_ids)
        or not isinstance(lock, dict)
        or set(lock) != {"schema_version", "status", "sha256", "case_count"}
        or lock.get("schema_version") != "replica-test-lock/v1"
        or lock.get("status") != "FROZEN"
        or lock.get("sha256") != actual_test_digest
        or type(lock.get("case_count")) is not int
        or lock["case_count"] != len(test_cases)
        or digest != actual_test_digest
        or outputs_digest != _sha256(run_dir / "replica_outputs.jsonl")
        or results_digest != _sha256(run_dir / "results.jsonl")
        or not all(set(output) == {"case_id", "output"} for output in outputs)
        or output_ids != test_ids
        or case_ids != test_ids
    ):
        raise ValueError("evaluation artifacts do not match the frozen run")
    judge_identity = evaluation["judge_identity"]
    judge_mode = evaluation["judge_mode"]
    for case, result in zip(test_cases, results, strict=True):
        deterministic = result.get("deterministic")
        semantic = result.get("semantic")
        assertions = case.get("deterministic_assertions")
        criteria = case.get("semantic_criteria")
        if (
            set(result)
            != {"case_id", "kind", "deterministic", "semantic", "pass"}
            or result.get("kind") != case.get("kind")
            or not isinstance(assertions, list)
            or not isinstance(criteria, list)
            or not isinstance(deterministic, dict)
            or set(deterministic) != {"status", "checks"}
            or not isinstance(deterministic.get("checks"), list)
            or not all(
                isinstance(check, dict)
                and set(check) == {"type", "pass"}
                and isinstance(check.get("type"), str)
                and isinstance(check.get("pass"), bool)
                for check in deterministic["checks"]
            )
            or len(deterministic["checks"]) != len(assertions)
            or [
                check["type"] for check in deterministic["checks"]
            ]
            != [
                assertion.get("type")
                for assertion in assertions
                if isinstance(assertion, dict)
            ]
            or deterministic.get("status")
            != (
                "NOT_REQUIRED"
                if not deterministic["checks"]
                else (
                    "PASSED"
                    if all(check["pass"] for check in deterministic["checks"])
                    else "FAILED"
                )
            )
            or not isinstance(semantic, dict)
            or semantic.get("status") not in {"PASSED", "FAILED", "NOT_REQUIRED"}
            or semantic.get("judge_identity") != judge_identity
            or semantic.get("judge_mode") != judge_mode
            or (bool(criteria) != (semantic.get("status") != "NOT_REQUIRED"))
            or (
                semantic.get("status") in {"PASSED", "FAILED"}
                and (
                    set(semantic)
                    != {"status", "reason", "judge_identity", "judge_mode"}
                    or not isinstance(semantic.get("reason"), str)
                    or not semantic["reason"].strip()
                )
            )
            or (
                semantic.get("status") == "NOT_REQUIRED"
                and set(semantic) != {"status", "judge_identity", "judge_mode"}
            )
            or result.get("pass")
            is not (
                deterministic["status"] in {"PASSED", "NOT_REQUIRED"}
                and semantic["status"] in {"PASSED", "NOT_REQUIRED"}
            )
        ):
            raise ValueError("evaluation summary is inconsistent with results")


def _json_text(value: Any) -> str:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    )


def _write_report_file_exclusive(path: Path, content: str) -> None:
    try:
        stream = path.open("x", encoding="utf-8")
    except FileExistsError:
        raise ValueError(f"final report already exists in {path.parent}") from None
    try:
        with stream:
            stream.write(content)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def write_final_report(
    run_dir: Path,
    build_record: dict[str, Any],
) -> dict[str, Any]:
    if (run_dir / "report.json").exists() or (run_dir / "report.md").exists():
        raise ValueError(f"final report already exists in {run_dir}")
    _validate_build_record(build_record)
    _validate_artifacts(run_dir, build_record)
    buildability_status = build_record.get("buildability_status")
    if buildability_status in {
        "INVALID_INPUT",
        "NOT_BUILDABLE",
        "PARTIALLY_BUILDABLE",
    }:
        evaluation = None
        status = buildability_status
    elif build_record.get("build_status") == "FAILED":
        evaluation = None
        status = "BUILD_FAILED"
    else:
        raw_evaluation = _read_json(run_dir / "evaluation-summary.json")
        if not isinstance(raw_evaluation, dict):
            raise ValueError("evaluation summary must be a JSON object")
        evaluation = dict(raw_evaluation)
        results = _read_jsonl(run_dir / "results.jsonl")
        _validate_evaluation(run_dir, evaluation, results)
        evaluation["failed_cases"] = [
            {
                "case_id": result.get("case_id"),
                "reason": _failure_reason(result),
            }
            for result in results
            if result.get("pass") is not True
        ]
        status = (
            "BUILT_AND_PASSED"
            if evaluation.get("status") == "PASSED"
            else "BUILT_WITH_FAILURES"
        )
    report = {
        "schema_version": "replica-report/v1",
        "status": status,
        "source_intake_sha256": build_record.get("source_intake_sha256"),
        "target": {
            "replica_id": build_record.get("replica_id"),
            "company": build_record.get("company"),
            "capability": build_record.get("capability"),
        },
        "build": {
            "buildability_status": build_record.get("buildability_status"),
            "build_status": build_record.get("build_status"),
            "blockers": build_record.get("blockers", []),
        },
        "evidence": {
            "level": build_record.get("evidence_level"),
            "readiness": build_record.get("readiness"),
        },
        "evaluation": evaluation,
        "scope": {
            "supported": build_record.get("supported_scope", []),
            "unsupported": build_record.get("unsupported_scope", []),
            "limitations": build_record.get("limitations", []),
        },
        "artifacts": build_record.get("artifacts", {}),
        "equivalence": "PUBLIC_SCOPE_REIMPLEMENTATION_ONLY",
    }
    supported = _markdown_items(report["scope"]["supported"])
    unsupported = _markdown_items(report["scope"]["unsupported"])
    limitations = _markdown_items(report["scope"]["limitations"])
    blockers = _markdown_items(report["build"]["blockers"])
    evaluation_values = evaluation or {}
    failed_cases = _markdown_items(
        [
            f'{case["case_id"]}: {case["reason"]}'
            for case in evaluation_values.get("failed_cases", [])
        ]
    )
    artifacts = "\n".join(
        f"- {name}: [{path}]({path})"
        for name, path in report["artifacts"].items()
    ) or "- 없음"
    markdown = f"""# {report["target"]["company"]} Replica 결과

- 기능: {report["target"]["capability"]}
- 최종 상태: **{status}**
- 근거 / readiness: {report["evidence"]["level"]} / {report["evidence"]["readiness"]}
- 테스트: {evaluation_values.get("passed", 0)}/{evaluation_values.get("total", 0)}
- Judge: {evaluation_values.get("judge_identity", "")} ({evaluation_values.get("judge_mode", "")})

## 지원 범위

{supported}

## 지원하지 않는 범위

{unsupported}

## Blocker

{blockers}

## 실패 사례

{failed_cases}

## 한계

{limitations}

## 산출물

{artifacts}

## 동등성 경계

이 결과는 공개 근거로 확인된 기능 범위의 독립 재구현이며 원제품 전체 또는 비공개 구현과의 동등성을 의미하지 않는다.
"""
    report_json = run_dir / "report.json"
    report_markdown = run_dir / "report.md"
    created = []
    try:
        _write_report_file_exclusive(report_json, _json_text(report))
        created.append(report_json)
        _write_report_file_exclusive(report_markdown, markdown)
        created.append(report_markdown)
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return report
