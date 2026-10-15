"""Provenance and verification targets of newly frozen web demonstrations.

These checks bind quotations to recorded sources. They do not establish that
an author's interpretation of a quotation is correct; pass-2 research owns that review.
"""
from __future__ import annotations

from typing import Any


CRITERIA_VERSION = 2
BASIS_TYPES = {"public_rule", "original_observation", "separate_verification", "our_condition"}


def text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_criteria(plan: dict, *, for_execution: bool = False) -> None:
    version = plan.get("criteria_version")
    if version is None and not for_execution:
        return  # Read legacy plans without retroactively certifying their criteria.
    if type(version) is not int or version != CRITERIA_VERSION:
        raise ValueError("new execution requires criteria_version 2; freeze a corrected plan before implementation")
    records = plan.get("sources", [])
    if not isinstance(records, list):
        raise ValueError("criteria sources must be a list")
    sources = {}
    for record in records:
        if (not isinstance(record, dict) or not all(text(record.get(k)) for k in ("id", "source", "excerpt"))
                or record["id"] in sources):
            raise ValueError("criteria sources need unique ids, sources and excerpts")
        sources[record["id"]] = record
    for case in plan["cases"]:
        limits = case.get("execution_limits", [])
        if not isinstance(limits, list) or not all(text(limit) for limit in limits):
            raise ValueError("execution_limits must describe stopping conditions separately from expectations")
        for expectation in case["expectations"]:
            label = f"expectation {expectation['id']}"
            basis = expectation["basis"]
            if basis["type"] == "our_condition":
                if not text(basis.get("rationale")):
                    raise ValueError(f"{label} our_condition needs a rationale, not an execution budget")
            else:
                source_id = basis.get("source_id")
                source = sources.get(source_id) if isinstance(source_id, str) else None
                quote = basis.get("quote")
                if (not source or source["source"] != basis["source"] or not text(quote)
                        or quote not in source["excerpt"] or not text(basis.get("interpretation"))):
                    raise ValueError(f"{label} basis needs a matching recorded source, exact quote and interpretation")
                detail = {"original_observation": "conditions", "separate_verification": "method"}.get(basis["type"])
                if detail and not text(basis.get(detail)):
                    raise ValueError(f"{label} basis needs {detail}")
            if expectation.get("purpose", "functional") not in {"functional", "quality"}:
                raise ValueError(f"{label} is an execution limit, not an acceptance criterion")
            covers = expectation.get("covers_steps")
            if (not isinstance(covers, list) or not covers
                    or any(type(i) is not int or i not in case["covers_steps"] for i in covers)
                    or len(set(covers)) != len(covers)):
                raise ValueError(f"{label} needs covers_steps within the case's planned route")
            parts = expectation.get("covers_parts", [])
            if not isinstance(parts, list) or any(
                    not isinstance(p, dict) or type(p.get("step_index")) is not int
                    or p["step_index"] not in covers or not text(p.get("part_id")) for p in parts):
                raise ValueError(f"{label} covers_parts need step_index and part_id")
            if "precondition" in expectation:
                if not text(expectation["precondition"]) or expectation.get("check") is not None:
                    raise ValueError(f"{label} needs a textual precondition and semantic observation of its occurrence")


def expectation_identity(expectation: dict) -> dict:
    return {key: expectation[key] for key in
            ("id", "description", "basis", "covers_steps", "covers_parts", "precondition", "upload_relation")
            if key in expectation}


def validate_verification_parts(parts: Any) -> None:
    if not isinstance(parts, list):
        raise ValueError("verification_parts must be a list")
    seen = set()
    for part in parts:
        if (not isinstance(part, dict) or not text(part.get("id")) or not text(part.get("description"))
                or part["id"] in seen):
            raise ValueError("verification_parts need unique ids and descriptions")
        seen.add(part["id"])
        if "reason" in part and not text(part["reason"]):
            raise ValueError("an untested verification part needs a reason")
        evidence = part.get("development_evidence", [])
        if not isinstance(evidence, list) or any(not isinstance(e, dict) or not all(
                text(e.get(k)) for k in ("source", "method", "result")) for e in evidence):
            raise ValueError("development_evidence needs source, method and result; it is not final UI verification")


def verification_scope(scope: dict, cases: list[dict]) -> dict:
    """Measure only explicitly mapped expectations; a planned route proves no outcome."""
    if not scope.get("steps"):
        return scope
    outcomes = [(c["case_id"], e) for c in cases for e in c["expectations"]]

    def observed(index, part_id=None):
        matches = [{"case_id": cid, "expectation_id": e["id"], "status": e["status"]}
                   for cid, e in outcomes if index in e.get("covers_steps", []) and (part_id is None or
                       {"step_index": index, "part_id": part_id} in e.get("covers_parts", []))]
        statuses = {m["status"] for m in matches}
        status = ("not_evaluated" if not statuses or statuses == {"not_evaluated"} else
                  "partially_evaluated" if "not_evaluated" in statuses else
                  "failed" if "failed" in statuses else "passed")
        return {"status": status, "expectations": matches, "evidence_level": "final_browser_demo"}

    steps, uncovered, unverified = [], [], []
    for step in scope["steps"]:
        if step["disposition"] == "excluded":
            steps.append({**step, "verification": {"status": "excluded", "expectations": []}})
            continue
        observation = observed(step["step_index"])
        parts = []
        for part in step.get("verification_parts", []):
            item = {**part, "step_index": step["step_index"], "verification": observed(step["step_index"], part["id"])}
            parts.append(item)
            if item["verification"]["status"] in {"not_evaluated", "partially_evaluated"}:
                unverified.append(item)
        current = {**step, "verification": observation, "verification_parts": parts}
        steps.append(current)
        if observation["status"] in {"not_evaluated", "partially_evaluated"}:
            uncovered.append(current)
    return {**scope, "steps": steps, "uncovered_steps": uncovered, "unverified_parts": unverified}
