from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from .completion import _valid_completion_contract, research_test_kind
from .experience import validate_experience_profile
from .resources import validate_budget


LEGACY_SECOND_PASS_SCHEMA = "replica-second-pass-result/v1"
MULTI_SECOND_PASS_SCHEMA = "replica-second-pass-claim-collection/v1"
CANONICAL_CLAIM_COLLECTION_SCHEMA = "replica-claim-collection/v1"
RESEARCH_AGENT_CLAIM_SCHEMA = "replica-agent-claim/v2"
MODEL_RUNTIMES = ("codex", "claude")
DEPENDENCY_ORDER = {
    "oss_only": 0,
    "commercial_api": 1,
    "proprietary_data": 2,
}
FINDING_BUCKETS = (
    "evidence",
    "datasets_apis",
    "oss_papers_patents",
    "eval_assets",
    "access_license",
    "impl_path",
)
FINDING_STATES = {"filled", "unknown", "not_applicable"}
STEP_DISPOSITIONS = {"implemented", "external_dependency", "excluded", "unconfirmed"}
REQUIRED_SCENARIO_TEST_KINDS = {"normal", "boundary", "insufficient_information"}
SECOND_PASS_FIELDS = {
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
SECOND_PASS_FIELDS_WITHOUT_IMPLEMENTATION = SECOND_PASS_FIELDS - {"implementation"}
SECOND_PASS_FIELDS_WITH_EXPERIENCE = SECOND_PASS_FIELDS | {"experience"}
SECOND_PASS_FIELDS_WITH_EXPERIENCE_WITHOUT_IMPLEMENTATION = (
    SECOND_PASS_FIELDS_WITH_EXPERIENCE - {"implementation"}
)


def _is_nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_text_list(value: Any, *, allow_empty: bool = True) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(_is_nonempty_text(item) for item in value)
    )


def _has_valid_implementation(implementation: Any) -> bool:
    if not isinstance(implementation, dict):
        return False
    if set(implementation) == {"operation", "configuration"}:
        operation = implementation.get("operation")
        configuration = implementation.get("configuration")
        return _is_nonempty_text(operation) and isinstance(configuration, dict)
    return (
        set(implementation) == {"strategy", "instructions"}
        and implementation.get("strategy") == "generated_component"
        and _is_nonempty_text(implementation.get("instructions"))
    )


def validate_second_pass_claim(
    value: Any,
    *,
    allow_missing_implementation: bool = False,
) -> dict[str, Any]:
    """Validate one legacy v1 claim payload without changing it."""
    base_field_sets = (
        {
            frozenset(SECOND_PASS_FIELDS),
            frozenset(SECOND_PASS_FIELDS_WITHOUT_IMPLEMENTATION),
            frozenset(SECOND_PASS_FIELDS_WITH_EXPERIENCE),
            frozenset(SECOND_PASS_FIELDS_WITH_EXPERIENCE_WITHOUT_IMPLEMENTATION),
        }
        if allow_missing_implementation
        else {
            frozenset(SECOND_PASS_FIELDS),
            frozenset(SECOND_PASS_FIELDS_WITH_EXPERIENCE),
        }
    )
    valid_field_sets = base_field_sets | {
        frozenset({*fields, "completion_contract"})
        for fields in base_field_sets
    }
    if not isinstance(value, dict) or frozenset(value) not in valid_field_sets:
        raise ValueError("invalid second-pass result contract")
    input_contract = value.get("input_contract")
    output_contract = value.get("output_contract")
    has_implementation = "implementation" in value
    implementation = value.get("implementation")
    criteria = value.get("acceptance_criteria")
    tests = value.get("tests")
    required_fields = (
        input_contract.get("required")
        if isinstance(input_contract, dict)
        else None
    )
    criterion_ids = (
        [criterion.get("id") for criterion in criteria]
        if isinstance(criteria, list)
        and all(isinstance(criterion, dict) for criterion in criteria)
        else []
    )
    test_cases = tests.get("cases") if isinstance(tests, dict) else None
    covered_ids = (
        {
            criterion_id
            for case in test_cases
            if isinstance(case, dict)
            for criterion_id in case.get("criterion_ids", [])
        }
        if isinstance(test_cases, list)
        and all(
            isinstance(case, dict)
            and _is_text_list(case.get("criterion_ids"), allow_empty=False)
            for case in test_cases
        )
        else set()
    )
    if (
        value.get("schema_version") != LEGACY_SECOND_PASS_SCHEMA
        or not all(
            _is_nonempty_text(value.get(field))
            for field in (
                "replica_id",
                "company",
                "capability",
                "canonical_claim",
            )
        )
        or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value["replica_id"])
        or value.get("evidence_level") not in {"direct", "public", "claim_only"}
        or value.get("readiness") != "ready"
        or value.get("handoff") != "build"
        or not isinstance(input_contract, dict)
        or set(input_contract) != {"type", "required"}
        or input_contract.get("type") != "object"
        or not _is_text_list(required_fields, allow_empty=False)
        or len(set(required_fields)) != len(required_fields)
        or not isinstance(output_contract, dict)
        or set(output_contract) != {"type", "format"}
        or not _is_nonempty_text(output_contract.get("type"))
        or not _is_nonempty_text(output_contract.get("format"))
        or not isinstance(criteria, list)
        or not criteria
        or not all(
            set(criterion) == {"id", "description"}
            and _is_nonempty_text(criterion.get("id"))
            and _is_nonempty_text(criterion.get("description"))
            for criterion in criteria
        )
        or len(set(criterion_ids)) != len(criterion_ids)
        or (not has_implementation and not allow_missing_implementation)
        or (has_implementation and not _has_valid_implementation(implementation))
        or not _is_text_list(value.get("supported_scope"))
        or not _is_text_list(value.get("unsupported_scope"))
        or not _is_text_list(value.get("limitations"))
        or not isinstance(tests, dict)
        or set(criterion_ids) != covered_ids
        or (
            "completion_contract" in value
            and not _valid_completion_contract(value["completion_contract"])
        )
    ):
        raise ValueError("invalid second-pass result contract")
    if "experience" in value:
        try:
            experience = validate_experience_profile(value["experience"])
        except ValueError:
            raise ValueError("invalid second-pass result contract") from None
        question_field = experience["interaction"]["question_field"]
        if (
            question_field not in required_fields
            or output_contract["type"] != "object"
            or output_contract["format"] != "grounded-conversation-response"
            or experience["comparison"]["evidence_level"]
            != value["evidence_level"]
            or not (set(required_fields) - {question_field}).issubset(
                experience["runtime_input"]
            )
        ):
            raise ValueError("invalid second-pass result contract")
        for example in experience["examples"]:
            public_input = dict(experience["runtime_input"])
            public_input[question_field] = example["question"]
            public_required_input = {
                field: public_input[field]
                for field in required_fields
                if field in public_input
            }
            if any(
                isinstance(case.get("input"), dict)
                and {
                    field: case["input"][field]
                    for field in required_fields
                    if field in case["input"]
                }
                == public_required_input
                for case in test_cases
            ):
                raise ValueError("invalid second-pass result contract")
        frozen_expected_outputs = {
            json.dumps(
                assertion["value"],
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            )
            for case in test_cases
            for assertion in case.get("deterministic_assertions", [])
            if isinstance(assertion, dict)
            and assertion.get("type") == "equals"
            and "value" in assertion
        }
        if any(
            json.dumps(
                original["output"],
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            )
            in frozen_expected_outputs
            for original in experience["comparison"]["original_outputs"]
        ):
            raise ValueError("invalid second-pass result contract")
    return value


class ResearchIncomplete(ValueError):
    """A ready claim lacks research the implementation would otherwise invent."""

    def __init__(self, claim_id: str, reason: str) -> None:
        super().__init__(f"RESEARCH_INCOMPLETE: {claim_id}: {reason}")


def _valid_sources(sources: Any, *, allow_empty: bool) -> bool:
    return (
        isinstance(sources, list)
        and (allow_empty or bool(sources))
        and all(
            isinstance(source, dict)
            and _is_nonempty_text(source.get("url"))
            and _is_nonempty_text(source.get("excerpt"))
            for source in sources
        )
    )


def _validate_revisions(claim_id: str, second_pass: dict[str, Any], original: Any) -> None:
    """A changed readiness or handoff verdict needs its prior verdict, reason, and new evidence."""
    revisions = second_pass.get("revisions", [])
    if not isinstance(revisions, list) or not all(
        isinstance(revision, dict)
        and isinstance(revision.get("previous"), dict)
        and _is_nonempty_text(revision["previous"].get("readiness"))
        and _is_nonempty_text(revision["previous"].get("handoff"))
        and _is_nonempty_text(revision.get("reason"))
        and _is_nonempty_text(revision.get("revised_at"))
        and _valid_sources(revision.get("sources"), allow_empty=False)
        for revision in revisions
    ):
        raise ResearchIncomplete(
            claim_id,
            "each second_pass.revisions entry needs previous readiness and handoff, "
            "a reason, revised_at, and sources with excerpts",
        )
    if not isinstance(original, dict):
        return
    verdict = (
        (original.get("readiness") or {}).get("status"),
        (original.get("handoff") or {}).get("action"),
    )
    current = (second_pass["readiness"].get("status"), second_pass["handoff"].get("action"))
    if verdict == current:
        return
    if not revisions or (
        revisions[0]["previous"]["readiness"],
        revisions[0]["previous"]["handoff"],
    ) != verdict:
        raise ResearchIncomplete(
            claim_id,
            f"the pass-2 fragment verdict {verdict} was changed to {current} "
            "without a revision that records the original verdict",
        )


def _read_fragment(claim_id: str, second_pass: dict[str, Any], fragment_root: Path) -> dict[str, Any]:
    """Read the worker's original verdict; without it a changed verdict cannot be detected."""
    fragment = (second_pass.get("run") or {}).get("fragment")
    path = fragment_root / fragment if _is_nonempty_text(fragment) else None
    if (
        path is None
        or path.is_symlink()
        or not path.resolve().is_relative_to(fragment_root.resolve())
        or not path.is_file()
    ):
        raise ResearchIncomplete(
            claim_id,
            "the pass-2 fragment named by second_pass.run.fragment is missing, so the verdict "
            "cannot be verified; keep second_pass/ next to research.json",
        )
    try:
        original = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError(f"invalid pass-2 fragment: {path}") from None
    if not isinstance(original, dict):
        raise ValueError(f"invalid pass-2 fragment: {path}")
    # Another claim's fragment would let its verdict stand in for this claim's.
    if original.get("claim_id") != claim_id:
        raise ResearchIncomplete(
            claim_id,
            f"the pass-2 fragment {fragment} records claim_id {original.get('claim_id')!r}, not this claim",
        )
    return original


def _validate_findings(claim_id: str, second_pass: dict[str, Any]) -> None:
    findings = second_pass.get("findings")
    if not isinstance(findings, dict):
        raise ResearchIncomplete(claim_id, "second_pass.findings must be an object")
    for bucket in FINDING_BUCKETS:
        finding = findings.get(bucket)
        if (
            not isinstance(finding, dict)
            or finding.get("state") not in FINDING_STATES
            or not _is_nonempty_text(finding.get("note"))
            or not _valid_sources(
                finding.get("sources", []),
                allow_empty=finding.get("state") != "filled",
            )
        ):
            raise ResearchIncomplete(
                claim_id,
                f"finding {bucket} must be closed with a note; filled findings need sources with excerpts",
            )
    boundaries = (second_pass.get("workflow") or {}).get("boundaries")
    if not isinstance(boundaries, dict) or boundaries.get("state") not in {"stated", "undisclosed"}:
        raise ResearchIncomplete(claim_id, "workflow.boundaries.state must be stated or undisclosed")


def _confirmed_workflow(claim_id: str, owner: str, claim: dict[str, Any]) -> dict[str, Any]:
    """Return the workflow steps frozen before implementation and how pass 2 changed pass 1.

    Pass 2's ``workflow.steps`` is the confirmed workflow when it is non-empty. Each of
    its steps keeps a pass-1 step (``first_pass_step`` or identical text) or is an added
    step with sourced excerpts, and every pass-1 step it drops is listed in
    ``workflow.removed_steps`` with a reason and sources, so rewriting the list can
    neither add unmapped scope nor drop a step silently.
    """
    first_steps = ((claim.get("first_pass") or {}).get("workflow") or {}).get("steps", [])
    workflow = (claim.get("second_pass") or {}).get("workflow") or {}
    second_steps = workflow.get("steps") or []
    if not isinstance(first_steps, list) or not isinstance(second_steps, list):
        raise ResearchIncomplete(claim_id, f"{owner} workflow.steps must be a list")
    if not second_steps:
        return {"claim_id": owner, "basis": "first_pass", "steps": first_steps,
                "added_steps": [], "removed_steps": []}
    first_texts = [step.get("step") if isinstance(step, dict) else None for step in first_steps]
    kept: set[int] = set()
    added = []
    for position, step in enumerate(second_steps, start=1):
        if not isinstance(step, dict) or not _is_nonempty_text(step.get("step")):
            raise ResearchIncomplete(claim_id, f"{owner} second_pass.workflow.steps entries need a step")
        origin = step.get("first_pass_step")
        if origin is None and step["step"] in first_texts:
            origin = first_texts.index(step["step"]) + 1
        if origin is None:
            if not _valid_sources(step.get("sources"), allow_empty=False):
                raise ResearchIncomplete(
                    claim_id,
                    f"{owner} pass-2 step {position} is not a pass-1 step; name its first_pass_step "
                    "or give the added step sources with excerpts",
                )
            added.append({"step_index": position, "step": step["step"]})
        elif isinstance(origin, bool) or not isinstance(origin, int) or not 1 <= origin <= len(first_steps):
            raise ResearchIncomplete(claim_id, f"{owner} pass-2 step {position} names an unknown first_pass_step")
        else:
            kept.add(origin)
    removed = workflow.get("removed_steps", [])
    if not isinstance(removed, list) or not all(
        isinstance(entry, dict)
        and type(entry.get("first_pass_step")) is int
        and 1 <= entry["first_pass_step"] <= len(first_steps)
        and entry["first_pass_step"] not in kept
        and _is_nonempty_text(entry.get("reason"))
        and _valid_sources(entry.get("sources"), allow_empty=False)
        for entry in removed
    ):
        raise ResearchIncomplete(
            claim_id,
            f"{owner} workflow.removed_steps entries need a dropped first_pass_step, a reason, "
            "and sources with excerpts",
        )
    removed_indexes = {entry["first_pass_step"] for entry in removed}
    unaccounted = sorted(set(range(1, len(first_steps) + 1)) - kept - removed_indexes)
    if unaccounted:
        raise ResearchIncomplete(
            claim_id,
            f"pass-2 workflow drops pass-1 steps without workflow.removed_steps: "
            f"{', '.join(f'{owner}#{index}' for index in unaccounted)}",
        )
    return {
        "claim_id": owner,
        "basis": "second_pass",
        "steps": second_steps,
        "added_steps": added,
        "removed_steps": [
            {"first_pass_step": entry["first_pass_step"], "step": first_texts[entry["first_pass_step"] - 1],
             "reason": entry["reason"]}
            for entry in removed
        ],
    }


def _step_coverage(
    claim_id: str,
    scenario: dict[str, Any],
    workflows: dict[str, list[Any]],
) -> dict[str, Any]:
    """Map every researched workflow step to what the frozen scenario does with it."""
    coverage = scenario.get("step_coverage")
    if not isinstance(coverage, list):
        raise ResearchIncomplete(
            claim_id,
            f"scenario {scenario['id']} needs step_coverage for every researched workflow step",
        )
    seen: set[tuple[str, int]] = set()
    excluded, external = [], []
    for entry in coverage:
        if not isinstance(entry, dict):
            raise ResearchIncomplete(claim_id, "step_coverage entries must be objects")
        owner = entry.get("claim_id", claim_id)
        index = entry.get("step_index")
        disposition = entry.get("disposition")
        steps = workflows.get(owner)
        if (
            steps is None
            or isinstance(index, bool)
            or not isinstance(index, int)
            or not 1 <= index <= len(steps)
            or (owner, index) in seen
            or disposition not in STEP_DISPOSITIONS
        ):
            raise ResearchIncomplete(
                claim_id,
                "step_coverage entries need a unique 1-based step_index into this claim's or an absorbed "
                f"claim's workflow.steps and a disposition in {sorted(STEP_DISPOSITIONS)}",
            )
        seen.add((owner, index))
        step = steps[index - 1].get("step") if isinstance(steps[index - 1], dict) else None
        if disposition == "unconfirmed":
            raise ResearchIncomplete(claim_id, f"workflow step {owner}#{index} is unconfirmed: {step}")
        if disposition in {"excluded", "external_dependency"}:
            if not _is_nonempty_text(entry.get("reason")):
                raise ResearchIncomplete(claim_id, f"{disposition} step {owner}#{index} needs a reason")
            record = {"claim_id": owner, "step_index": index, "step": step, "reason": entry["reason"]}
            (excluded if disposition == "excluded" else external).append(record)
    missing = [
        f"{owner}#{index}"
        for owner, steps in workflows.items()
        for index in range(1, len(steps) + 1)
        if (owner, index) not in seen
    ]
    if missing:
        raise ResearchIncomplete(claim_id, f"workflow steps without step_coverage: {', '.join(missing)}")
    return {
        "scope": "partial_workflow" if excluded else "whole_workflow",
        "excluded_steps": excluded,
        "external_dependencies": external,
    }


def _validate_scenario_tests(claim_id: str, scenario: dict[str, Any]) -> None:
    tests = scenario.get("tests")
    if not isinstance(tests, list):
        raise ResearchIncomplete(claim_id, f"scenario {scenario['id']} tests must be a list")
    kinds = set()
    for case in tests:
        kind = research_test_kind(case)
        if kind is None or "input" not in case:
            raise ResearchIncomplete(
                claim_id,
                "each scenario test needs an input and a kind, or an id of normal, boundary, "
                "or insufficient-information",
            )
        kinds.add(kind)
    missing = REQUIRED_SCENARIO_TEST_KINDS - kinds
    if missing:
        raise ResearchIncomplete(
            claim_id,
            f"scenario {scenario['id']} lacks {', '.join(sorted(missing))} tests",
        )


def _validate_summary(value: dict[str, Any], claims: list[Any]) -> None:
    summary = value.get("summary")
    if not isinstance(summary, dict):
        return
    counts = {"ready": 0, "partial": 0, "blocked": 0}
    for claim in claims:
        second_pass = claim.get("second_pass") if isinstance(claim, dict) else None
        status = (second_pass or {}).get("readiness", {}).get("status") if isinstance(second_pass, dict) else None
        if status in counts:
            counts[status] += 1
    for status, count in counts.items():
        recorded = summary.get(f"{status}_count")
        if recorded is not None and recorded != count:
            raise ValueError(
                f"research summary {status}_count is {recorded} but claims record {count}; "
                "recompute the summary from claim readiness"
            )


def _research_agent_claims(
    value: dict[str, Any],
    *,
    model_runtime: str | None,
    fragment_root: Path | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    company = value.get("company")
    claims = value.get("claims")
    if (
        value.get("schema_version") not in {1, 2}
        or not isinstance(company, dict)
        or not _is_nonempty_text(company.get("name"))
        or not isinstance(claims, list)
    ):
        raise ValueError("invalid company research contract")
    workflow_state = value.get("workflow")
    summary = value.get("summary")
    no_ai_claims = not claims and isinstance(summary, dict) and summary.get("next_step") == "no_ai_claims"
    if (
        not isinstance(workflow_state, dict)
        or not (workflow_state.get("status") == "pass_2_complete"
                or (no_ai_claims and workflow_state.get("status") == "pass_1_complete"))
        or not _is_nonempty_text((workflow_state.get("pass_1") or {}).get("completed_at"))
    ):
        raise ValueError(
            "RESEARCH_INCOMPLETE: research must pass finalize-pass-1 and reach pass_2_complete before implementation; "
            "only finalized no_ai_claims research can finish after pass 1"
        )
    _validate_summary(value, claims)

    by_id = {claim.get("id"): claim for claim in claims if isinstance(claim, dict)}
    absorbed: dict[str, list[str]] = {}
    for claim in claims:
        if not isinstance(claim, dict):
            raise ValueError("invalid company research claim")
        second_pass = claim.get("second_pass")
        if not isinstance(second_pass, dict) or second_pass.get("status") != "merged":
            continue
        parent_id = second_pass.get("merged_into")
        parent = by_id.get(parent_id)
        parent_pass = parent.get("second_pass") if isinstance(parent, dict) else None
        if (
            parent_id == claim.get("id")
            or not isinstance(parent_pass, dict)
            or parent_pass.get("status") == "merged"
        ):
            raise ResearchIncomplete(
                str(claim.get("id")),
                "a merged claim needs merged_into naming a researched, unmerged parent claim",
            )
        absorbed.setdefault(parent_id, []).append(claim["id"])

    prepared = []
    ledger: list[dict[str, Any]] = []
    for claim in claims:
        second_pass = claim.get("second_pass")
        readiness = second_pass.get("readiness") if isinstance(second_pass, dict) else None
        handoff = second_pass.get("handoff") if isinstance(second_pass, dict) else None
        # Pass 2 is complete only when every pass-1 claim carries its own verdict.
        if (
            not isinstance(readiness, dict)
            or readiness.get("status") not in {"ready", "partial", "blocked"}
            or not isinstance(handoff, dict)
            or handoff.get("action") not in {"build", "merge", "evidence_request", "reject"}
        ):
            raise ResearchIncomplete(
                str(claim.get("id")),
                "every pass-1 claim needs a pass-2 readiness and handoff verdict",
            )
        original = None
        if fragment_root is not None:
            original = _read_fragment(str(claim.get("id")), second_pass, fragment_root)
        _validate_revisions(str(claim.get("id")), second_pass, original)
        entry = {
            "claim_id": claim.get("id"),
            "research_status": second_pass.get("status"),
            "readiness": readiness["status"],
            "readiness_reasons": readiness.get("reasons"),
            "handoff": handoff["action"],
            "merged_into": second_pass.get("merged_into"),
            "selected_for_execution": False,
            "not_executed_reason": None,
        }
        ledger.append(entry)
        if (
            second_pass.get("status") not in {"confirmed", "refined"}
            or readiness.get("status") != "ready"
            or handoff.get("action") != "build"
        ):
            entry["not_executed_reason"] = (
                f"merged into {entry['merged_into']}" if second_pass.get("status") == "merged"
                else f"pass-2 research {second_pass.get('status')}, readiness {readiness['status']}, "
                     f"handoff {handoff['action']}"
            )
            continue
        entry["selected_for_execution"] = True

        claim_id = claim.get("id")
        scenarios = second_pass.get("replication_contract")
        if (
            not _is_nonempty_text(claim_id)
            or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", claim_id)
            or second_pass.get("claim_id", claim_id) != claim_id
            or not isinstance(scenarios, list)
            or not scenarios
        ):
            raise ValueError("invalid executable research claim")
        for scenario in scenarios:
            if (
                not isinstance(scenario, dict)
                or not _is_nonempty_text(scenario.get("id"))
                or scenario.get("self_sufficiency") not in DEPENDENCY_ORDER
                or not _is_nonempty_text(scenario.get("input"))
                or not _is_nonempty_text(scenario.get("output"))
                or not _is_text_list(
                    scenario.get("acceptance_criteria"),
                    allow_empty=False,
                )
            ):
                raise ValueError("invalid research replication scenario")
        scenario_ids = [scenario["id"] for scenario in scenarios]
        if len(set(scenario_ids)) != len(scenario_ids):
            raise ValueError("duplicate research scenario identity")
        selected_id = handoff.get("selected_scenario_id")
        priority = handoff.get("scenario_priority")
        if priority is not None and (
            not _is_text_list(priority, allow_empty=False)
            or len(set(priority)) != len(priority)
            or not set(priority) <= set(scenario_ids)
        ):
            raise ValueError("invalid researched scenario priority")
        if selected_id is not None and selected_id not in scenario_ids:
            raise ValueError("selected scenario is absent from second-pass research")
        if selected_id is not None and priority and selected_id != priority[0]:
            raise ValueError("conflicting second-pass scenario selection")
        selected_id = selected_id or (priority[0] if priority else scenario_ids[0])
        selected = next(s for s in scenarios if s["id"] == selected_id)

        _validate_findings(claim_id, second_pass)
        if not _valid_sources(selected.get("sources", []), allow_empty=True):
            raise ResearchIncomplete(claim_id, "scenario sources need a url and a non-empty excerpt")
        _validate_scenario_tests(claim_id, selected)
        confirmed = [
            _confirmed_workflow(claim_id, owner, by_id[owner])
            for owner in (claim_id, *absorbed.get(claim_id, []))
        ]
        if not confirmed[0]["steps"]:
            # Without researched steps nothing proves the contract covers the whole workflow.
            raise ResearchIncomplete(
                claim_id,
                "the confirmed workflow has no steps, so whole-workflow scope cannot be verified",
            )
        workflow_coverage = _step_coverage(
            claim_id, selected, {entry["claim_id"]: entry["steps"] for entry in confirmed},
        )
        workflow_coverage["workflows"] = [
            {key: value for key, value in entry.items() if key != "steps"} | {"step_count": len(entry["steps"])}
            for entry in confirmed
        ]
        payload = {
            "schema_version": RESEARCH_AGENT_CLAIM_SCHEMA,
            "claim_id": claim_id,
            "company": copy.deepcopy(company),
            "first_pass": copy.deepcopy(claim.get("first_pass")),
            "second_pass": copy.deepcopy(second_pass),
            "absorbed_claims": [
                {"claim_id": child, "first_pass": copy.deepcopy(by_id[child].get("first_pass"))}
                for child in absorbed.get(claim_id, [])
            ],
            "workflow_coverage": workflow_coverage,
            "selected_scenario_id": selected["id"],
            "scenario_selection": {
                "basis": (
                    "explicit_selection" if handoff.get("selected_scenario_id")
                    else "research_priority" if priority else "research_order"
                ),
                "reason": handoff.get("selection_reason"),
            },
            "execution_policy": {
                "repeat_policy": "contract",
                "budget": validate_budget(handoff.get("experiment_budget", {
                    "time_limit_seconds": None, "cost_limit": None, "stop_on_blocked": True,
                })),
            },
            "input_contract": selected["input"],
            "output_contract": selected["output"],
            "acceptance_criteria": [
                {
                    "id": f"criterion-{index:03d}",
                    "description": description,
                }
                for index, description in enumerate(
                    selected["acceptance_criteria"],
                    start=1,
                )
            ],
        }
        if model_runtime:
            payload["model_runtime"] = {
                "provider": model_runtime,
                "transport": "local_cli",
            }
        prepared.append(
            {
                "claim_id": claim_id,
                "payload": payload,
            }
        )
    # Research with no executable claim is still a complete company result.
    return prepared, ledger


def parse_second_pass(
    value: Any,
    *,
    model_runtime: str | None = None,
    fragment_root: Path | None = None,
) -> dict[str, Any]:
    """Normalize a Second-pass input to the canonical claim collection.

    ``fragment_root`` is the company research directory. Every claim's pass-2
    fragment must be present there, and a changed verdict must carry a
    revision. In-memory callers without a research directory pass ``None``;
    the file-based CLI route always verifies.
    """
    if model_runtime is not None and model_runtime not in MODEL_RUNTIMES:
        raise ValueError("invalid Replica model runtime")
    if not isinstance(value, dict):
        raise ValueError("invalid second-pass claim collection")
    if value.get("schema_version") in {1, 2}:
        canonical_claims, company_claims = _research_agent_claims(
            value,
            model_runtime=model_runtime,
            fragment_root=fragment_root,
        )
        source_claims = None
    elif value.get("schema_version") == LEGACY_SECOND_PASS_SCHEMA:
        source_claims = [value]
    elif (
        value.get("schema_version") == MULTI_SECOND_PASS_SCHEMA
        and set(value) == {"schema_version", "claims"}
        and isinstance(value.get("claims"), list)
        and value["claims"]
    ):
        source_claims = value["claims"]
    else:
        raise ValueError("invalid second-pass claim collection")
    if source_claims is not None:
        claims = [
            copy.deepcopy(
                validate_second_pass_claim(
                    claim,
                    allow_missing_implementation=True,
                )
            )
            for claim in source_claims
        ]
        canonical_claims = [
            {"claim_id": claim["replica_id"], "payload": claim}
            for claim in claims
        ]
    claim_ids = [claim["claim_id"] for claim in canonical_claims]
    seen_claim_ids: set[str] = set()
    for claim_id in claim_ids:
        if claim_id in seen_claim_ids:
            raise ValueError(f"duplicate claim identity: {claim_id}")
        seen_claim_ids.add(claim_id)
    collection = {
        "schema_version": CANONICAL_CLAIM_COLLECTION_SCHEMA,
        "claim_count": len(canonical_claims),
        "claims": canonical_claims,
    }
    if source_claims is None:
        # Every researched claim, executed or not, so results keep their denominator.
        collection["company"] = copy.deepcopy(value["company"])
        collection["company_claims"] = company_claims
        sessions = value.get("agent_sessions", [])
        # Research agents the orchestrator spawned, so their session logs can be measured later.
        if not isinstance(sessions, list) or not all(
            isinstance(s, dict) and set(s) <= {"role", "agent_id", "runtime", "claim_id"}
            and _is_nonempty_text(s.get("role")) and _is_nonempty_text(s.get("agent_id"))
            and s.get("runtime", model_runtime or "claude") in MODEL_RUNTIMES
            for s in sessions
        ):
            raise ValueError("agent_sessions must list {role, agent_id[, runtime, claim_id]} records")
        if sessions:
            collection["research_agent_sessions"] = copy.deepcopy(sessions)
    return collection
