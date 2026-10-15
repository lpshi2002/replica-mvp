"""Final evaluation of a web-app Replica: run its frozen demo plan and bind the result to the claim.

The plan was frozen from pass-2 research before implementation and is public;
nothing is sealed. The result directory is published under final-results/runs.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .resources import utc_now
from .web_demo import run_web_demo, web_reproduction_status, validate_demo_plan
from .web_checkpoint import evaluator_version
from .model_calls import summarize_receipts, summarize_receipt_directories


WEB_RESULT_SCHEMA = "replica-agent-web-demo-result/v1"
MAX_WEB_SUBMISSIONS = 3


def register_development_run(registry_path: Path, claim_id: str, source: Path) -> dict[str, Any]:
    """Import existing development receipts without touching the implementation or verdict."""
    from .agent_harness import _read_registry, _claim_record, _replace_registry
    registry = _read_registry(registry_path)
    claim = _claim_record(registry, claim_id)
    source = source.resolve()
    result_path = source / "demo-result.json"
    result = json.loads(result_path.read_text())
    if result.get("claim_id") != claim_id or not (source / "receipts").is_dir():
        raise ValueError("development result must identify this claim and contain receipts")
    result_hash = _digest(result_path)
    records = claim.setdefault("development_evaluations", [])
    found = next((r for r in records if r["result_sha256"] == result_hash), None)
    if found:
        return found
    target = registry_path.parent / claim["namespace"] / "development-evaluations" / result_hash[:16]
    if target.exists():
        raise ValueError("unregistered development evidence already exists; inspect before retrying import")
    if any(p.is_symlink() for p in (source / "receipts").rglob("*")):
        raise ValueError("development receipts must not contain symlinks")
    target.mkdir(parents=True)
    shutil.copyfile(result_path, target / "demo-result.json")
    shutil.copytree(source / "receipts", target / "receipts")
    record = {"path": target.relative_to(registry_path.parent).as_posix(), "result_sha256": result_hash,
              "source": str(source), "registered_at": utc_now()}
    records.append(record)
    _replace_registry(registry_path, registry)
    return record


def cumulative_web_costs(root: Path, claim: dict[str, Any]) -> dict[str, Any]:
    directories = []
    sources = []
    for record in [*claim.get("bundle_submissions", []), *claim.get("development_evaluations", [])]:
        name = record.get("public_run_dir") or record.get("path")
        if not name:
            continue
        directory = root / name
        if not directory.resolve().is_relative_to(root.resolve()):
            raise ValueError("cost evidence escaped the run directory")
        if record.get("result_sha256") and _digest(directory / "demo-result.json") != record["result_sha256"]:
            raise ValueError("cost evidence result changed")
        directories.append(directory / "receipts")
        sources.append(name)
    summary = summarize_receipt_directories(directories)
    return {"phases": summary["phases"], "sources": sources,
            "unique_calls": sum(p["calls"] for p in summary["phases"].values()), "unique_receipts": len(summary["calls"]),
            "coverage": "All registered evaluation and development-demo segments; agent session usage is reported separately. Unregistered development calls are unknown, not zero."}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def review_context(root: Path, claim: dict[str, Any]) -> dict[str, Any]:
    """Public research the code review checks the implementation against."""
    from .agent_harness import _selected_scenario
    payload = json.loads((root / claim["claim_payload_path"]).read_text(encoding="utf-8"))
    selected = _selected_scenario(payload)
    return {
        "workflow_steps": claim["web_demo"]["scope"]["steps"],
        "acceptance_criteria": payload.get("acceptance_criteria"),
        "scenario": {key: selected.get(key) for key in ("input", "output", "boundaries", "out_of_scope",
                                                       "self_sufficiency", "evidence_level")},
        "implementation_path": ((payload["second_pass"].get("findings") or {}).get("impl_path") or {}).get("note"),
    }


def _run_swaps(case: dict[str, Any]) -> list[tuple[str, str]]:
    """This run's drawn values paired with the plan's example values, longest first."""
    replacements = (case.get("instance") or {}).get("replacements") or []
    pairs = [(r["to"], r["from"]) for r in replacements
             if isinstance(r, dict) and isinstance(r.get("to"), str) and r["to"] and isinstance(r.get("from"), str)]
    return sorted(pairs, key=lambda pair: len(pair[0]), reverse=True)


def _in_plan_terms(text: Any, swaps: list[tuple[str, str]]) -> Any:
    """Write a free-text reason with the plan's example values in place of this run's values."""
    if not isinstance(text, str):
        return text
    for drawn, example in swaps:
        text = text.replace(drawn, example)
    return text


def write_retry_feedback(root: Path, claim: dict[str, Any], directory: Path) -> Path | None:
    """Give the implementer each expectation's status and reason; no screenshots, page text or run values.

    Reasons are free text from checks, the judge and the code review, so every value the run drew
    is written back as the plan's example value. A drawn value the generator did not list as a
    replacement cannot be recognized here.
    """
    final = claim.get("final_result") or {}
    if final.get("schema_version") != WEB_RESULT_SCHEMA:
        return None
    result = json.loads((root / final["public_run_dir"] / "demo-result.json").read_text(encoding="utf-8"))
    plan = json.loads((root / final["public_run_dir"] / "demo-plan.json").read_text(encoding="utf-8"))
    # Describe expectations as the plan does; this run's drawn values are not part of the feedback.
    described = {(case["id"], item["id"]): item["description"] for case in plan["cases"] for item in case["expectations"]}
    swaps = {case["case_id"]: _run_swaps(case) for case in result["cases"]}
    all_swaps = sorted({pair for pairs in swaps.values() for pair in pairs}, key=lambda pair: len(pair[0]), reverse=True)
    review = result["code_review"]
    feedback = {
        "schema_version": "replica-web-retry-feedback/v1", "attempt": len(claim["bundle_submissions"]),
        "reproduction_status": final["reproduction_status"],
        "cases": [{
            "case_id": case["case_id"], "execution_status": case["execution_status"],
            "stop_reason": _in_plan_terms(case.get("stop_reason"), swaps[case["case_id"]]),
            "expectations": [{"id": item["id"], "description": described[(case["case_id"], item["id"])],
                              "status": item["status"], "reason": _in_plan_terms(item["reason"], swaps[case["case_id"]])}
                             for item in case["expectations"]],
        } for case in result["cases"]],
        "code_review": {
            "status": review.get("status"), "reason": _in_plan_terms(review.get("reason"), all_swaps),
            "findings": [{key: _in_plan_terms(value, all_swaps) for key, value in finding.items()}
                         if isinstance(finding, dict) else finding for finding in review.get("findings") or []],
        },
        "uncovered_steps": result["scope"].get("uncovered_steps"),
        "note": ("Fix the behavior these reasons describe for any input in scope. The next evaluation draws new "
                 "values for every case with a variation rule and reviews the code again; branches for earlier values will not pass."),
    }
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"retry-feedback-{feedback['attempt']:03d}.json"
    path.write_text(json.dumps(feedback, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def interrupted_attempt(root: Path, attempt: dict[str, Any]) -> bool:
    if attempt.get("status") == "INTERRUPTED" or attempt.get("environment_interrupted"):
        return True
    directory = attempt.get("public_run_dir")
    if not directory:
        return False
    path = root / directory
    if not path.resolve().is_relative_to((root / "final-results" / "runs").resolve()):
        raise ValueError("evaluation directory escaped public runs")
    return any(c.get("usage_limit") or c["status"] == "timeout"
               for c in summarize_receipts(path / "receipts")["calls"])


def submission_count(root: Path, claim: dict[str, Any]) -> int:
    return len({a["candidate_sha256"] for a in claim.get("bundle_submissions", [])
                if not interrupted_attempt(root, a)})


def evaluate_web_bundle(registry_path: Path, claim_id: str, *, provider: str | None = None, model: str | None = None,
                        tester: Callable | None = None, judge: Callable | None = None,
                        browser_factory: Callable | None = None, instance_generator: Callable | None = None,
                        reviewer: Callable | None = None, recovery_reason: str | None = None,
                        clear_limit: bool = False, phase_models: dict[str, str] | None = None,
                        tester_mode: str = "plan", cache_ttl: str | None = "5m",
                        stable_prefix: bool = False, input_cases_from: Path | None = None) -> dict[str, Any]:
    from .agent_harness import (
        PUBLIC_RESULTS_ROOT, _claim_record, _read_registry, _relative_path, _replace_registry,
        _validate_implementation_result,
    )
    from .bundle_evaluation import _validate_history
    registry = _read_registry(registry_path)
    claim = _claim_record(registry, claim_id)
    root = registry_path.parent.resolve()
    web = claim.get("web_demo")
    if not isinstance(web, dict):
        raise ValueError("this claim has no frozen demo plan")
    attempts = claim.setdefault("bundle_submissions", [])
    recovering = bool(recovery_reason) or claim.get("status") == "EVALUATION_INTERRUPTED"
    if input_cases_from is not None and recovering:
        raise ValueError("comparison inputs cannot replace a recovery checkpoint")
    if claim.get("status") != "IMPLEMENTATION_READY" and not recovering:
        raise ValueError("final web evaluation requires IMPLEMENTATION_READY or explicit recovery")
    if any(a["status"] == "RUNNING" for a in attempts):
        raise ValueError("the existing web evaluation has not finished")
    _validate_implementation_result(root, claim)
    _validate_history(root, claim)
    plan_path = root / web["plan_path"]
    if _digest(plan_path) != web["plan_sha256"]:
        raise ValueError("the frozen demo plan changed after it was fixed")
    manifest_path = root / claim["implementation_result"]["candidate_path"]
    validate_demo_plan(json.loads(plan_path.read_text(encoding="utf-8")), plan_path.parent, manifest_path, for_execution=True)
    manifest_sha256 = _digest(manifest_path)
    previous, resume_from = None, None
    if recovering:
        if claim.get("status") not in {"RESULT_FAILED", "EVALUATION_INTERRUPTED"} or not attempts:
            raise ValueError("recovery requires a failed/interrupted evaluation, not a successful result")
        previous = attempts[-1]
        if previous["candidate_sha256"] != manifest_sha256 or previous["plan_sha256"] != web["plan_sha256"]:
            raise ValueError("recovery requires the same bound candidate and frozen plan")
        old_version = previous.get("evaluator_version")
        if not interrupted_attempt(root, previous) and old_version == evaluator_version():
            raise ValueError("a completed evaluation requires an evaluator fix before recovery")
        resume_from = root / previous["public_run_dir"]
        if previous.get("checkpoint_sha256") and _digest(resume_from / "checkpoint.json") != previous["checkpoint_sha256"]:
            raise ValueError("recovery checkpoint changed")
    else:
        if submission_count(root, claim) >= MAX_WEB_SUBMISSIONS:
            raise ValueError("three web evaluation submissions are exhausted")
        if any(a["candidate_sha256"] == manifest_sha256 for a in attempts):
            raise ValueError("the same candidate cannot be evaluated twice; use explicit recovery after an interruption")
    number = len(attempts) + 1
    output = root / PUBLIC_RESULTS_ROOT / "runs" / claim_id / f"web-attempt-{number:03d}-{manifest_sha256[:12]}"
    attempt = {"attempt": number, "mode": "web_demo", "candidate_sha256": manifest_sha256,
               "plan_sha256": web["plan_sha256"], "started_at": utc_now(), "status": "RUNNING",
               "evaluator_version": evaluator_version(), "public_run_dir": _relative_path(root, output)}
    if previous:
        attempt["recovery_of"] = previous["attempt"]
        attempt["recovery_reason"] = recovery_reason or "resume interrupted evaluation"
        attempt["pause_wall_seconds"] = max(0, time.time() - datetime.fromisoformat(
            previous.get("finished_at", previous["started_at"])).timestamp())
        attempt["budget_policy"] = "evaluation recovery uses the bound candidate; no development retry or elapsed-development-budget charge"
    attempts.append(attempt)
    # The old result remains in its immutable attempt; a crash must not present it as this attempt's result.
    claim.pop("final_result", None)
    claim["status"] = "IMPLEMENTATION_READY"
    _replace_registry(registry_path, registry)
    started = time.monotonic()
    try:
        result = run_web_demo(plan_path, output, manifest_path=manifest_path,
                              provider=provider or registry["model_runtime"]["provider"], model=model,
                              tester=tester, judge=judge, browser_factory=browser_factory,
                              instance_generator=instance_generator, reviewer=reviewer,
                              review_context=review_context(root, claim), scope=web["scope"],
                              phase_models=phase_models, resume_from=resume_from,
                              tester_mode=tester_mode, cache_ttl=cache_ttl, stable_prefix=stable_prefix,
                              input_cases_from=input_cases_from,
                              gate=root / f"{provider or registry['model_runtime']['provider']}-usage-limit.json",
                              clear_limit=clear_limit, company=(registry.get("company") or {}).get("name"))
    except BaseException:
        registry = _read_registry(registry_path)
        claim = _claim_record(registry, claim_id)
        current = claim["bundle_submissions"][-1]
        current.update(status="INTERRUPTED", environment_interrupted=True, finished_at=utc_now(),
                       elapsed_seconds=time.monotonic() - started)
        if (output / "checkpoint.json").exists():
            current["checkpoint_sha256"] = _digest(output / "checkpoint.json")
        claim["status"] = "EVALUATION_INTERRUPTED"
        _replace_registry(registry_path, registry)
        raise
    reproduction = web_reproduction_status(result)
    registry = _read_registry(registry_path)
    claim = _claim_record(registry, claim_id)
    public_dir = _relative_path(root, output)
    result_sha256 = _digest(output / "demo-result.json")
    interrupted = bool(result.get("interruption"))
    claim["bundle_submissions"][-1].update({
        "status": "INTERRUPTED" if interrupted else "COMPLETED", "environment_interrupted": interrupted,
        "finished_at": utc_now(), "elapsed_seconds": time.monotonic() - started,
        "active_seconds": result.get("active_seconds"), "checkpoint_sha256": _digest(output / "checkpoint.json"),
        "reproduction_status": reproduction, "public_run_dir": public_dir, "result_sha256": result_sha256,
    })
    claim["final_result"] = {
        "schema_version": WEB_RESULT_SCHEMA, "status": "COMPLETED", "reproduction_status": reproduction,
        "candidate_sha256": manifest_sha256, "plan_sha256": web["plan_sha256"],
        "public_run_dir": public_dir, "result_sha256": result_sha256, "code_review": result["code_review"]["status"],
    }
    claim["status"] = "EVALUATION_INTERRUPTED" if interrupted else "RESULT_SUCCESS" if reproduction == "reproduced" else "RESULT_FAILED"
    _replace_registry(registry_path, registry)
    return registry


def validate_web_result(root: Path, claim: dict[str, Any]) -> dict[str, Any]:
    """Check the bound web result still matches its files, candidate and frozen plan; return it."""
    from .agent_harness import PUBLIC_RESULTS_ROOT, _validate_implementation_result
    _validate_implementation_result(root, claim)
    final = claim["final_result"]
    public_dir = root / final["public_run_dir"]
    if (not public_dir.resolve().is_relative_to((root / PUBLIC_RESULTS_ROOT / "runs").resolve())
            or _digest(public_dir / "demo-result.json") != final["result_sha256"]):
        raise ValueError("web demo result binding changed")
    result = json.loads((public_dir / "demo-result.json").read_text(encoding="utf-8"))
    if result.get("evaluation_policy_version") not in {None, 2}:
        raise ValueError("unsupported stored evaluation policy version")
    if (result.get("claim_id") != claim["claim_id"]
            or result.get("candidate_manifest_sha256") != final["candidate_sha256"]
            or final["candidate_sha256"] != claim["implementation_result"]["candidate_sha256"]
            or result.get("plan_sha256") != final["plan_sha256"]
            or final["plan_sha256"] != claim["web_demo"]["plan_sha256"]
            or web_reproduction_status(result, legacy=result.get("evaluation_policy_version") is None) != final["reproduction_status"]
            or (claim["status"] == "RESULT_SUCCESS") != (final["reproduction_status"] == "reproduced")):
        raise ValueError("web demo result status binding changed")
    return result
