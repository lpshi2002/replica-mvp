from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, NoReturn

from run_hybrid import execute


def _reject_constant(value: str) -> NoReturn:
    raise ValueError(f"non-standard JSON constant: {value}")


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=_reject_constant)
    except FileNotFoundError:
        raise ValueError(f"missing evaluator input: {path}") from None
    except ValueError as error:
        raise ValueError(f"invalid evaluator input {path.name}: {error}") from None


def _json_equal(left: Any, right: Any) -> bool:
    return type(left) is type(right) and left == right


def _assertion_passes(assertion: dict[str, Any], output: Any) -> bool:
    if assertion["type"] == "equals":
        return _json_equal(output, assertion["value"])
    return isinstance(output, str) and assertion["value"] in output


def _write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def _write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        for value in values:
            stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")


def evaluate(
    task_dir: Path,
    evaluation_vault: Path,
    attempt: int,
    timeout: int,
    maximum: int,
) -> dict[str, Any]:
    task_dir = task_dir.resolve(strict=True)
    evaluation_vault = evaluation_vault.resolve(strict=True)
    request = _load(task_dir / "builder-request.json")
    replica_id = request.get("replica_id")
    digest = request.get("source_contract_sha256")
    if (
        request.get("schema_version") != "replica-hybrid-builder-request/v1"
        or not isinstance(replica_id, str)
        or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", replica_id)
        or not isinstance(digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
    ):
        raise ValueError("invalid public builder request")
    implementation = task_dir / "attempts" / f"attempt-{attempt:02d}" / "implementation" / "replica.py"
    if not implementation.is_file():
        raise ValueError("candidate implementation is missing")
    candidate_bytes = implementation.read_bytes()
    candidate_sha256 = hashlib.sha256(candidate_bytes).hexdigest()

    private_root = evaluation_vault / "hybrid-runs" / replica_id / digest
    tests_path = private_root / "tests.json"
    tests_bytes = tests_path.read_bytes()
    lock = _load(private_root / "test-suite-lock.json")
    tests_sha256 = hashlib.sha256(tests_bytes).hexdigest()
    suite = json.loads(tests_bytes.decode("utf-8-sig"), parse_constant=_reject_constant)
    if (
        lock.get("schema_version") != "replica-test-lock/v1"
        or lock.get("status") != "FROZEN"
        or lock.get("sha256") != tests_sha256
        or lock.get("case_count") != len(suite.get("cases", []))
    ):
        raise ValueError("frozen test suite changed after compilation")
    cases = suite["cases"]
    if any(case.get("semantic_criteria") for case in cases):
        return {
            "status": "EVALUATION_BLOCKED",
            "failure_class": "independent_judge_required",
            "attempt": attempt,
            "passed": 0,
            "total": len(cases),
            "retryable": False,
        }

    attempt_dir = private_root / "attempts" / f"attempt-{attempt:02d}"
    completed_attempts = sorted(path.name for path in attempt_dir.parent.glob("attempt-*") if path.is_dir())
    expected_attempts = [f"attempt-{number:02d}" for number in range(1, attempt)]
    if completed_attempts != expected_attempts:
        raise ValueError("evaluation attempts must be submitted in order")
    if attempt_dir.exists():
        raise ValueError("evaluation attempt already exists")
    attempt_dir.mkdir(parents=True)
    manifest = _load(task_dir / "assets.json")
    outputs: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    passed = 0
    saw_runtime_failure = False
    try:
        for case in cases:
            case_id = case["id"]
            with TemporaryDirectory() as temporary_directory:
                temporary_root = Path(temporary_directory)
                candidate = temporary_root / "replica.py"
                candidate.write_bytes(candidate_bytes)
                output_dir = temporary_root / "outputs"
                output_dir.mkdir()
                envelope = {
                    "schema_version": "replica-hybrid-request/v1",
                    "input": case["input"],
                    "assets": manifest["assets"],
                    "assets_dir": str((task_dir / "assets").resolve()),
                    "output_dir": str(output_dir.resolve()),
                }
                try:
                    output = execute(candidate, envelope, timeout, maximum)
                    assertion_results = [
                        _assertion_passes(assertion, output)
                        for assertion in case["deterministic_assertions"]
                    ]
                    case_passed = all(assertion_results)
                    error_class = None if case_passed else "deterministic_failure"
                    error_detail = None
                except RuntimeError as error:
                    output = None
                    assertion_results = []
                    case_passed = False
                    error_class = "runtime_failure"
                    error_detail = str(error)
                    saw_runtime_failure = True
            outputs.append({"case_id": case_id, "output": output, "error": error_detail})
            results.append(
                {
                    "case_id": case_id,
                    "kind": case["kind"],
                    "pass": case_passed,
                    "assertions": assertion_results,
                    "failure_class": error_class,
                }
            )
            passed += int(case_passed)
        if hashlib.sha256(implementation.read_bytes()).hexdigest() != candidate_sha256:
            raise ValueError("candidate changed during evaluation")
        _write_jsonl(attempt_dir / "replica_outputs.jsonl", outputs)
        _write_jsonl(attempt_dir / "results.jsonl", results)
        status = "BUILT_AND_PASSED" if passed == len(cases) else "EVALUATION_FAILED"
        summary = {
            "schema_version": "replica-hybrid-evaluation/v1",
            "status": status,
            "candidate_sha256": candidate_sha256,
            "test_suite_sha256": tests_sha256,
            "attempt": attempt,
            "passed": passed,
            "total": len(cases),
            "isolation": "same-workspace",
        }
        _write_json(attempt_dir / "summary.json", summary)
    except Exception:
        shutil.rmtree(attempt_dir, ignore_errors=True)
        raise

    return {
        "status": status,
        "failure_class": None if status == "BUILT_AND_PASSED" else (
            "runtime_failure" if saw_runtime_failure else "deterministic_failure"
        ),
        "attempt": attempt,
        "passed": passed,
        "total": len(cases),
        "retryable": status != "BUILT_AND_PASSED" and attempt < 3,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a hybrid candidate without exposing frozen cases.")
    parser.add_argument("task_dir", type=Path)
    parser.add_argument("--evaluation-vault", required=True, type=Path)
    parser.add_argument("--attempt", type=int, choices=(1, 2, 3), required=True)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-output-bytes", type=int, default=10_000_000)
    args = parser.parse_args()
    if args.timeout <= 0 or args.max_output_bytes <= 0:
        parser.error("limits must be positive")
    try:
        result = evaluate(
            args.task_dir,
            args.evaluation_vault,
            args.attempt,
            args.timeout,
            args.max_output_bytes,
        )
    except (OSError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
