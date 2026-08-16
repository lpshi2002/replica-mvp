from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any


def _reject_nonstandard_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


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


def _write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    try:
        content = "".join(
            json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n"
            for value in values
        )
    except (TypeError, ValueError):
        raise ValueError("evaluation artifact must contain standard JSON") from None
    path.write_text(
        content,
        encoding="utf-8",
    )


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"missing file: {path}") from None
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON in {path}: {error}") from None


def _is_valid_lock(value: Any, digest: str, case_count: int) -> bool:
    return (
        isinstance(value, dict)
        and set(value)
        == {"schema_version", "status", "sha256", "case_count"}
        and value.get("schema_version") == "replica-test-lock/v1"
        and value.get("status") == "FROZEN"
        and value.get("sha256") == digest
        and type(value.get("case_count")) is int
        and value["case_count"] == case_count
    )


def freeze_test_suite(source: Path, run_dir: Path) -> dict[str, Any]:
    source_bytes = source.read_bytes()
    try:
        suite = json.loads(
            source_bytes.decode("utf-8-sig"),
            parse_constant=_reject_nonstandard_constant,
        )
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError(f"invalid test suite JSON in {source}: {error}") from None
    if (
        not isinstance(suite, dict)
        or suite.get("schema_version") != "replica-tests/v1"
        or not isinstance(suite.get("cases"), list)
        or not all(isinstance(case, dict) for case in suite["cases"])
    ):
        raise ValueError("test suite must contain a cases list")
    required_kinds = {"normal", "boundary", "insufficient_information"}
    if not required_kinds <= {case.get("kind") for case in suite["cases"]}:
        raise ValueError("test suite is missing required test kinds")
    case_ids = [case.get("id") for case in suite["cases"]]
    if (
        not all(isinstance(case_id, str) and case_id for case_id in case_ids)
        or len(set(case_ids)) != len(case_ids)
    ):
        raise ValueError("test case ids must be unique non-empty strings")
    inputs = [case.get("input") for case in suite["cases"]]
    if any(
        _json_equal(candidate, existing)
        for index, candidate in enumerate(inputs)
        for existing in inputs[:index]
    ):
        raise ValueError("test case inputs must be unique")
    for case in suite["cases"]:
        assertions = case.get("deterministic_assertions")
        criteria = case.get("semantic_criteria")
        if (
            "input" not in case
            or not isinstance(case.get("kind"), str)
            or not isinstance(assertions, list)
            or not all(isinstance(assertion, dict) for assertion in assertions)
            or not isinstance(criteria, list)
            or not all(isinstance(criterion, str) and criterion for criterion in criteria)
            or not (assertions or criteria)
        ):
            raise ValueError(f"invalid test case: {case.get('id', '')}")
        for assertion in assertions:
            if assertion.get("type") not in {"equals", "contains"}:
                raise ValueError(
                    f"unsupported assertion in test case {case['id']}"
                )
            if "value" not in assertion or (
                assertion["type"] == "contains"
                and not isinstance(assertion["value"], str)
            ):
                raise ValueError(f"invalid assertion in test case {case['id']}")

    digest = hashlib.sha256(source_bytes).hexdigest()
    frozen = {
        "schema_version": "replica-test-lock/v1",
        "status": "FROZEN",
        "sha256": digest,
        "case_count": len(suite["cases"]),
    }
    tests_path = run_dir / "tests.json"
    lock_path = run_dir / "test-suite-lock.json"
    if tests_path.exists() or lock_path.exists():
        if tests_path.exists() and lock_path.exists():
            existing = _read_json(lock_path)
            existing_digest = hashlib.sha256(tests_path.read_bytes()).hexdigest()
            if (
                digest == existing_digest
                and _is_valid_lock(existing, digest, len(suite["cases"]))
            ):
                return existing
        raise ValueError(f"test suite is already frozen in {run_dir}")

    run_dir.mkdir(parents=True, exist_ok=True)
    tests_path.write_bytes(source_bytes)
    _write_json(lock_path, frozen)
    return frozen


def _json_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _json_equal(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _json_equal(left[key], right[key]) for key in left
        )
    return type(left) is type(right) and left == right


def _require_standard_json(value: Any) -> None:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        raise ValueError("evaluation artifact must contain standard JSON") from None


def _check_assertion(assertion: dict[str, Any], output: Any) -> dict[str, Any]:
    assertion_type = assertion.get("type")
    expected = assertion.get("value")
    if assertion_type == "equals":
        passed = _json_equal(output, expected)
    elif assertion_type == "contains":
        passed = isinstance(output, str) and isinstance(expected, str) and expected in output
    else:
        passed = False
    return {
        "type": assertion_type,
        "pass": passed,
    }


def evaluate_frozen_suite(
    run_dir: Path,
    *,
    expected_test_sha256: str,
    run_replica: Callable[[Any], Any],
    semantic_judge: Callable[[dict[str, Any]], dict[str, Any]],
    judge_identity: str,
    judge_mode: str,
) -> dict[str, Any]:
    if not isinstance(judge_identity, str) or not judge_identity.strip():
        raise ValueError("judge_identity must be a non-empty string")
    if judge_mode not in {"independent", "same_session"}:
        raise ValueError("judge_mode must be independent or same_session")

    tests_path = run_dir / "tests.json"
    lock = _read_json(run_dir / "test-suite-lock.json")
    tests_bytes = tests_path.read_bytes()
    digest = hashlib.sha256(tests_bytes).hexdigest()
    if digest != expected_test_sha256:
        raise ValueError("frozen test suite does not match the trusted digest")
    suite = json.loads(tests_bytes.decode("utf-8-sig"))
    if not _is_valid_lock(lock, expected_test_sha256, len(suite["cases"])):
        raise ValueError("frozen test suite changed after it was locked")
    artifact_paths = [
        run_dir / "replica_outputs.jsonl",
        run_dir / "results.jsonl",
        run_dir / "evaluation-summary.json",
    ]
    if any(path.exists() for path in artifact_paths):
        raise ValueError(f"evaluation artifacts already exist in {run_dir}")

    first_outputs = [run_replica(case["input"]) for case in suite["cases"]]
    for output in first_outputs:
        _require_standard_json(output)
    repeated_outputs = [run_replica(case["input"]) for case in suite["cases"]]
    for output in repeated_outputs:
        _require_standard_json(output)
    if not all(
        _json_equal(first, repeated)
        for first, repeated in zip(first_outputs, repeated_outputs, strict=True)
    ):
        raise RuntimeError("replica output is not deterministic for the same input")

    outputs = [
        {"case_id": case["id"], "output": output}
        for case, output in zip(suite["cases"], first_outputs, strict=True)
    ]
    outputs_path = run_dir / "replica_outputs.jsonl"
    _write_jsonl(outputs_path, outputs)

    results = []
    for case, output_record in zip(suite["cases"], outputs, strict=True):
        checks = [
            _check_assertion(assertion, output_record["output"])
            for assertion in case["deterministic_assertions"]
        ]
        deterministic = {
            "status": (
                "NOT_REQUIRED"
                if not checks
                else "PASSED" if all(check["pass"] for check in checks) else "FAILED"
            ),
            "checks": checks,
        }
        criteria = case["semantic_criteria"]
        if criteria:
            judged = semantic_judge(
                {
                    "case_id": case["id"],
                    "kind": case["kind"],
                    "input": case["input"],
                    "replica_output": output_record["output"],
                    "semantic_criteria": criteria,
                    "reference": case.get("reference"),
                }
            )
            if (
                not isinstance(judged, dict)
                or not isinstance(judged.get("pass"), bool)
                or not isinstance(judged.get("reason"), str)
                or not judged["reason"].strip()
            ):
                raise RuntimeError(
                    "semantic judge must return boolean pass and non-empty reason"
                )
            semantic = {
                "status": "PASSED" if judged["pass"] else "FAILED",
                "reason": judged["reason"],
                "judge_identity": judge_identity,
                "judge_mode": judge_mode,
            }
        else:
            semantic = {
                "status": "NOT_REQUIRED",
                "judge_identity": judge_identity,
                "judge_mode": judge_mode,
            }
        passed = (
            deterministic["status"] in {"PASSED", "NOT_REQUIRED"}
            and semantic["status"] in {"PASSED", "NOT_REQUIRED"}
        )
        results.append(
            {
                "case_id": case["id"],
                "kind": case["kind"],
                "deterministic": deterministic,
                "semantic": semantic,
                "pass": passed,
            }
        )

    results_path = run_dir / "results.jsonl"
    _write_jsonl(results_path, results)
    passed_count = sum(result["pass"] for result in results)
    summary = {
        "schema_version": "replica-evaluation-summary/v1",
        "status": "PASSED" if passed_count == len(results) else "FAILED",
        "passed": passed_count,
        "total": len(results),
        "test_suite_sha256": digest,
        "outputs_sha256": hashlib.sha256(outputs_path.read_bytes()).hexdigest(),
        "results_sha256": hashlib.sha256(results_path.read_bytes()).hexdigest(),
        "judge_identity": judge_identity,
        "judge_mode": judge_mode,
    }
    _write_json(run_dir / "evaluation-summary.json", summary)
    return summary
