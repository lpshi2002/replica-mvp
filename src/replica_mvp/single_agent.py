"""One implementation agent per claim, sharing the frozen bundle evaluator.

This route records real single-agent identities; it does not simulate pair messages.
Only the orchestrator writes the registry. Implementers receive public contracts.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .agent_harness import (
    HARNESS_SCHEMA, IMPLEMENTATION_RESULT_SCHEMA, REGISTRY_NAME,
    _builder_context, _claim_record, freeze_web_claim, _public_research, _read_registry,
    _replace_registry, _validate_bound_artifact, _validate_implementation_bundle, require_company_mount,
    _write_new_json,
)
from .bundle_evaluation import digest, prepare_bundle_evaluation, _validate_history, MAX_SUBMISSIONS
from .bundle_runtime import copy_bundle
from .resources import budget_stop, timestamp, unknown_resources, utc_now
from .second_pass import parse_second_pass


def prepare_single_harness(source: Path, run_dir: Path, *, orchestrator_id: str,
                           model: str = "gpt-6-astra", reasoning_effort: str = "low",
                           model_runtime: str = "codex") -> dict[str, Any]:
    if not all(isinstance(v, str) and v.strip() for v in (orchestrator_id, model, reasoning_effort)):
        raise ValueError("single implementation requires an identity, model and reasoning effort")
    raw = source.read_bytes()
    research = json.loads(raw)
    canonical = parse_second_pass(research, model_runtime=model_runtime, fragment_root=source.parent)
    if any(c["payload"].get("schema_version") != "replica-agent-claim/v2" for c in canonical["claims"]):
        raise ValueError("single implementation requires completed company research")
    run_dir.mkdir(parents=True, exist_ok=False)
    claims = []
    for item in canonical["claims"]:
        cid, payload = item["claim_id"], item["payload"]
        namespace = f"claims/{cid}"
        public = run_dir / namespace
        (public / "implementer").mkdir(parents=True)
        sealed = run_dir / "evaluator-vault" / cid / "claim-sealed.json"
        sealed.parent.mkdir(parents=True)
        _write_new_json(sealed, payload)
        _write_new_json(public / "claim.json", _public_research(payload))
        web_demo, research_gaps = freeze_web_claim(payload, cid, source.parent, run_dir)
        context = _builder_context(cid, payload, model_runtime, web_demo["plan_path"] if web_demo else None)
        context["schema_version"] = "replica-implementation-context/v1"
        _write_new_json(public / "implementation-context.json", context)
        claims.append({
            "claim_id": cid, "namespace": namespace, "status": "RESEARCH_INCOMPLETE" if research_gaps else "PENDING",
            **({"web_demo": web_demo} if web_demo else {}),
            **({"research_gaps": research_gaps} if research_gaps else {}),
            "execution_mode": "single", "claim_payload_path": f"{namespace}/claim.json",
            "sealed_claim_path": str(sealed.relative_to(run_dir)), "sealed_claim_sha256": digest(sealed),
            "implementation_context_path": f"{namespace}/implementation-context.json",
            "implementer": {"agent_id": None, "parent_agent_id": orchestrator_id,
                            "requested_model": model, "requested_reasoning_effort": reasoning_effort,
                            "role": "implementer", "artifact_namespace": f"{namespace}/implementer"},
        })
    registry = {
        "schema_version": HARNESS_SCHEMA, "execution_mode": "single", "status": "RUNNING",
        "claim_count": len(claims), "claims": claims,
        "orchestrator": {"agent_id": orchestrator_id, "role": "root_orchestrator", "status": "RUNNING"},
        "model_runtime": {"provider": model_runtime, "transport": "local_cli"},
        "scheduling": {"policy": "parallel_single_implementers", "active_claim_id": None,
                       "max_concurrent_implementers": len(claims), "peak_active_implementers": 0},
        "require_final_bundle_evaluation": True,
        "company": canonical.get("company"), "company_claims": canonical.get("company_claims", []),
        "research_source": {"path": str(source.resolve()), "sha256": hashlib.sha256(raw).hexdigest()},
        **({"research_agent_sessions": canonical["research_agent_sessions"]}
           if canonical.get("research_agent_sessions") else {}),
    }
    path = run_dir / REGISTRY_NAME
    _write_new_json(path, registry)
    for claim in claims:
        # Web-app claims are evaluated by their frozen public demo plan, not a sealed JSON suite.
        if "web_demo" not in claim and "research_gaps" not in claim:
            registry = prepare_bundle_evaluation(path, claim["claim_id"])
    if not claims:
        from .agent_harness import finish_agent_harness
        return finish_agent_harness(path)
    return registry


def start_single_implementation(registry_path: Path, claim_id: str, *, agent_id: str,
                                model: str, reasoning_effort: str) -> dict[str, Any]:
    registry = _read_registry(registry_path)
    claim = _claim_record(registry, claim_id)
    worker = claim.get("implementer", {})
    if registry.get("execution_mode") != "single" or claim["status"] != "PENDING":
        raise ValueError("single implementation requires a prepared pending claim")
    if not isinstance(agent_id, str) or not agent_id.strip() or agent_id == registry["orchestrator"]["agent_id"]:
        raise ValueError("a real, distinct implementer identity is required")
    if any(c["implementer"]["agent_id"] == agent_id for c in registry["claims"]):
        raise ValueError("each claim needs its own implementer")
    if (model, reasoning_effort) != (worker["requested_model"], worker["requested_reasoning_effort"]):
        raise ValueError("spawn model and reasoning effort differ from the requested policy")
    worker["agent_id"] = agent_id
    claim.update(status="IMPLEMENTING", started_at=utc_now())
    active = sum(c["status"] == "IMPLEMENTING" for c in registry["claims"])
    registry["scheduling"]["peak_active_implementers"] = max(active, registry["scheduling"]["peak_active_implementers"])
    _replace_registry(registry_path, registry)
    return registry


def _development_seconds(claim: dict[str, Any]) -> float:
    """Count development intervals, stopping the clock while evaluation owns the bundle.

    Legacy intervals use their recorded start/finish conservatively; unknown idle time
    inside an implementation session is not silently subtracted.
    """
    accumulated = claim.get("development_elapsed_seconds", 0)
    if claim["status"] == "IMPLEMENTING":
        start = claim.get("development_active_since", claim["started_at"])
        return accumulated + max(0, (timestamp(utc_now()) - timestamp(start)).total_seconds())
    if "development_elapsed_seconds" in claim:
        return accumulated
    return max(0, (timestamp(claim["finished_at"]) - timestamp(claim["started_at"])).total_seconds())


def bind_single_implementation(registry_path: Path, claim_id: str, *, agent_id: str) -> dict[str, Any]:
    registry = _read_registry(registry_path)
    claim = _claim_record(registry, claim_id)
    if (registry.get("execution_mode") != "single" or claim["status"] != "IMPLEMENTING"
            or claim["implementer"]["agent_id"] != agent_id):
        raise ValueError("only the bound single implementer can submit an active claim")
    root = registry_path.parent.resolve()
    workspace = root / claim["implementer"]["artifact_namespace"]
    manifest_path = workspace / "implementation" / "manifest.json"
    payload = json.loads((root / claim["claim_payload_path"]).read_text())
    manifest, artifacts = _validate_implementation_bundle(root, claim_id, manifest_path, payload)
    require_company_mount(claim, manifest)
    if any(a["candidate_sha256"] == digest(manifest_path) for a in claim.get("bundle_submissions", [])):
        raise ValueError("the same candidate cannot be resubmitted to sealed tests")
    report_path = workspace / "development.json"
    report = json.loads(report_path.read_text())
    if (not isinstance(report, dict) or report.get("status") != "passed"
            or not isinstance(report.get("checks"), list) or not report["checks"]
            or any(not isinstance(c, dict) or not isinstance(c.get("command"), str)
                   or not c["command"].strip() or type(c.get("exit_code")) is not int
                   or c["exit_code"] != 0 for c in report["checks"])):
        raise ValueError("a successful development check receipt is required")
    # The implementer's own append-only record of what each development attempt changed and found.
    log_path = workspace / "development-log.jsonl"
    development_log = None
    if log_path.exists():
        try:
            entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except ValueError:
            raise ValueError("development-log.jsonl must hold one JSON object per line") from None
        if not all(isinstance(entry, dict) for entry in entries):
            raise ValueError("development-log.jsonl must hold one JSON object per line")
        development_log = {"path": log_path.relative_to(root).as_posix(), "sha256": digest(log_path),
                           "entries": len(entries)}
    resources = unknown_resources()
    budget = payload["execution_policy"]["budget"]
    elapsed = _development_seconds(claim)
    stop = budget_stop(budget, claim["started_at"], [resources], elapsed_seconds=elapsed)
    if stop:
        # A spent budget ends the claim with a recorded reason instead of leaving it open.
        return _close_unbuilt(registry_path, registry, claim, stop,
                              f"The implementation budget stopped the claim before submission ({stop}).")
    relative = manifest_path.relative_to(root).as_posix()
    state = {
        "schema_version": "replica-single-execution/v1", "status": "SUCCESS", "claim_id": claim_id,
        "agent_id": agent_id, "requested_model": claim["implementer"]["requested_model"],
        "requested_reasoning_effort": claim["implementer"]["requested_reasoning_effort"],
        "started_at": claim["started_at"], "finished_at": utc_now(),
        "claim_sha256": digest(root / claim["claim_payload_path"]),
        "development_receipt": {"path": report_path.relative_to(root).as_posix(), "sha256": digest(report_path)},
        "attempts": [{"correction_number": 0, "decision": "success", "candidate_path": relative,
                      "candidate_sha256": digest(manifest_path), "resources": resources}],
        "measurement_note": ("Token usage is read from the implementer's session log at harness finish; "
                             "development-log.jsonl holds the implementer's own attempt record."),
        "development_log": development_log,
    }
    state_path = workspace / "execution-state.json"
    _write_new_json(state_path, state)
    binding = {"candidate_path": relative, "candidate_sha256": digest(manifest_path),
               "execution_state_sha256": digest(state_path)}
    claim["execution_result"] = binding.copy()
    claim["development_log"] = development_log
    claim["implementation_result"] = {
        "schema_version": IMPLEMENTATION_RESULT_SCHEMA, "status": "IMPLEMENTATION_READY", **binding,
        **{k: manifest[k] for k in ("scenario_id", "implementation_type", "dependency_level", "entrypoint",
                                  "command", "dependencies", "environment_variables")}, "artifacts": artifacts,
    }
    claim.update(status="IMPLEMENTATION_READY", finished_at=utc_now())
    claim["development_elapsed_seconds"] = elapsed
    claim.pop("development_active_since", None)
    _replace_registry(registry_path, registry)
    return registry


# Why a claim ended without a bound implementation; budget and availability stops block the experiment.
SINGLE_FAILURE_CATEGORIES = ("development_checks_failed", "implementer_unavailable",
                             "budget_exhausted", "budget_unverifiable")


def _close_unbuilt(registry_path: Path, registry: dict[str, Any], claim: dict[str, Any],
                   category: str, reason: str) -> dict[str, Any]:
    claim["failure"] = {"category": category, "reason": reason, "recorded_at": utc_now()}
    claim.update(status="EXECUTION_FAILED", finished_at=utc_now())
    _replace_registry(registry_path, registry)
    return registry


def fail_single_implementation(registry_path: Path, claim_id: str, *, category: str, reason: str) -> dict[str, Any]:
    """End a claim whose implementer could not be created or could not submit a bindable bundle."""
    registry = _read_registry(registry_path)
    claim = _claim_record(registry, claim_id)
    if registry.get("execution_mode") != "single" or claim["status"] not in {"PENDING", "IMPLEMENTING"}:
        raise ValueError("only a pending or implementing single claim can end without an implementation")
    if category not in SINGLE_FAILURE_CATEGORIES:
        raise ValueError(f"failure category must be one of {', '.join(SINGLE_FAILURE_CATEGORIES)}")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("a failure reason is required")
    return _close_unbuilt(registry_path, registry, claim, category, reason.strip())


def retry_single_implementation(registry_path: Path, claim_id: str) -> dict[str, Any]:
    registry = _read_registry(registry_path)
    claim = _claim_record(registry, claim_id)
    if registry.get("execution_mode") != "single" or claim["status"] not in {"RESULT_FAILED", "EVALUATION_INTERRUPTED"}:
        raise ValueError("single retry requires a failed or interrupted evaluation")
    root = registry_path.parent.resolve()
    validate_single_implementation(root, claim)
    if claim.get("web_demo") and claim["status"] == "EVALUATION_INTERRUPTED":
        raise ValueError("resume the same bundle with agent-web-recover; an evaluation interruption does not require implementation retry")
    if claim["status"] == "RESULT_FAILED":
        from .agent_harness import _validate_final_result
        from .web_evaluation import write_retry_feedback
        _validate_final_result(root, claim)
        write_retry_feedback(root, claim, root / claim["implementer"]["artifact_namespace"])
    _validate_history(root, claim)
    attempts = claim.get("bundle_submissions", [])
    from .web_evaluation import submission_count
    if not attempts or (submission_count(root, claim) if claim.get("web_demo") else len(attempts)) >= MAX_SUBMISSIONS:
        raise ValueError("three sealed submissions are exhausted or no prior submission exists")
    payload = json.loads((root / claim["claim_payload_path"]).read_text())
    elapsed = _development_seconds(claim)
    if budget_stop(payload["execution_policy"]["budget"], claim["started_at"], [unknown_resources()], elapsed_seconds=elapsed):
        raise ValueError("single implementation budget prevents retry")
    state_path = root / claim["implementer"]["artifact_namespace"] / "execution-state.json"
    state = json.loads(state_path.read_text())
    archive = root / "evaluator-vault" / claim_id / f"single-development-{len(attempts):03d}"
    archive.mkdir(exist_ok=False)
    copy_bundle(root / claim["implementation_result"]["candidate_path"], archive / "implementation")
    import shutil
    shutil.copyfile(state_path, archive / "execution-state.json")
    shutil.copyfile(root / state["development_receipt"]["path"], archive / "development.json")
    # The next code review reads only the log entries written after this submission.
    log = root / claim["implementer"]["artifact_namespace"] / "development-log.jsonl"
    if log.is_file():
        shutil.copyfile(log, archive / "development-log.jsonl")
    attempts[-1]["development_archive"] = {
        "path": archive.relative_to(root).as_posix(),
        "artifacts": {p.relative_to(archive).as_posix(): digest(p) for p in archive.rglob("*") if p.is_file()},
    }
    for key in ("execution_result", "implementation_result", "final_result", "finished_at"):
        claim.pop(key, None)
    claim["status"] = "IMPLEMENTING"
    claim["development_elapsed_seconds"] = elapsed
    claim["development_active_since"] = utc_now()
    claim.setdefault("retries", []).append({"requested_at": utc_now(), "agent_id": claim["implementer"]["agent_id"]})
    _replace_registry(registry_path, registry)
    state_path.unlink()
    return registry


def validate_single_implementation(root: Path, claim: dict[str, Any]) -> None:
    result = claim.get("implementation_result", {})
    worker = claim["implementer"]
    namespace = f"claims/{claim['claim_id']}/implementer"
    if worker["artifact_namespace"] != namespace:
        raise ValueError("single implementer namespace changed")
    if result.get("candidate_path") != f"{namespace}/implementation/manifest.json":
        raise ValueError("single candidate path changed")
    candidate = _validate_bound_artifact(root, {"path": result["candidate_path"],
                                              "sha256": result["candidate_sha256"]}, label="single candidate")
    state_path = _validate_bound_artifact(root, {"path": f"{namespace}/execution-state.json",
                                               "sha256": result["execution_state_sha256"]}, label="single execution")
    state = json.loads(state_path.read_text())
    if (state.get("schema_version") != "replica-single-execution/v1" or state.get("status") != "SUCCESS"
            or state.get("claim_id") != claim["claim_id"] or state.get("agent_id") != worker["agent_id"]
            or state.get("requested_model") != worker["requested_model"]
            or state.get("requested_reasoning_effort") != worker["requested_reasoning_effort"]
            or state["claim_sha256"] != digest(root / claim["claim_payload_path"])
            or state["attempts"][-1]["candidate_sha256"] != result["candidate_sha256"]
            or state["attempts"][-1]["candidate_path"] != result["candidate_path"]
            or result["execution_state_sha256"] != claim["execution_result"]["execution_state_sha256"]):
        raise ValueError("single execution binding changed")
    _validate_bound_artifact(root, state["development_receipt"], label="single development receipt")
    payload = json.loads((root / claim["claim_payload_path"]).read_text())
    manifest, artifacts = _validate_implementation_bundle(root, claim["claim_id"], candidate, payload)
    if (result.get("schema_version") != IMPLEMENTATION_RESULT_SCHEMA or result.get("status") != "IMPLEMENTATION_READY"
            or result.get("artifacts") != artifacts
            or any(result.get(k) != manifest[k] for k in ("scenario_id", "implementation_type", "dependency_level",
                                                        "entrypoint", "command", "dependencies", "environment_variables"))):
        raise ValueError("single implementation bundle changed")
