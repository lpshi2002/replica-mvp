"""Frozen final evaluation for Sol/Terra bundles, separate from development feedback."""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from .bundle_runtime import bundle_session, copy_bundle, observe_dependencies, safe_relative, validate_runtime
from .completion import EVALUATION_TEST_KINDS, assess_bundle_execution, research_test_kind
from .experience import validate_experience_profile
from .evaluation import (
    _check_assertion, _is_valid_lock, _json_equal, _path_value, _read_json,
    _require_standard_json, _write_json, _write_jsonl, freeze_test_suite,
)
from .resources import budget_stop, measurement, unknown_resources, utc_now, validate_budget, validate_resources


MAX_SUBMISSIONS = 3
_UNSTARTED = {"PENDING", "RESEARCH_INCOMPLETE"}
PLAN_FIELDS = {
    "runtime", "repeat_policy", "timeout_seconds", "budget", "additional_cases",
    "case_checks", "public_examples", "assets", "output_artifacts",
}


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def value_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def _validate_artifacts(directory: Path, artifacts: dict[str, str], label: str) -> None:
    for name, expected in artifacts.items():
        path = directory / name
        if (not safe_relative(name) or path.is_symlink() or not path.resolve().is_relative_to(directory.resolve())
                or digest(path) != expected):
            raise ValueError(f"{label} artifact hash mismatch")


def _validate_history(root: Path, claim: dict[str, Any]) -> None:
    for attempt in claim.get("bundle_submissions", []):
        archive = attempt.get("development_archive")
        if archive:
            directory = root / archive["path"]
            if not directory.resolve().is_relative_to(root / "evaluator-vault"):
                raise ValueError("development archive escaped the evaluator vault")
            _validate_artifacts(directory, archive["artifacts"], "prior development")
        if attempt.get("result_sha256"):
            directory = root / attempt["public_run_dir"]
            if (not directory.resolve().is_relative_to(root / "final-results" / "runs")
                    or digest(directory / "replica-result.json") != attempt["result_sha256"]):
                raise ValueError("prior evaluation result hash mismatch")
            result = _read_json(directory / "replica-result.json")
            _validate_artifacts(directory, result["artifacts"], "prior public")
            vault = (root / claim["bundle_evaluation"]["plan_path"]).parent / f"attempt-{attempt['attempt']:03d}"
            if not vault.resolve().is_relative_to(root / "evaluator-vault"):
                raise ValueError("prior evaluation escaped the evaluator vault")
            _validate_artifacts(vault, result["private_evidence"], "prior evaluation")


def _sealed_claim(root: Path, claim: dict[str, Any]) -> dict[str, Any]:
    """Read the full claim with sealed tests; older runs kept it in claim.json."""
    path = claim.get("sealed_claim_path")
    if path is None:
        return _read_json(root / claim["claim_payload_path"])
    sealed = root / path
    if (not sealed.resolve().is_relative_to(root / "evaluator-vault") or sealed.is_symlink()
            or digest(sealed) != claim["sealed_claim_sha256"]):
        raise ValueError("sealed claim hash mismatch")
    return _read_json(sealed)


def _research_cases(payload: dict[str, Any], selected: dict[str, Any]) -> list[dict[str, Any]]:
    cases = []
    source_cases = selected.get("tests", [])
    if not isinstance(source_cases, list) or any(
        not isinstance(c, dict) or not isinstance(c.get("id"), str) or not c["id"].strip() or "input" not in c
        for c in source_cases
    ):
        raise ValueError("research tests must be a list of identified input cases")
    for source in source_cases:
        case = deepcopy(source)
        case["kind"] = research_test_kind(source)
        if case["kind"] is None:
            raise ValueError(f"research test {source['id']!r} needs an evaluation kind")
        if isinstance(case.get("input"), str):
            try:
                case["input"] = json.loads(case["input"])
            except ValueError:
                pass
        case.setdefault("deterministic_assertions", [])
        case.setdefault("semantic_criteria", [])
        if not isinstance(case["deterministic_assertions"], list) or not isinstance(case["semantic_criteria"], list):
            raise ValueError("research checks and semantic criteria must be lists")
        if source.get("expected_behavior"):
            case["semantic_criteria"].append(source["expected_behavior"])
        if "reference_facts" in source:
            case["reference"] = {"facts": source["reference_facts"]}
        cases.append(case)
    return cases


def _validate_case_metadata(cases: list[dict[str, Any]], criterion_ids: set[str]) -> None:
    if not isinstance(cases, list) or any(
        not isinstance(c, dict) or not isinstance(c.get("id"), str) or not c["id"].strip() or "input" not in c
        for c in cases
    ):
        raise ValueError("evaluation cases must have identities and inputs")
    ids = {c["id"] for c in cases}
    if len(ids) != len(cases):
        raise ValueError("evaluation case identities must be unique")
    for case in cases:
        if case.get("kind") not in EVALUATION_TEST_KINDS:
            raise ValueError(f"evaluation case {case['id']!r} kind must be one of {sorted(EVALUATION_TEST_KINDS)}")
        covered = case.get("criterion_ids", [])
        if not isinstance(covered, list) or not all(isinstance(i, str) for i in covered) or not set(covered) <= criterion_ids:
            raise ValueError("evaluation case refers to an unknown acceptance criterion")
        relation = case.get("metamorphic")
        if relation is not None and (
            not isinstance(relation, dict) or set(relation) != {"case_id", "relation", "path", "reason"}
            or relation["case_id"] not in ids or relation["case_id"] == case["id"]
            or relation["relation"] not in {"equal", "different"}
            or not isinstance(relation["path"], list)
            or not all(type(part) in {str, int} for part in relation["path"])
            or not isinstance(relation["reason"], str) or not relation["reason"].strip()
        ):
            raise ValueError("invalid metamorphic relation")
        novelty = case.get("novelty")
        if novelty is not None and (
            not isinstance(novelty, dict) or set(novelty) != {"difference", "development_inputs"}
            or not isinstance(novelty["difference"], str) or not novelty["difference"].strip()
            or not isinstance(novelty["development_inputs"], list) or not novelty["development_inputs"]
            or any(_json_equal(case["input"], value) for value in novelty["development_inputs"])
        ):
            raise ValueError("novel input needs a documented difference from distinct development inputs")
        if not isinstance(case.get("repeat_policy", "contract"), str) or case.get("repeat_policy", "contract") not in {"exact", "contract"}:
            raise ValueError("invalid case repeat policy")
        if "session" in case and (not isinstance(case["session"], str) or not case["session"].strip()):
            raise ValueError("a shared case session must be a non-empty name")


def _is_json_path(value: Any) -> bool:
    return isinstance(value, list) and all(type(part) in {str, int} for part in value)


def _validate_assets(assets: Any) -> None:
    fields = {"path", "source", "sha256", "media_type", "provenance", "usage_terms", "visibility"}
    if not isinstance(assets, list):
        raise ValueError("evaluation assets must be a list")
    paths = set()
    for asset in assets:
        if (not isinstance(asset, dict) or set(asset) != fields
                or any(not isinstance(asset[f], str) or not asset[f].strip() for f in fields)
                or not safe_relative(asset["path"]) or asset["path"] in paths
                or asset["visibility"] not in {"evaluation_vault", "public"}
                or len(asset["sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in asset["sha256"])):
            raise ValueError("invalid input asset record")
        paths.add(asset["path"])


def prepare_bundle_evaluation(registry_path: Path, claim_id: str, supplement: Path | None = None) -> dict[str, Any]:
    """Freeze research cases; an additive second-pass supplement never rewrites an old plan."""
    from .agent_harness import _claim_record, _read_registry, _replace_registry, _selected_scenario
    registry = _read_registry(registry_path)
    claim = _claim_record(registry, claim_id)
    root = registry_path.parent.resolve()
    payload = _sealed_claim(root, claim)
    selected = _selected_scenario(payload)
    if selected is None:
        raise ValueError("bundle evaluation requires a research claim")
    previous = claim.get("bundle_evaluation")
    if previous and supplement is None:
        return registry
    if claim.get("bundle_submissions"):
        raise ValueError("evaluation cannot change after a sealed submission; supplement research in a new experiment")
    config = deepcopy(selected.get("evaluation", {}))
    if not isinstance(config, dict) or set(config) - PLAN_FIELDS:
        raise ValueError("invalid bundle evaluation configuration")
    supplement_sha256 = None
    if supplement is not None:
        addition = _read_json(supplement)
        if not isinstance(addition, dict) or set(addition) - PLAN_FIELDS:
            raise ValueError("invalid second-pass evaluation supplement")
        if previous:
            prior = _read_json(root / previous["plan_path"])
            config = prior["configuration"]
        for field, value in addition.items():
            if field in {"additional_cases", "public_examples", "assets"}:
                if not isinstance(value, list):
                    raise ValueError("evaluation supplement collections must be lists")
                config[field] = config.get(field, []) + value
            elif field == "case_checks":
                if not isinstance(value, dict):
                    raise ValueError("case_checks must be an object")
                existing = config.get(field, {})
                if set(existing) & set(value):
                    raise ValueError("supplement cannot replace existing case checks")
                config[field] = {**existing, **value}
            else:
                if field in config and config[field] != value:
                    raise ValueError("supplement cannot replace a frozen execution policy")
                config[field] = value
        supplement_sha256 = digest(supplement)
    if not isinstance(config, dict) or set(config) - PLAN_FIELDS:
        raise ValueError("invalid bundle evaluation configuration")
    cases = _research_cases(payload, selected)
    checks = config.get("case_checks", {})
    if not isinstance(checks, dict) or not set(checks) <= {c["id"] for c in cases}:
        raise ValueError("case checks must reference researched tests")
    acceptance = {c["id"]: c["description"] for c in payload["acceptance_criteria"]}
    for case in cases:
        extra = checks.get(case["id"], {})
        if not isinstance(extra, dict) or set(extra) - {"deterministic_assertions", "criterion_ids", "metamorphic", "novelty", "session"}:
            raise ValueError("supplement can add checks, not replace research inputs or expectations")
        if not isinstance(extra.get("deterministic_assertions", []), list):
            raise ValueError("deterministic assertions must be a list")
        case["deterministic_assertions"].extend(extra.get("deterministic_assertions", []))
        case.update({key: value for key, value in extra.items() if key != "deterministic_assertions"})
    additional_cases = config.get("additional_cases", [])
    if not isinstance(additional_cases, list):
        raise ValueError("additional_cases must be a list")
    cases.extend(deepcopy(additional_cases))
    _validate_case_metadata(cases, set(acceptance))
    runtime = config.get("runtime")
    if runtime is not None:
        validate_runtime(runtime)
    repeat = config.get("repeat_policy", "contract")
    if repeat not in {"exact", "contract"}:
        raise ValueError("invalid repeat policy")
    timeout = config.get("timeout_seconds", 120)
    if type(timeout) not in {int, float} or not 0 < timeout <= 3600:
        raise ValueError("invalid execution timeout")
    budget = validate_budget(config.get("budget", {
        "time_limit_seconds": 600, "cost_limit": None, "stop_on_blocked": True,
    }))
    assets = config.get("assets", [])
    _validate_assets(assets)
    output_artifacts = config.get("output_artifacts", [])
    if not isinstance(output_artifacts, list) or any(
        not isinstance(a, dict) or not {"path", "media_type"} <= set(a) <= {"path", "media_type", "when"}
        or not _is_json_path(a["path"])
        or not isinstance(a["media_type"], str) or "/" not in a["media_type"]
        or ("when" in a and (
            not isinstance(a["when"], dict) or set(a["when"]) != {"path", "in"}
            or not _is_json_path(a["when"]["path"]) or not isinstance(a["when"]["in"], list) or not a["when"]["in"]
        ))
        for a in output_artifacts
    ):
        raise ValueError("output artifacts need a JSON path, media type, and an optional when {path, in} condition")
    examples = config.get("public_examples", [])
    if not isinstance(examples, list) or any(
        not isinstance(e, dict) or set(e) != {"input", "description"}
        or not isinstance(e["description"], str) or not e["description"].strip()
        or any(_json_equal(e["input"], c["input"]) for c in cases) for e in examples
    ):
        raise ValueError("public examples must be distinct from sealed inputs")
    revision = previous.get("revision", 0) + 1 if previous else 1
    vault = root / "evaluator-vault" / claim_id / f"plan-{revision:03d}"
    vault.mkdir(parents=True, exist_ok=False)
    suite_path = vault / "source-tests.json"
    _write_json(suite_path, {"schema_version": "replica-tests/v1", "cases": cases})
    gaps = []
    try:
        lock = freeze_test_suite(suite_path, vault)
    except ValueError as error:
        # Invalid/incomplete research is a recorded gap, never a silently weakened suite.
        lock = None
        gaps.append(str(error))
    suite_path.unlink()
    if not runtime:
        gaps.append("research_gap: execution transport is not prepared")
    covered = {i for c in cases for i in c.get("criterion_ids", [])}
    if covered != set(acceptance):
        gaps.append("research_gap: acceptance criteria do not have complete evaluation coverage")
    if not any(c.get("kind") == "novel" and c.get("novelty") for c in cases):
        gaps.append("research_gap: novel input differences are not prepared")
    relations = {c["metamorphic"]["relation"] for c in cases if c.get("metamorphic")}
    if not {"equal", "different"} <= relations:
        gaps.append("research_gap: invariant and changed-fact relations are not prepared")
    if not examples:
        gaps.append("research_gap: a separate public runtime example is not prepared")
    artifact_paths = [a["path"] for a in output_artifacts]
    for case in cases:
        relation = case.get("metamorphic")
        if relation and relation["relation"] == "different" and not (
            relation["path"] in artifact_paths
            or case.get("repeat_policy", repeat) == "exact"
            or any(a.get("type") == "equals" and a.get("path", []) == relation["path"]
                   for a in case["deterministic_assertions"])
        ):
            # Generated wording always differs, so "different" proves nothing there.
            gaps.append(f"research_gap: case {case['id']} compares a non-deterministic field with a different relation")
    plan = {
        "schema_version": "replica-bundle-evaluation-plan/v1", "claim_id": claim_id,
        "scenario_id": selected["id"], "claim_sha256": digest(root / claim["claim_payload_path"]),
        "sealed_claim_sha256": claim.get("sealed_claim_sha256"),
        "prepared_at": utc_now(), "prepared_before_implementation": (
            claim["status"] in _UNSTARTED and not any((root / claim["builder"]["artifact_namespace"]).rglob("*"))
        ),
        "workflow_coverage": payload.get("workflow_coverage"),
        "revision": revision, "previous_plan_sha256": previous.get("plan_sha256") if previous else None,
        "supplement_sha256": supplement_sha256, "configuration": config,
        "runtime": runtime, "repeat_policy": repeat, "timeout_seconds": timeout,
        "budget": budget, "test_lock": lock, "gaps": gaps,
        "acceptance_criteria": payload["acceptance_criteria"], "public_examples": examples, "assets": assets,
        "output_artifacts": output_artifacts,
    }
    _write_json(vault / "plan.json", plan)
    public_contract_path = root / "claims" / claim_id / f"runtime-contract-{revision:03d}.json"
    _write_json(public_contract_path, {
        "schema_version": "replica-bundle-runtime-contract/v1", "claim_id": claim_id,
        "revision": revision, "plan_sha256": digest(vault / "plan.json"),
        "runtime": runtime, "timeout_seconds": timeout, "budget": budget,
        "output_artifacts": output_artifacts, "public_examples": examples,
        "public_assets": [asset for asset in assets if asset["visibility"] == "public"],
    })
    claim["bundle_evaluation"] = {
        "plan_path": (vault / "plan.json").relative_to(root).as_posix(),
        "plan_sha256": digest(vault / "plan.json"), "revision": revision,
        "public_runtime_contract_path": public_contract_path.relative_to(root).as_posix(),
        "public_runtime_contract_sha256": digest(public_contract_path),
    }
    if claim["status"] in _UNSTARTED:
        # Evaluation gaps are resolved in research before any Agent spends effort on them.
        claim["status"] = "RESEARCH_INCOMPLETE" if gaps else "PENDING"
        claim["research_gaps"] = gaps
    _replace_registry(registry_path, registry)
    return registry


def _judge(judge: Callable | None, request: dict[str, Any], timeout: float = 120) -> dict[str, Any]:
    if judge is None:
        return {"status": "NOT_EVALUATED", "reason": "A separate semantic evaluator is not configured."}
    if timeout <= 0:
        return {"status": "NOT_EVALUATED", "reason": "The frozen evaluation time budget is exhausted."}
    try:
        result = judge({**request, "timeout_seconds": timeout})
        if (not isinstance(result, dict) or type(result.get("pass")) is not bool
                or not isinstance(result.get("reason"), str) or not result["reason"].strip()):
            raise ValueError("judge must return boolean pass and non-empty reason")
        judged = {"status": "PASSED" if result["pass"] else "FAILED", "reason": result["reason"]}
        if "resources" in result:
            judged["resources"] = validate_resources(result["resources"])
        return judged
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        return {"status": "NOT_EVALUATED", "reason": str(error)}


def _copy_assets(assets: list[dict[str, Any]], root: Path) -> list[dict[str, Any]]:
    receipts = []
    for asset in assets:
        source = Path(asset["source"])
        if source.is_symlink() or not source.is_file():
            raise FileNotFoundError("required input asset is missing")
        content = source.read_bytes()
        if hashlib.sha256(content).hexdigest() != asset["sha256"]:
            raise ValueError("input asset hash mismatch")
        target = root / asset["path"]
        if target.exists():
            raise ValueError("input asset would overwrite an implementation file")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        receipts.append({k: v for k, v in asset.items() if k != "source"})
    return receipts


def _capture_artifacts(output: Any, specifications: list[dict[str, Any]], runtime_root: Path,
                       destination: Path) -> list[dict[str, Any]]:
    receipts = []
    for index, specification in enumerate(specifications):
        condition = specification.get("when")
        if condition is not None:
            try:
                state = _path_value(output, condition["path"])
            except (KeyError, IndexError, TypeError):
                raise RuntimeError("output artifact condition field is absent from the output") from None
            if not any(_json_equal(state, value) for value in condition["in"]):
                # A response without effects must not leave the effect's file behind either.
                try:
                    present = _path_value(output, specification["path"])
                except (KeyError, IndexError, TypeError):
                    present = None
                if present is not None:
                    raise RuntimeError("output names an artifact for a response that declares no effect")
                continue
        try:
            name = _path_value(output, specification["path"])
        except (KeyError, IndexError, TypeError):
            raise RuntimeError("required output artifact is absent from the output") from None
        source = runtime_root / name if isinstance(name, str) else runtime_root
        if (not safe_relative(name) or source.is_symlink() or not source.is_file()
                or not source.resolve().is_relative_to(runtime_root.resolve())):
            raise RuntimeError("output artifact must be an actual file inside the runtime directory")
        if not 0 < source.stat().st_size <= 100_000_000:
            raise RuntimeError("output artifact is empty or exceeds the 100 MB limit")
        target = destination / f"{index:03d}-{Path(name).name}"
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as src, target.open("xb") as dst:
            shutil.copyfileobj(src, dst)
        receipts.append({"output_path": specification["path"], "path": str(target),
                         "sha256": digest(target), "media_type": specification["media_type"],
                         "bytes": target.stat().st_size})
    return receipts


def _replace_output_path(output: Any, path: list[Any], value: str) -> Any:
    if not path:
        return value
    result = deepcopy(output)
    parent = _path_value(result, path[:-1])
    parent[path[-1]] = value
    return result


def _evaluate_cases(vault: Path, plan: dict[str, Any], manifest_path: Path,
                    judge: Callable | None) -> tuple[dict[str, Any], dict[str, Any]]:
    cases = _read_json(vault / "tests.json")["cases"]
    outputs, repeated, executions = [], [], []
    started = time.monotonic()
    stop = None
    failure_category = None
    timeout = plan["timeout_seconds"]
    seconds = plan["budget"]["time_limit_seconds"]
    deadline = started + seconds if seconds is not None else float("inf")
    assets, public, output_artifacts, dependencies = [], [], [], []
    source_unchanged = True

    def run_input(run: Callable, value: Any) -> tuple[Any, str | None]:
        nonlocal stop, failure_category
        before = time.monotonic()
        output, error = None, None
        if stop:
            return None, stop
        # A case limited by the remaining total budget exhausts the budget; one that
        # overruns its own per-request limit is a failed case and later cases still run.
        budget_bound = deadline - before < timeout
        try:
            remaining = min(timeout, deadline - before)
            if remaining <= 0:
                raise TimeoutError("evaluation time budget exhausted")
            output = run(value, remaining)
            _require_standard_json(output)
        except (OSError, RuntimeError, ValueError) as failure:
            error = str(failure)
            failure_category = _failure_category(failure)
            if isinstance(failure, TimeoutError):
                if budget_bound:
                    stop = "budget_exhausted"
                else:
                    failure_category = "case_timeout"
            elif plan["budget"]["stop_on_blocked"] and failure_category in {"access_missing", "data_missing", "environment_error"}:
                stop = error
        executions.append({"input_sha256": value_digest(value), "output_sha256": value_digest(output),
                           "elapsed_seconds": time.monotonic() - before, "error": error})
        return output, error

    # Each case runs in a fresh session unless research names a shared session for a stateful sequence.
    groups: list[list[dict[str, Any]]] = []
    named: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        if "session" not in case:
            groups.append([case])
        elif case["session"] in named:
            named[case["session"]].append(case)
        else:
            named[case["session"]] = [case]
            groups.append(named[case["session"]])
    recorded: list[dict[str, Any]] = [{}, {}]
    case_artifacts = {case["id"]: [[], []] for case in cases}
    errors = {}

    def record_outputs() -> None:
        for collection, values in ((outputs, recorded[0]), (repeated, recorded[1])):
            collection[:] = [{"case_id": c["id"], "output": values[c["id"]]} for c in cases if c["id"] in values]
        _write_jsonl(vault / "replica_outputs.jsonl", outputs)
        _write_jsonl(vault / "repeated_outputs.jsonl", repeated)
        _write_jsonl(vault / "execution-records.jsonl", executions)

    try:
        if plan["budget"]["cost_limit"] is not None:
            raise PermissionError("cost budget cannot be enforced without metered economic cost; execution blocked")
        for repetition in (0, 1):
            for group in groups:
                if stop:
                    for case in group:
                        recorded[repetition][case["id"]] = None
                        errors[case["id"]] = stop
                    continue
                with bundle_session(manifest_path, plan["runtime"], min(timeout, deadline - time.monotonic()),
                                    prepare=lambda root: _copy_assets(plan["assets"], root)) as (run, runtime_root):
                    if not dependencies:
                        dependencies = observe_dependencies(_read_json(manifest_path), runtime_root, deadline - time.monotonic())
                    assets = [{k: v for k, v in a.items() if k != "source"} for a in plan["assets"]]
                    for case in group:
                        output, error = run_input(run, case["input"])
                        recorded[repetition][case["id"]] = output
                        captured = []
                        if not error:
                            try:
                                captured = _capture_artifacts(output, plan["output_artifacts"], runtime_root,
                                                              vault / "artifacts" / str(len(executions)))
                                output_artifacts.extend(captured)
                            except (OSError, ValueError, RuntimeError) as failure:
                                error = str(failure)
                                failure_category = _failure_category(failure)
                                executions[-1]["error"] = error
                        case_artifacts[case["id"]][repetition] = captured
                        if error:
                            errors[case["id"]] = error
                        record_outputs()
                    manifest = _read_json(manifest_path)
                    source_unchanged &= all((runtime_root / f["path"]).is_file()
                                           and digest(runtime_root / f["path"]) == f["sha256"] for f in manifest["files"])
        # Public output must never inherit sealed files, caches or conversation state.
        with bundle_session(manifest_path, plan["runtime"], min(timeout, deadline - time.monotonic()),
                            prepare=lambda root: _copy_assets([a for a in plan["assets"] if a["visibility"] == "public"], root)) as (run, runtime_root):
            for example in plan["public_examples"]:
                output, error = run_input(run, example["input"])
                captured = []
                if not error:
                    try:
                        captured = _capture_artifacts(output, plan["output_artifacts"], runtime_root,
                                                      vault / "public-artifacts" / str(len(public)))
                    except (OSError, ValueError, RuntimeError) as failure:
                        error = str(failure)
                public.append({**example, "output": output, "error": error, "artifacts": captured})
            manifest = _read_json(manifest_path)
            source_unchanged &= all((runtime_root / f["path"]).is_file()
                                    and digest(runtime_root / f["path"]) == f["sha256"] for f in manifest["files"])
    except (OSError, RuntimeError, ValueError) as failure:
        stop = str(failure)
        failure_category = _failure_category(failure)
        for values in recorded:
            for case in cases:
                if case["id"] not in values:
                    values[case["id"]] = None
                    errors[case["id"]] = stop
    record_outputs()
    # All generation finishes before any grading request is made.
    results = []
    for case, first, again in zip(cases, outputs, repeated, strict=True):
        checks = [_check_assertion(a, record["output"])
                  for record in (first, again) for a in case["deterministic_assertions"]]
        repeat_policy = case.get("repeat_policy", plan["repeat_policy"])
        if repeat_policy == "exact":
            checks.append({"type": "exact_repeat", "pass": _json_equal(first["output"], again["output"])})
        relation = case.get("metamorphic")
        if relation:
            for repetition, (collection, observed) in enumerate(((outputs, first), (repeated, again))):
                try:
                    other = next(o for o in collection if o["case_id"] == relation["case_id"])
                    values = []
                    for record in (observed, other):
                        value = _path_value(record["output"], relation["path"])
                        for artifact in case_artifacts.get(record["case_id"], [[], []])[repetition]:
                            if artifact["output_path"] == relation["path"]:
                                value = artifact["sha256"]
                        values.append(value)
                    equal = _json_equal(*values)
                    passed = other["case_id"] not in errors and equal == (relation["relation"] == "equal")
                except (KeyError, IndexError, TypeError):
                    passed = False
                checks.append({"type": "metamorphic", "pass": passed})
        semantic = {"status": "NOT_REQUIRED"}
        if case["semantic_criteria"] and case["id"] not in errors:
            semantic = _judge(judge, {
                "stage": "quality", "case_id": case["id"], "kind": case["kind"], "input": case["input"],
                "replica_output": first["output"], "repeated_output": again["output"],
                "semantic_criteria": case["semantic_criteria"], "reference": case.get("reference"),
                "artifacts": case_artifacts.get(case["id"], []),
                "instruction": (
                    "Assess every criterion on BOTH outputs. Prose may vary; facts, grounding and required behavior must hold. "
                    "For file outputs, inspect the actual preserved artifacts, not merely their filenames or existence. "
                    "If the required modality or contents cannot be inspected, return pass=false and explain that limitation."
                ),
            }, timeout=min(timeout, deadline - time.monotonic()))
        results.append({
            "case_id": case["id"], "kind": case["kind"], "criterion_ids": case.get("criterion_ids", []),
            "checks": checks, "semantic": semantic, "error": errors.get(case["id"]),
            "pass": case["id"] not in errors and all(c["pass"] for c in checks)
                    and semantic["status"] in {"PASSED", "NOT_REQUIRED"},
        })
    _write_jsonl(vault / "results.jsonl", results)
    by_kind = {}
    for result in results:
        group = by_kind.setdefault(result["kind"], {"passed": 0, "total": 0})
        group["passed"] += int(result["pass"])
        group["total"] += 1
    summary = {
        "schema_version": "replica-evaluation-summary/v1",
        "status": "PASSED" if all(r["pass"] for r in results) else "FAILED",
        "passed": sum(r["pass"] for r in results), "total": len(results), "by_kind": by_kind,
        "test_suite_sha256": digest(vault / "tests.json"),
        "outputs_sha256": digest(vault / "replica_outputs.jsonl"),
        "results_sha256": digest(vault / "results.jsonl"),
        "repeated_outputs_sha256": digest(vault / "repeated_outputs.jsonl"),
        "execution_records_sha256": digest(vault / "execution-records.jsonl"),
        "elapsed_seconds": time.monotonic() - started, "stop_reason": stop,
        "failure_category": failure_category,
        "dependencies": dependencies,
        "source_unchanged": source_unchanged,
        "unjudged": sum(r["semantic"]["status"] == "NOT_EVALUATED" for r in results),
    }
    _write_json(vault / "artifact-receipts.json", {"input_assets": assets, "output_artifacts": output_artifacts})
    return summary, {"public_examples": public, "assets": assets, "outputs": outputs,
                     "repeated_outputs": repeated, "artifacts": case_artifacts,
                     "execution_records": executions, "dependencies": dependencies}


def _failure_category(error: Exception) -> str:
    if isinstance(error, TimeoutError) or "cost budget" in str(error):
        return "budget_exhausted"
    if isinstance(error, PermissionError):
        return "access_missing"
    if isinstance(error, FileNotFoundError):
        return "data_missing" if "asset" in str(error) else "environment_error"
    if isinstance(error, OSError) or "ModuleNotFoundError" in str(error):
        return "environment_error"
    return "implementation_defect"


def _evaluate_agent_bundle(registry_path: Path, claim_id: str, *, semantic_judge: Callable | None = None,
                          judge_identity: str = "not_configured", judge_mode: str = "same_session") -> dict[str, Any]:
    from .agent_harness import (
        _claim_record, _read_registry, _replace_registry, _validate_implementation_result,
        _bundle_dependency_level, _selected_scenario,
    )
    if not isinstance(judge_identity, str) or not judge_identity.strip() or judge_mode not in {"same_session", "independent"}:
        raise ValueError("final evaluation requires a named judge and an explicit independence label")
    registry = _read_registry(registry_path)
    claim = _claim_record(registry, claim_id)
    root = registry_path.parent.resolve()
    if claim.get("status") != "IMPLEMENTATION_READY":
        raise ValueError("final bundle evaluation requires IMPLEMENTATION_READY")
    _validate_implementation_result(root, claim)
    _validate_history(root, claim)
    prepared = claim.get("bundle_evaluation")
    if prepared is None:
        raise ValueError("prepare the second-pass evaluation before submitting the bundle")
    plan_path = root / prepared["plan_path"]
    if not plan_path.resolve().is_relative_to(root / "evaluator-vault") or digest(plan_path) != prepared["plan_sha256"]:
        raise ValueError("bundle evaluation plan hash mismatch")
    if prepared.get("public_runtime_contract_path"):
        public_contract_path = root / prepared["public_runtime_contract_path"]
        if (not public_contract_path.resolve().is_relative_to(root / "claims" / claim_id)
                or digest(public_contract_path) != prepared["public_runtime_contract_sha256"]):
            raise ValueError("public runtime contract hash mismatch")
    plan = _read_json(plan_path)
    if plan["claim_sha256"] != digest(root / claim["claim_payload_path"]) or (
        plan.get("sealed_claim_sha256") is not None
        and plan["sealed_claim_sha256"] != digest(root / claim["sealed_claim_path"])
    ):
        raise ValueError("evaluation no longer matches the immutable claim")
    manifest_path = root / claim["implementation_result"]["candidate_path"]
    manifest_sha256 = digest(manifest_path)
    attempts = claim.setdefault("bundle_submissions", [])
    if any(a["status"] == "RUNNING" for a in attempts):
        raise ValueError("the existing sealed evaluation has not finished")
    if len(attempts) >= MAX_SUBMISSIONS:
        raise ValueError("three sealed submissions are exhausted")
    if any(a["candidate_sha256"] == manifest_sha256 for a in attempts):
        raise ValueError("the same candidate cannot be resubmitted to sealed tests")
    # The frozen evaluation budget covers all submissions, including implementation review.
    if plan["budget"]["time_limit_seconds"] is not None:
        plan = deepcopy(plan)
        plan["budget"]["time_limit_seconds"] -= sum(a.get("elapsed_seconds", 0) for a in attempts)
        if plan["budget"]["time_limit_seconds"] <= 0:
            raise ValueError("the frozen evaluation time budget is exhausted")
    number = len(attempts) + 1
    vault = plan_path.parent / f"attempt-{number:03d}"
    lock = plan["test_lock"]
    if lock is not None:
        source_tests = plan_path.parent / "tests.json"
        suite = _read_json(source_tests)
        if not _is_valid_lock(lock, digest(source_tests), len(suite["cases"])):
            raise ValueError("frozen bundle tests changed")
    vault.mkdir(exist_ok=False)
    if lock is not None:
        freeze_test_suite(source_tests, vault)
    copy_bundle(manifest_path, vault / "submitted-implementation")
    shutil.copyfile(root / claim["operator"]["artifact_namespace"] / "execution-state.json", vault / "submitted-execution-state.json")
    attempts.append({"attempt": number, "candidate_sha256": manifest_sha256,
                     "plan_sha256": prepared["plan_sha256"], "started_at": utc_now(), "status": "RUNNING"})
    _replace_registry(registry_path, registry)
    if lock is None or plan["runtime"] is None:
        summary = {"schema_version": "replica-evaluation-summary/v1", "status": "NOT_EVALUATED",
                   "passed": 0, "total": lock["case_count"] if lock else 0, "by_kind": {},
                   "stop_reason": "research_gap", "elapsed_seconds": 0, "source_unchanged": True,
                   "unjudged": 0, "failure_category": "research_gap"}
        evidence = {"public_examples": [], "assets": [], "outputs": []}
    else:
        summary, evidence = _evaluate_cases(vault, plan, manifest_path, semantic_judge)
    summary.update({"judge_identity": judge_identity, "judge_mode": judge_mode,
                    "candidate_sha256": manifest_sha256, "plan_sha256": prepared["plan_sha256"]})
    _write_json(vault / "evaluation-summary.json", summary)
    summary_sha256 = digest(vault / "evaluation-summary.json")
    manifest = _read_json(manifest_path)
    claim_payload = _read_json(root / claim["claim_payload_path"])
    review = {"status": "NOT_EVALUATED", "reason": "No successfully executed candidate outputs to inspect."}
    review_started = time.monotonic()
    if any(o["output"] is not None for o in evidence["outputs"]):
        review = _judge(semantic_judge, {
            "stage": "implementation_review", "manifest": manifest,
            "files": {r["path"]: (manifest_path.parent / r["path"]).read_text(errors="replace")
                      for r in manifest["files"] if (manifest_path.parent / r["path"]).stat().st_size <= 200_000},
            "unreviewed_files": [r["path"] for r in manifest["files"] if (manifest_path.parent / r["path"]).stat().st_size > 200_000],
            "public_contract": plan["acceptance_criteria"],
            "workflow": claim_payload["second_pass"].get("workflow"),
            "research_findings": claim_payload["second_pass"].get("findings"),
            "selected_scenario": {key: value for scenario in claim_payload["second_pass"]["replication_contract"]
                                  if scenario["id"] == plan["scenario_id"] for key, value in scenario.items() if key not in {"tests", "evaluation"}},
            "model_runtime": claim_payload.get("model_runtime"),
            "evaluation_runtime": plan["runtime"],
            "effective_dependency_level": _bundle_dependency_level(
                claim_payload, _selected_scenario(claim_payload), manifest["dependencies"]),
            "observed_dependencies": evidence.get("dependencies", []),
            "execution_records": evidence.get("execution_records", []),
            "preserved_artifacts": evidence.get("artifacts", {}),
            "evaluation_cases": _read_json(vault / "tests.json")["cases"],
            "outputs": evidence["outputs"],
            "repeated_outputs": evidence.get("repeated_outputs", []),
            "instruction": (
                "Inspect the executed source and evidence for full workflow fidelity, real required dependencies, "
                "input-driven behavior, reuse and novel-input representativeness. Reject fixture/company/test branches, "
                "a target company's own core API posing as a replica, stubs and answer leakage. "
                "Check that novel inputs materially differ from development examples, not just names or numbers. "
                "Inspect preserved_artifacts at their absolute paths for storage and saved-sink evidence. "
                "The harness supplies the HTTP port_argument when launching the manifest command; it is not a missing implementation argument. "
                "Use effective_dependency_level after the explicit model_runtime overlay: the selected native model CLI can make an oss_only research route commercial_api; all other research requirements remain unchanged. "
                "Distinguish application source from third-party dependencies. Assess vendored public binaries like installed public packages using provenance, observed versions and actual execution evidence; an unreviewed binary alone is not an automatic failure. "
                "If fidelity-critical application source is unreviewed, do not assume that it implements the contract. "
                "A manifest or Builder pass claim alone is not evidence. Return pass=false when evidence is insufficient."
            ),
        }, timeout=min(plan["timeout_seconds"],
                       (plan["budget"]["time_limit_seconds"] or float("inf")) - summary["elapsed_seconds"]))
    review.update({"judge_identity": judge_identity, "judge_mode": judge_mode,
                   "candidate_sha256": manifest_sha256, "results_sha256": summary.get("results_sha256")})
    _write_json(vault / "implementation-review.json", review)
    # Recheck both the original and the executed copy before binding the public artifact.
    _validate_implementation_result(root, claim)
    if digest(plan_path) != prepared["plan_sha256"] or digest(vault / "evaluation-summary.json") != summary_sha256:
        raise ValueError("evaluation contract or summary changed during grading")
    if lock is not None:
        expected_files = {"tests.json": lock["sha256"]}
        expected_files.update({name: summary[key] for name, key in (
            ("replica_outputs.jsonl", "outputs_sha256"), ("results.jsonl", "results_sha256"),
            ("repeated_outputs.jsonl", "repeated_outputs_sha256"), ("execution-records.jsonl", "execution_records_sha256"),
        ) if key in summary})
        if any(digest(vault / name) != expected for name, expected in expected_files.items()):
            raise ValueError("sealed evaluation evidence changed during grading")
        receipts_path = vault / "artifact-receipts.json"
        artifact_receipts = _read_json(receipts_path)["output_artifacts"] if receipts_path.exists() else []
        artifact_receipts += [a for e in evidence["public_examples"] for a in e["artifacts"]]
        for receipt in artifact_receipts:
            artifact = Path(receipt["path"])
            if not artifact.resolve().is_relative_to(vault.resolve()) or artifact.is_symlink() or digest(artifact) != receipt["sha256"]:
                raise ValueError("generated artifact changed during grading")
    public_assets = []
    for asset in plan["assets"]:
        if asset["visibility"] == "public":
            source = Path(asset["source"])
            if source.is_file() and not source.is_symlink() and digest(source) == asset["sha256"]:
                public_assets.append(asset)
    assessment = assess_bundle_execution(
        plan, summary, review,
        has_outputs=any(o["output"] is not None for o in evidence["outputs"]),
        public_example_passed=bool(evidence["public_examples"]) and not any(e["error"] for e in evidence["public_examples"]),
        public_assets_available=len(public_assets) == sum(a["visibility"] == "public" for a in plan["assets"]),
    )
    reproduction = assessment["reproduction_status"]
    resources = unknown_resources()
    resources["measurements"] = [m for m in resources["measurements"] if m["phase"] == "execution"]
    resources["measurements"].append(measurement("elapsed_time", "final_evaluation", summary["elapsed_seconds"] + time.monotonic() - review_started,
                                                "seconds", "Measured with a monotonic clock; includes runtime waiting."))
    if (vault / "results.jsonl").exists():
        for line in (vault / "results.jsonl").read_text().splitlines():
            resources["measurements"].extend(json.loads(line)["semantic"].get("resources", {}).get("measurements", []))
    resources["measurements"].extend(review.get("resources", {}).get("measurements", []))
    state_path = root / claim["operator"]["artifact_namespace"] / "execution-state.json"
    state = _read_json(state_path)
    development = [{"submission": number, "correction_number": a["correction_number"], "decision": a["decision"],
                    "resources": a.get("resources", unknown_resources()),
                    "stop_reason": (a.get("stop_reason") or {}).get("category")}
                   for a in state["attempts"]]
    for attempt in attempts[:-1]:
        prior_result = _read_json(root / attempt["public_run_dir"] / "replica-result.json") if attempt.get("public_run_dir") else {}
        development = [a for a in prior_result.get("development_attempts", []) if a.get("submission", attempt["attempt"]) == attempt["attempt"]] + development
    _write_json(vault / "completion-assessment.json", assessment)
    public_root = root / "final-results" / "runs" / claim_id
    public_root.mkdir(parents=True, exist_ok=True)
    public_dir = public_root / f"attempt-{number:03d}-{manifest_sha256[:12]}"
    public_dir.mkdir(exist_ok=False)
    copy_bundle(manifest_path, public_dir / "implementation")
    # Only redistributable public assets and public examples cross this boundary.
    _copy_assets(public_assets, public_dir / "implementation")
    replica = {
        "schema_version": "replica-bundle/v1", "claim_id": claim_id, "scenario_id": plan["scenario_id"],
        "manifest": "implementation/manifest.json", "manifest_sha256": manifest_sha256,
        "runtime": plan["runtime"], "timeout_seconds": plan["timeout_seconds"],
        "assets": [{k: v for k, v in a.items() if k != "source"} for a in public_assets],
        "output_artifacts": plan["output_artifacts"],
    }
    _write_json(public_dir / "replica.json", replica)
    researched = _selected_scenario(_sealed_claim(root, claim)) or {}
    spec = {
        "schema_version": "replica-spec/v1", "input_contract": manifest["input_contract"],
        "output_contract": manifest["output_contract"], "acceptance_criteria": plan["acceptance_criteria"],
    }
    # The experience commands read the evidence level and public profile from the published run.
    if researched.get("evidence_level") in {"direct", "public", "claim_only"}:
        spec["evidence_policy"] = {"level": researched["evidence_level"]}
        if "experience" in researched:
            profile = validate_experience_profile(deepcopy(researched["experience"]))
            if profile["comparison"]["evidence_level"] != researched["evidence_level"]:
                raise ValueError("experience evidence level does not match the selected scenario")
            _write_json(public_dir / "experience.json", profile)
    _write_json(public_dir / "replica-spec.json", spec)
    public_examples = []
    for index, example in enumerate(evidence["public_examples"]):
        published = {key: deepcopy(value) for key, value in example.items() if key != "artifacts"}
        published["error"] = "public example failed; details are evaluator-only" if example["error"] else None
        for artifact in example["artifacts"]:
            source = Path(artifact["path"])
            destination = public_dir / "artifacts" / str(index) / source.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            published["output"] = _replace_output_path(published["output"], artifact["output_path"],
                                                       destination.relative_to(public_dir).as_posix())
        public_examples.append(published)
    _write_json(public_dir / "public-examples.json", public_examples)
    # Detailed judge reasons and per-case marks may reveal sealed expectations.
    public_assessment = {k: v for k, v in assessment.items() if k not in {"implementation_review", "evaluation"}}
    public_assessment["implementation_review"] = {k: review[k] for k in ("status", "judge_identity", "judge_mode")}
    public_assessment["evaluation"] = {k: summary[k] for k in (
        "status", "passed", "total", "by_kind", "judge_identity", "judge_mode", "candidate_sha256", "plan_sha256",
    )}
    _write_json(public_dir / "completion-assessment.json", public_assessment)
    public_files = [p for p in public_dir.rglob("*") if p.is_file()]
    result = {
        "schema_version": "replica-bundle-result/v1", "claim_id": claim_id, "scenario_id": plan["scenario_id"],
        "status": summary["status"], "reproduction_status": reproduction,
        "candidate_sha256": manifest_sha256, "plan_sha256": prepared["plan_sha256"],
        "attempt": number, "max_attempts": MAX_SUBMISSIONS,
        "evaluation": public_assessment["evaluation"], "resources": resources, "development_attempts": development,
        "dependencies": summary.get("dependencies", []),
        "stop_reason": ("evaluated" if summary["status"] == "PASSED" else
                        "execution_blocked" if summary["stop_reason"] else "quality_or_evaluation_gap"),
        "failure_category": summary["failure_category"] or (None if reproduction == "reproduced" else "quality_gap"),
        "artifacts": {p.relative_to(public_dir).as_posix(): digest(p) for p in public_files},
        "private_evidence": {p.relative_to(vault).as_posix(): digest(p) for p in vault.rglob("*") if p.is_file()},
    }
    _write_json(public_dir / "replica-result.json", result)
    attempts[-1].update({"status": summary["status"], "finished_at": utc_now(),
                         "reproduction_status": reproduction, "public_run_dir": public_dir.relative_to(root).as_posix(),
                         "elapsed_seconds": summary["elapsed_seconds"] + time.monotonic() - review_started,
                         "result_sha256": digest(public_dir / "replica-result.json")})
    claim["final_result"] = {
        "schema_version": "replica-agent-bundle-result/v1", "status": summary["status"],
        "reproduction_status": reproduction, "candidate_sha256": manifest_sha256,
        "public_run_dir": public_dir.relative_to(root).as_posix(),
        "vault_dir": vault.relative_to(root).as_posix(),
        "result_sha256": digest(public_dir / "replica-result.json"),
    }
    claim["status"] = "RESULT_SUCCESS" if reproduction == "reproduced" else "RESULT_FAILED"
    _replace_registry(registry_path, registry)
    return registry


def evaluate_agent_bundle(registry_path: Path, claim_id: str, **kwargs) -> dict[str, Any]:
    """Preserve an interrupted submission instead of leaving it silently RUNNING."""
    from .agent_harness import _claim_record, _read_registry, _replace_registry
    before = len(_claim_record(_read_registry(registry_path), claim_id).get("bundle_submissions", []))
    started = time.monotonic()
    try:
        return _evaluate_agent_bundle(registry_path, claim_id, **kwargs)
    except BaseException:
        registry = _read_registry(registry_path)
        claim = _claim_record(registry, claim_id)
        attempts = claim.get("bundle_submissions", [])
        if len(attempts) > before and attempts[-1]["status"] == "RUNNING":
            attempts[-1].update({"status": "INTERRUPTED", "finished_at": utc_now(),
                                 "elapsed_seconds": time.monotonic() - started})
            claim["status"] = "EVALUATION_INTERRUPTED"
            _replace_registry(registry_path, registry)
        raise


def retry_agent_bundle(registry_path: Path, claim_id: str) -> dict[str, Any]:
    """Reopen the same pair while retaining frozen research, budgets and all prior artifacts."""
    from .agent_execution import create_agent_execution_state, load_agent_execution_state_file, _write_state
    from .agent_harness import _claim_record, _read_registry, _replace_registry, _validate_implementation_result, _validate_implementation_bundle
    registry = _read_registry(registry_path)
    claim = _claim_record(registry, claim_id)
    packaging_retry = claim["status"] == "EXECUTION_SUCCESS" and "implementation_result" not in claim
    if not packaging_retry and claim["status"] not in {"RESULT_FAILED", "EVALUATION_INTERRUPTED"}:
        raise ValueError("only a failed or interrupted bundle evaluation can reopen the same pair")
    root = registry_path.parent.resolve()
    payload = _read_json(root / claim["claim_payload_path"])
    if packaging_retry:
        candidate_path = root / claim["execution_result"]["candidate_path"]
        if candidate_path != root / "claims" / claim_id / "builder" / "implementation" / "manifest.json":
            raise ValueError("packaging retry requires the bound implementation manifest")
        if len(claim.get("packaging_retries", [])) >= 2:
            raise ValueError("two packaging retries are exhausted")
        try:
            _validate_implementation_bundle(root, claim_id, candidate_path, payload)
        except ValueError as error:
            # Only packaging residue is recoverable here; no unchecked paths or files are copied.
            if str(error) != "Terra implementation bundle contains undeclared files":
                raise
        else:
            raise ValueError("a valid package should be finalized, not retried")
    else:
        _validate_implementation_result(root, claim)
        candidate_path = root / claim["implementation_result"]["candidate_path"]
    if claim["status"] == "RESULT_FAILED":
        validate_bundle_result(root, claim)
    attempts = claim.get("bundle_submissions", [])
    if len(attempts) >= MAX_SUBMISSIONS:
        raise ValueError("three sealed submissions are exhausted")
    plan = _read_json(root / claim["bundle_evaluation"]["plan_path"])
    limit = plan["budget"]["time_limit_seconds"]
    if limit is not None and sum(a.get("elapsed_seconds", 0) for a in attempts) >= limit:
        raise ValueError("the frozen evaluation time budget is exhausted")
    state_path = root / claim["operator"]["artifact_namespace"] / "execution-state.json"
    previous, state_hash = load_agent_execution_state_file(state_path, payload)
    if state_hash != claim["execution_result"]["execution_state_sha256"]:
        raise ValueError("retry cannot change the bound development terminal")
    if "started_at" not in previous:
        raise ValueError("legacy development state has no frozen budget origin; prepare a new experiment")
    resources = previous.get("prior_resources", []) + [a.get("resources", unknown_resources()) for a in previous["attempts"]]
    if "budget" in previous and budget_stop(previous["budget"], previous["started_at"], resources):
        raise ValueError("the frozen development budget is exhausted or unverifiable")
    archive_name = (f"packaging-{len(claim.get('packaging_retries', [])) + 1:03d}"
                    if packaging_retry else f"development-{len(attempts):03d}")
    archive = root / "evaluator-vault" / claim_id / archive_name
    archive.mkdir(exist_ok=False)
    _write_json(archive / "claim-binding.json", claim)
    # Archive executable artifacts and control metadata, never relay semantic peer messages.
    shutil.copyfile(state_path, archive / "execution-state.json")
    copy_bundle(candidate_path, archive / "implementation")
    development_archive = {
        "path": archive.relative_to(root).as_posix(),
        "artifacts": {p.relative_to(archive).as_posix(): digest(p) for p in archive.rglob("*") if p.is_file()},
    }
    if packaging_retry:
        claim.setdefault("packaging_retries", []).append({"development_archive": development_archive,
                                                         "rejection": "undeclared_files",
                                                         "recorded_at": utc_now()})
    else:
        attempts[-1]["development_archive"] = development_archive
    state = create_agent_execution_state(claim=payload, claim_id=claim_id,
                                        operator_agent_id=claim["operator"]["agent_id"],
                                        builder_agent_id=claim["builder"]["agent_id"], pair_nonce=claim["smoke"]["nonce"])
    state["started_at"] = previous.get("started_at", state["started_at"])
    state["prior_resources"] = resources
    _write_state(state_path, state, new=False)
    for field in ("execution_result", "implementation_result", "final_result"):
        claim.pop(field, None)
    claim["status"] = "READY_FOR_PROTOCOL"
    claim["continuity"].update({"phase": "READY", "completed_rounds": [], "next_round": 0,
                                "correction_count": 0, "terminal_state": None, "failure": None,
                                "operator_status": "NOT_STARTED", "builder_status": "NOT_STARTED"})
    claim["continuity"].pop("finished_at", None)
    registry["status"] = "READY_FOR_PROTOCOL"
    registry["replica_agent"]["status"] = "READY_FOR_PROTOCOL"
    _replace_registry(registry_path, registry)
    return registry


def validate_bundle_result(root: Path, claim: dict[str, Any]) -> None:
    from .agent_harness import _validate_implementation_result
    _validate_implementation_result(root, claim)
    _validate_history(root, claim)
    final = claim["final_result"]
    public_dir, vault = root / final["public_run_dir"], root / final["vault_dir"]
    if (not public_dir.resolve().is_relative_to(root / "final-results" / "runs")
            or not vault.resolve().is_relative_to(root / "evaluator-vault")
            or digest(public_dir / "replica-result.json") != final["result_sha256"]):
        raise ValueError("bundle final result binding changed")
    result = _read_json(public_dir / "replica-result.json")
    for directory, artifacts in ((public_dir, result["artifacts"]), (vault, result["private_evidence"])):
        _validate_artifacts(directory, artifacts, "bundle final")
    if (result["claim_id"] != claim["claim_id"] or result["reproduction_status"] != final["reproduction_status"]
            or result["candidate_sha256"] != claim["implementation_result"]["candidate_sha256"]
            or (claim["status"] == "RESULT_SUCCESS") != (result["reproduction_status"] == "reproduced")):
        raise ValueError("bundle final status binding changed")


def run_published_bundle(run_dir: Path, runtime_input: Any, *, allow_model_adapter: bool = False,
                         input_assets: dict[str, str] | None = None, session: bool = False,
                         state_dir: Path | None = None) -> Any:
    replica = _read_json(run_dir / "replica.json")
    result = _read_json(run_dir / "replica-result.json")
    _validate_artifacts(run_dir, result["artifacts"], "published bundle")
    manifest_path = run_dir / replica["manifest"]
    if digest(manifest_path) != replica["manifest_sha256"]:
        raise ValueError("published manifest hash mismatch")
    manifest = _read_json(manifest_path)
    if manifest["dependency_level"] != "oss_only" and not allow_model_adapter:
        raise ValueError("this bundle uses external dependencies; enable --use-model-adapter to execute it")
    if input_assets is not None and (not isinstance(input_assets, dict) or any(
        not safe_relative(name) or not isinstance(source, str) or not source
        for name, source in input_assets.items()
    )):
        raise ValueError("input assets must map safe runtime-relative paths to local source files")
    replacements = input_assets or {}
    assets = [{**a, "source": str(manifest_path.parent / a["path"])} for a in replica["assets"] if a["path"] not in replacements]
    assets.extend({"path": name, "source": source, "sha256": digest(Path(source))} for name, source in replacements.items())
    outputs = []
    new_assets = [a for a in assets if a["path"] in replacements]
    with bundle_session(manifest_path, replica["runtime"], replica["timeout_seconds"],
                        prepare=lambda root: _copy_assets(assets, root), workspace=state_dir,
                        resume_prepare=lambda root: _copy_assets(new_assets, root)) as (run, root):
        for value in runtime_input if session else [runtime_input]:
            output = run(value)
            if replica["output_artifacts"]:
                destination = Path(tempfile.mkdtemp(prefix="replica-output-"))
                for artifact in _capture_artifacts(output, replica["output_artifacts"], root, destination):
                    output = _replace_output_path(output, artifact["output_path"], artifact["path"])
            outputs.append(output)
    return outputs if session else outputs[0]
