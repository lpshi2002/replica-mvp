"""Final evaluation of a web-app Replica: run its frozen demo plan and bind the result to the claim.

The plan was frozen from pass-2 research before implementation and is public;
nothing is sealed. The result directory is published under final-results/runs.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable

from .resources import utc_now
from .web_demo import run_web_demo, web_reproduction_status


WEB_RESULT_SCHEMA = "replica-agent-web-demo-result/v1"
MAX_WEB_SUBMISSIONS = 3


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


def evaluate_web_bundle(registry_path: Path, claim_id: str, *, provider: str | None = None, model: str | None = None,
                        tester: Callable | None = None, judge: Callable | None = None,
                        browser_factory: Callable | None = None, instance_generator: Callable | None = None,
                        reviewer: Callable | None = None) -> dict[str, Any]:
    from .agent_harness import (
        PUBLIC_RESULTS_ROOT, _claim_record, _read_registry, _relative_path, _replace_registry,
        _validate_implementation_result,
    )
    registry = _read_registry(registry_path)
    claim = _claim_record(registry, claim_id)
    root = registry_path.parent.resolve()
    if claim.get("status") != "IMPLEMENTATION_READY":
        raise ValueError("final web evaluation requires IMPLEMENTATION_READY")
    _validate_implementation_result(root, claim)
    web = claim.get("web_demo")
    if not isinstance(web, dict):
        raise ValueError("this claim has no frozen demo plan")
    plan_path = root / web["plan_path"]
    if _digest(plan_path) != web["plan_sha256"]:
        raise ValueError("the frozen demo plan changed after it was fixed")
    manifest_path = root / claim["implementation_result"]["candidate_path"]
    manifest_sha256 = _digest(manifest_path)
    attempts = claim.setdefault("bundle_submissions", [])
    if any(a["status"] == "RUNNING" for a in attempts):
        raise ValueError("the existing web evaluation has not finished")
    if len(attempts) >= MAX_WEB_SUBMISSIONS:
        raise ValueError("three web evaluation submissions are exhausted")
    if any(a["candidate_sha256"] == manifest_sha256 for a in attempts):
        raise ValueError("the same candidate cannot be evaluated twice")
    number = len(attempts) + 1
    output = root / PUBLIC_RESULTS_ROOT / "runs" / claim_id / f"web-attempt-{number:03d}-{manifest_sha256[:12]}"
    attempts.append({"attempt": number, "mode": "web_demo", "candidate_sha256": manifest_sha256,
                     "plan_sha256": web["plan_sha256"], "started_at": utc_now(), "status": "RUNNING"})
    _replace_registry(registry_path, registry)
    started = time.monotonic()
    result = run_web_demo(plan_path, output, manifest_path=manifest_path,
                          provider=provider or registry["model_runtime"]["provider"], model=model,
                          tester=tester, judge=judge, browser_factory=browser_factory,
                          instance_generator=instance_generator, reviewer=reviewer,
                          review_context=review_context(root, claim), scope=web["scope"])
    reproduction = web_reproduction_status(result)
    # Other claims may have advanced while the demo ran; update only this claim.
    registry = _read_registry(registry_path)
    claim = _claim_record(registry, claim_id)
    public_dir = _relative_path(root, output)
    result_sha256 = _digest(output / "demo-result.json")
    claim["bundle_submissions"][-1].update({
        "status": "COMPLETED", "finished_at": utc_now(), "elapsed_seconds": time.monotonic() - started,
        "reproduction_status": reproduction, "public_run_dir": public_dir, "result_sha256": result_sha256,
    })
    claim["final_result"] = {
        "schema_version": WEB_RESULT_SCHEMA, "status": "COMPLETED", "reproduction_status": reproduction,
        "candidate_sha256": manifest_sha256, "plan_sha256": web["plan_sha256"],
        "public_run_dir": public_dir, "result_sha256": result_sha256,
        "code_review": result["code_review"]["status"],
    }
    claim["status"] = "RESULT_SUCCESS" if reproduction == "reproduced" else "RESULT_FAILED"
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
    if (result.get("claim_id") != claim["claim_id"]
            or result.get("candidate_manifest_sha256") != final["candidate_sha256"]
            or final["candidate_sha256"] != claim["implementation_result"]["candidate_sha256"]
            or result.get("plan_sha256") != final["plan_sha256"]
            or final["plan_sha256"] != claim["web_demo"]["plan_sha256"]
            or web_reproduction_status(result) != final["reproduction_status"]
            or (claim["status"] == "RESULT_SUCCESS") != (final["reproduction_status"] == "reproduced")):
        raise ValueError("web demo result status binding changed")
    return result
