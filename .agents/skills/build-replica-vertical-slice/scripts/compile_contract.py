from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any, NoReturn


SCHEMA = "replica-second-pass-result/v1"
FIELDS = {
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


def _reject_constant(value: str) -> NoReturn:
    raise ValueError(f"non-standard JSON constant: {value}")


def _read_json(path: Path) -> tuple[bytes, Any]:
    try:
        raw = path.read_bytes()
        return raw, json.loads(raw.decode("utf-8-sig"), parse_constant=_reject_constant)
    except FileNotFoundError:
        raise ValueError(f"missing source: {path}") from None
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError(f"invalid JSON in {path}: {error}") from None


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _text_list(value: Any, *, allow_empty: bool = True) -> bool:
    return isinstance(value, list) and (allow_empty or bool(value)) and all(
        _text(item) for item in value
    )


def _validate(value: Any) -> dict[str, Any]:
    valid_fields = (FIELDS, FIELDS - {"implementation"})
    if not isinstance(value, dict) or not any(set(value) == fields for fields in valid_fields):
        raise ValueError("invalid second-pass result fields")
    criteria = value.get("acceptance_criteria")
    tests = value.get("tests")
    cases = tests.get("cases") if isinstance(tests, dict) else None
    valid_criteria = isinstance(criteria, list) and bool(criteria) and all(
        isinstance(item, dict)
        and set(item) == {"id", "description"}
        and _text(item.get("id"))
        and _text(item.get("description"))
        for item in criteria
    )
    criterion_ids = [item["id"] for item in criteria] if valid_criteria else []
    valid_case_criteria = isinstance(cases, list) and all(
        isinstance(case, dict)
        and _text_list(case.get("criterion_ids"), allow_empty=False)
        for case in cases
    )
    covered_ids = (
        {
            criterion_id
            for case in cases
            for criterion_id in case["criterion_ids"]
        }
        if valid_case_criteria
        else set()
    )
    required_kinds = {"normal", "boundary", "insufficient_information"}
    input_contract = value.get("input_contract")
    output_contract = value.get("output_contract")
    case_ids = (
        [case.get("id") for case in cases]
        if isinstance(cases, list) and all(isinstance(case, dict) for case in cases)
        else []
    )
    valid_cases = bool(cases) and all(
        isinstance(case.get("id"), str)
        and bool(case["id"])
        and case.get("kind") in required_kinds
        and "input" in case
        and _text_list(case.get("criterion_ids"), allow_empty=False)
        and isinstance(case.get("deterministic_assertions"), list)
        and isinstance(case.get("semantic_criteria"), list)
        and all(_text(item) for item in case["semantic_criteria"])
        and bool(case["deterministic_assertions"] or case["semantic_criteria"])
        and all(
            isinstance(assertion, dict)
            and assertion.get("type") in {"equals", "contains"}
            and "value" in assertion
            and (assertion["type"] != "contains" or isinstance(assertion["value"], str))
            for assertion in case["deterministic_assertions"]
        )
        for case in cases or []
    )
    if (
        value.get("schema_version") != SCHEMA
        or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value.get("replica_id", ""))
        or not all(_text(value.get(name)) for name in ("company", "capability", "canonical_claim"))
        or value.get("evidence_level") not in {"direct", "public", "claim_only"}
        or value.get("readiness") != "ready"
        or value.get("handoff") != "build"
        or not isinstance(input_contract, dict)
        or set(input_contract) != {"type", "required"}
        or input_contract.get("type") != "object"
        or not _text_list(input_contract.get("required"), allow_empty=False)
        or len(set(input_contract["required"])) != len(input_contract["required"])
        or not isinstance(output_contract, dict)
        or set(output_contract) != {"type", "format"}
        or not _text(output_contract.get("type"))
        or not _text(output_contract.get("format"))
        or not valid_criteria
        or len(set(criterion_ids)) != len(criterion_ids)
        or not _text_list(value.get("supported_scope"))
        or not _text_list(value.get("unsupported_scope"))
        or not _text_list(value.get("limitations"))
        or not isinstance(tests, dict)
        or tests.get("schema_version") != "replica-tests/v1"
        or not isinstance(cases, list)
        or not valid_cases
        or len(set(case_ids)) != len(case_ids)
        or not required_kinds <= {case.get("kind") for case in cases if isinstance(case, dict)}
        or set(criterion_ids) != covered_ids
    ):
        raise ValueError("invalid or incomplete ready build contract")
    return value


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _write_new(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def compile_contract(source: Path, workspace: Path, evaluation_vault: Path) -> dict[str, Any]:
    source = source.resolve(strict=True)
    workspace = workspace.resolve()
    evaluation_vault = evaluation_vault.resolve()
    if _inside(workspace, evaluation_vault) or _inside(evaluation_vault, workspace):
        raise ValueError("workspace and evaluation vault must not overlap")
    if _inside(source, workspace):
        raise ValueError("source must be outside the public workspace")

    source_bytes, parsed = _read_json(source)
    contract = _validate(parsed)
    digest = hashlib.sha256(source_bytes).hexdigest()
    replica_id = contract["replica_id"]
    task_dir = workspace / "hybrid-tasks" / replica_id / digest
    private_dir = evaluation_vault / "hybrid-runs" / replica_id / digest
    if task_dir.exists() or private_dir.exists():
        raise ValueError("compiled contract already exists")

    tests_bytes = (
        json.dumps(contract["tests"], ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode("utf-8")
    tests_digest = hashlib.sha256(tests_bytes).hexdigest()
    try:
        task_dir.mkdir(parents=True)
        private_dir.mkdir(parents=True)
        (private_dir / "second-pass.json").write_bytes(source_bytes)
        (private_dir / "tests.json").write_bytes(tests_bytes)
        _write_new(
            private_dir / "test-suite-lock.json",
            {
                "schema_version": "replica-test-lock/v1",
                "status": "FROZEN",
                "sha256": tests_digest,
                "case_count": len(contract["tests"]["cases"]),
            },
        )
        evidence = {
            "schema_version": "replica-execution-evidence/v1",
            "source_contract_sha256": digest,
            "replica_id": contract["replica_id"],
            "company": contract["company"],
            "capability": contract["capability"],
            "canonical_claim": contract["canonical_claim"],
            "evidence_level": contract["evidence_level"],
        }
        spec = {
            "schema_version": "replica-execution-spec/v1",
            "source_contract_sha256": digest,
            "input_contract": contract["input_contract"],
            "output_contract": contract["output_contract"],
            "acceptance_criteria": contract["acceptance_criteria"],
            "supported_scope": contract["supported_scope"],
            "unsupported_scope": contract["unsupported_scope"],
            "limitations": contract["limitations"],
        }
        request = {
            **evidence,
            **{key: value for key, value in spec.items() if key not in {"schema_version", "source_contract_sha256"}},
            "schema_version": "replica-hybrid-builder-request/v1",
            "implementation_hint": contract.get("implementation"),
            "evaluation_isolation": "same-workspace",
        }
        _write_new(task_dir / "evidence.json", evidence)
        _write_new(task_dir / "spec.json", spec)
        _write_new(task_dir / "builder-request.json", request)
        _write_new(
            task_dir / "asset-requests.json",
            {"schema_version": "replica-asset-requests/v1", "assets": []},
        )
        (task_dir / "attempts" / "attempt-01" / "implementation").mkdir(parents=True)
    except Exception:
        shutil.rmtree(task_dir, ignore_errors=True)
        shutil.rmtree(private_dir, ignore_errors=True)
        raise

    return {
        "status": "PREPARED",
        "source_sha256": digest,
        "task_dir": str(task_dir),
        "request_path": str(task_dir / "builder-request.json"),
        "asset_requests_path": str(task_dir / "asset-requests.json"),
        "implementation_path": str(task_dir / "attempts" / "attempt-01" / "implementation" / "replica.py"),
        "evaluation_isolation": "same-workspace",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare one hybrid Replica build task.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--evaluation-vault", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = compile_contract(args.source, args.workspace, args.evaluation_vault)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
