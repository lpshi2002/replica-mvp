from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from .agent_protocol import (
    BUILDER_EXECUTION_FEEDBACK,
    OPERATOR_EXECUTION_INSTRUCTION,
    validate_agent_protocol_message,
)
from .resources import budget_stop, timestamp, utc_now, unknown_resources, validate_budget, validate_resources


EXECUTION_SCHEMA = "replica-agent-execution/v1"
MAX_CORRECTIONS = 3
REQUIRED_TEST_KINDS = {"normal", "boundary", "negative", "structural"}

_BASE_SUCCESS_CRITERIA = (
    {
        "id": "functional_correctness",
        "what": "Supported inputs produce the contractually expected behavior.",
        "why": "A runnable artifact is not a Replica unless its core behavior works.",
        "pass_condition": "All functional checks and expected-output comparisons pass.",
        "fail_condition": "Any supported input produces an incorrect result.",
    },
    {
        "id": "structural_correctness",
        "what": "Inputs, outputs, schemas, and repeated execution obey the frozen contract.",
        "why": "Correct-looking values in an invalid or nondeterministic structure are unsafe.",
        "pass_condition": "Schema, JSON validity, and deterministic repeat checks all pass.",
        "fail_condition": "The shape is invalid, non-JSON, or changes for identical input.",
    },
    {
        "id": "claim_correspondence",
        "what": "Executable checks cover every required acceptance criterion in the claim.",
        "why": "Passing unrelated tests can otherwise create a false Replica success.",
        "pass_condition": "Every required claim criterion maps to at least one passing check.",
        "fail_condition": "A required criterion is uncovered or has a failing mapped check.",
    },
    {
        "id": "artifact_validity",
        "what": "The produced artifact is parseable, loadable, and executable as declared.",
        "why": "File existence alone does not show that the artifact can be used.",
        "pass_condition": "Artifact validation and a real execution through its entrypoint pass.",
        "fail_condition": "The artifact is missing, malformed, unloadable, or not executable.",
    },
    {
        "id": "negative_failure_behavior",
        "what": "Insufficient, malformed, and unsupported inputs fail in the bounded contract form.",
        "why": "A Replica must not invent values or silently succeed on invalid input.",
        "pass_condition": "Relevant negative cases return the specified bounded failure behavior.",
        "fail_condition": "Invalid input crashes, invents data, or incorrectly reports success.",
    },
    {
        "id": "boundary_edge_behavior",
        "what": "Frozen boundaries and relevant edge cases preserve the expected semantics.",
        "why": "Threshold and empty-value bugs commonly survive normal-case tests.",
        "pass_condition": "All boundary and selected edge checks pass.",
        "fail_condition": "Any boundary or relevant edge check fails.",
    },
)


def replica_success_criteria(claim: Mapping[str, Any]) -> list[dict[str, str]]:
    """Design a Medium-High contract from one immutable claim."""
    if not isinstance(claim, Mapping):
        raise ValueError("success criteria require an immutable claim object")
    acceptance = claim.get("acceptance_criteria")
    if not isinstance(acceptance, list) or not acceptance:
        raise ValueError("claim requires non-empty acceptance_criteria")
    derived = []
    seen_ids = set()
    for criterion in acceptance:
        if (
            not isinstance(criterion, Mapping)
            or not _is_text(criterion.get("id"))
            or not _is_text(criterion.get("description"))
            or criterion["id"] in seen_ids
        ):
            raise ValueError("invalid claim acceptance criterion")
        seen_ids.add(criterion["id"])
        derived.append(
            {
                "id": f"claim:{criterion['id']}",
                "what": criterion["description"],
                "why": "This behavior is required by the immutable claim acceptance contract.",
                "pass_condition": (
                    f"At least one executable check mapped to {criterion['id']} passes."
                ),
                "fail_condition": (
                    f"No executable check covers {criterion['id']}, or a mapped check fails."
                ),
            }
        )
    criteria = deepcopy(list(_BASE_SUCCESS_CRITERIA) + derived)
    if claim.get("execution_policy", {}).get("repeat_policy") == "contract":
        criteria[1].update({
            "why": "Required facts, structure and deterministic fields must survive repeated execution.",
            "pass_condition": "Schema and contract invariants pass on every repeat; prose may vary.",
            "fail_condition": "A required fact, citation, permission, calculation or side-effect invariant fails.",
        })
    return criteria


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _reject_nonstandard_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _canonical_sha256(value: Any) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError):
        raise ValueError("execution message must contain standard JSON") from None
    return hashlib.sha256(encoded).hexdigest()


def _instruction_plan_sha256(instruction: Mapping[str, Any]) -> str:
    return _canonical_sha256(
        {
            field: instruction[field]
            for field in (
                "replication_strategy",
                "implementation_instructions",
                "implementation_actions",
                "expected_result",
                "expected_artifact",
                "validation_expectations",
            )
        }
    )


def _criteria_are_documented(criteria: Any) -> bool:
    fields = {"id", "what", "why", "pass_condition", "fail_condition"}
    return bool(
        isinstance(criteria, list)
        and criteria
        and all(
            isinstance(criterion, dict)
            and set(criterion) == fields
            and all(_is_text(criterion.get(field)) for field in fields)
            for criterion in criteria
        )
        and len({criterion["id"] for criterion in criteria}) == len(criteria)
    )


def create_agent_execution_state(
    *,
    claim: Mapping[str, Any],
    claim_id: str,
    operator_agent_id: str,
    builder_agent_id: str,
    pair_nonce: str,
) -> dict[str, Any]:
    """Create one Operator-owned execution loop for an immutable sibling pair."""
    if not all(
        _is_text(value)
        for value in (claim_id, operator_agent_id, builder_agent_id, pair_nonce)
    ):
        raise ValueError("execution loop requires non-empty pair identity")
    if operator_agent_id == builder_agent_id:
        raise ValueError("execution loop requires distinct sibling identities")
    claim_identity = claim.get("claim_id", claim.get("replica_id"))
    if claim_identity != claim_id:
        raise ValueError("execution loop claim identity mismatch")
    state = {
        "schema_version": EXECUTION_SCHEMA,
        "claim_id": claim_id,
        "operator_agent_id": operator_agent_id,
        "builder_agent_id": builder_agent_id,
        "pair_nonce": pair_nonce,
        "claim_sha256": _canonical_sha256(claim),
        "status": "ACTIVE",
        "success_criteria": replica_success_criteria(claim),
        "attempts": [],
        "next_correction_number": 0,
        "correction_count": 0,
        "terminal_state": None,
    }
    state.update({
        "started_at": utc_now(),
        "budget": deepcopy(validate_budget(claim.get("execution_policy", {}).get("budget", {
            "time_limit_seconds": None, "cost_limit": None, "stop_on_blocked": True,
        }))),
        "stop_reason": None,
    })
    return state


def _validate_state(state: Any) -> dict[str, Any]:
    fields = {
        "schema_version",
        "claim_id",
        "operator_agent_id",
        "builder_agent_id",
        "pair_nonce",
        "claim_sha256",
        "status",
        "success_criteria",
        "attempts",
        "next_correction_number",
        "correction_count",
        "terminal_state",
    }
    if (
        not isinstance(state, dict)
        or set(state) not in (fields, fields | {"started_at", "budget", "stop_reason"},
                             fields | {"started_at", "budget", "stop_reason", "prior_resources"})
        or state.get("schema_version") != EXECUTION_SCHEMA
        or not _criteria_are_documented(state.get("success_criteria"))
        or not _is_sha256(state.get("claim_sha256"))
        or not isinstance(state.get("attempts"), list)
        or type(state.get("next_correction_number")) is not int
        or type(state.get("correction_count")) is not int
        or not all(
            _is_text(state.get(field))
            for field in (
                "claim_id",
                "operator_agent_id",
                "builder_agent_id",
                "pair_nonce",
            )
        )
    ):
        raise ValueError("invalid Agent execution state")
    status = state.get("status")
    if "budget" in state:
        validate_budget(state["budget"])
        timestamp(state["started_at"])
    if not isinstance(state.get("prior_resources", []), list):
        raise ValueError("invalid prior development resources")
    for resources in state.get("prior_resources", []):
        validate_resources(resources)
    attempts = state["attempts"]
    next_number = state["next_correction_number"]
    correction_count = state["correction_count"]
    terminal_state = state.get("terminal_state")
    if status == "ACTIVE":
        valid_lifecycle = (
            not attempts
            and next_number == 0
            and correction_count == 0
            and terminal_state is None
        )
    elif status == "CORRECTION_REQUIRED":
        valid_lifecycle = (
            1 <= next_number <= MAX_CORRECTIONS
            and len(attempts) == next_number
            and correction_count == next_number - 1
            and terminal_state is None
            and all(attempt.get("decision") == "RETRY" for attempt in attempts)
        )
    elif status == "SUCCESS":
        valid_lifecycle = (
            0 <= correction_count <= MAX_CORRECTIONS
            and next_number == correction_count
            and len(attempts) == correction_count + 1
            and terminal_state == "SUCCESS"
            and attempts[-1].get("decision") == "PASS"
        )
    elif status == "FAILED":
        valid_lifecycle = (
            next_number == correction_count
            and 0 <= correction_count <= MAX_CORRECTIONS
            and len(attempts) == correction_count + 1
            and terminal_state == "FAILED"
            and attempts[-1].get("decision") == "FAIL"
            and (correction_count == MAX_CORRECTIONS or bool(state.get("stop_reason")))
        )
    else:
        valid_lifecycle = False
    attempt_fields = {
        "correction_number",
        "candidate_path",
        "instruction_sha256",
        "instruction_plan_sha256",
        "feedback_sha256",
        "execution_status",
        "test_status",
        "failed_check_count",
        "test_suite_sha256",
        "judge_identity",
        "judge_mode",
        "passed_criteria",
        "total_criteria",
        "decision",
    }
    legacy_attempt_fields = attempt_fields - {"candidate_path"}
    criteria_count = len(state["success_criteria"])
    valid_attempts = True
    for index, attempt in enumerate(attempts):
        valid_attempt = (
            isinstance(attempt, dict)
            and frozenset(set(attempt) - {"resources", "stop_reason", "recorded_at"})
            in {frozenset(attempt_fields), frozenset(legacy_attempt_fields)}
            and attempt.get("correction_number") == index
            and _is_text(
                attempt.get(
                    "candidate_path",
                    f"claims/{state['claim_id']}/builder/operator.json",
                )
            )
            and all(
                _is_sha256(attempt.get(field))
                for field in (
                    "instruction_sha256",
                    "instruction_plan_sha256",
                    "feedback_sha256",
                    "test_suite_sha256",
                )
            )
            and type(attempt.get("failed_check_count")) is int
            and attempt["failed_check_count"] >= 0
            and type(attempt.get("passed_criteria")) is int
            and 0 <= attempt["passed_criteria"] <= criteria_count
            and attempt.get("total_criteria") == criteria_count
            and attempt.get("execution_status") in {"succeeded", "failed", "blocked"}
            and attempt.get("test_status") in {"passed", "failed", "not_run"}
            and _is_text(attempt.get("judge_identity"))
            and attempt.get("judge_mode")
            in {"independent", "same_session", "not_required"}
            and attempt.get("decision") in {"RETRY", "PASS", "FAIL"}
        )
        if valid_attempt and attempt["decision"] == "PASS":
            valid_attempt = (
                attempt["execution_status"] == "succeeded"
                and attempt["test_status"] == "passed"
                and attempt["failed_check_count"] == 0
                and attempt["passed_criteria"] == criteria_count
            )
        if valid_attempt and "candidate_path" not in attempt:
            attempt["candidate_path"] = (
                f"claims/{state['claim_id']}/builder/operator.json"
            )
        if not valid_attempt:
            valid_attempts = False
            break
        if "resources" in attempt:
            validate_resources(attempt["resources"])
            timestamp(attempt.get("recorded_at"))
    if not valid_lifecycle or not valid_attempts:
        raise ValueError("invalid Agent execution state")
    return deepcopy(state)


def _criteria_pass(
    feedback: Mapping[str, Any],
    success_criteria: list[dict[str, str]],
) -> bool:
    results = feedback["validation_results"]
    expected_ids = [criterion["id"] for criterion in success_criteria]
    if [result["criterion_id"] for result in results] != expected_ids:
        raise ValueError("Builder validation results do not match success criteria")
    summary = feedback["test_summary"]
    return bool(
        all(result["passed"] for result in results)
        and summary["failed"] == 0
        and summary["passed"] == summary["total"]
        and summary["total"] >= len(results)
        and REQUIRED_TEST_KINDS <= set(summary["kinds"])
    )


def _attempt_passed(
    feedback: Mapping[str, Any],
    criteria_passed: bool,
) -> bool:
    artifact_states = [artifact["status"] for artifact in feedback["artifact_state"]]
    return bool(
        feedback["execution_status"] == "succeeded"
        and feedback["test_status"] == "passed"
        and not feedback["failed_checks"]
        and feedback["error"] is None
        and artifact_states
        and all(status != "missing" for status in artifact_states)
        and criteria_passed
    )


def advance_agent_execution(
    state: Mapping[str, Any],
    instruction: Any,
    feedback: Any,
) -> dict[str, Any]:
    """Validate one direct attempt and return only sanitized loop metadata."""
    current = _validate_state(state)
    if current.get("status") not in {"ACTIVE", "CORRECTION_REQUIRED"}:
        raise ValueError("Agent execution loop is terminal")
    correction_number = current["next_correction_number"]
    if correction_number > MAX_CORRECTIONS:
        raise ValueError("fourth correction is forbidden")
    binding = {
        "claim_id": current["claim_id"],
        "operator_agent_id": current["operator_agent_id"],
        "builder_agent_id": current["builder_agent_id"],
        "pair_nonce": current["pair_nonce"],
        "expected_correction_number": correction_number,
    }
    validated_instruction = validate_agent_protocol_message(instruction, **binding)
    validated_feedback = validate_agent_protocol_message(feedback, **binding)
    if validated_instruction["message_type"] != OPERATOR_EXECUTION_INSTRUCTION:
        raise ValueError("execution loop requires an Operator execution instruction")
    if validated_feedback["message_type"] != BUILDER_EXECUTION_FEEDBACK:
        raise ValueError("execution loop requires Builder execution feedback")
    if validated_instruction["success_criteria"] != current["success_criteria"]:
        raise ValueError("Operator changed the frozen success criteria")
    candidate_path = validated_instruction["expected_artifact"]["path"]
    if not any(
        artifact["path"] == candidate_path
        for artifact in validated_feedback["artifact_state"]
    ):
        raise ValueError("Builder feedback does not match the instructed candidate")

    instruction_sha256 = _canonical_sha256(validated_instruction)
    instruction_plan_sha256 = _instruction_plan_sha256(validated_instruction)
    feedback_sha256 = _canonical_sha256(validated_feedback)
    if correction_number > 0:
        prior_attempt = current["attempts"][-1]
        if (
            validated_instruction["responds_to_feedback_sha256"]
            != prior_attempt["feedback_sha256"]
        ):
            raise ValueError("correction does not reference prior Builder feedback")
        if instruction_plan_sha256 == prior_attempt["instruction_plan_sha256"]:
            raise ValueError("correction did not change the actionable plan")

    criteria_passed = _criteria_pass(
        validated_feedback,
        current["success_criteria"],
    )
    passed = _attempt_passed(validated_feedback, criteria_passed)
    resources = deepcopy(validated_feedback.get("resources", unknown_resources()))
    stop_reason = validated_feedback.get("stop_reason")
    if "budget" in current:
        stop = budget_stop(current["budget"], current["started_at"],
                           current.get("prior_resources", []) +
                           [a.get("resources", unknown_resources()) for a in current["attempts"]] + [resources])
        if stop:
            stop_reason = {"category": "budget_exhausted", "reason": stop,
                           "evidence": ["Frozen budget and recorded resource observations."]}
        elif validated_feedback["execution_status"] == "blocked" and current["budget"]["stop_on_blocked"]:
            stop_reason = stop_reason or {
                "category": "environment_error", "reason": "Builder reported a blocking requirement.",
                "evidence": ["Bound Builder feedback; see its diagnostics."],
            }
    if stop_reason and "budget" in current:
        passed = False
        decision = "FAIL"
        current["status"] = current["terminal_state"] = "FAILED"
        current["stop_reason"] = deepcopy(stop_reason)
    elif passed:
        decision = "PASS"
        current["status"] = "SUCCESS"
        current["terminal_state"] = "SUCCESS"
    elif correction_number < MAX_CORRECTIONS:
        decision = "RETRY"
        current["status"] = "CORRECTION_REQUIRED"
        current["next_correction_number"] = correction_number + 1
    else:
        decision = "FAIL"
        current["status"] = "FAILED"
        current["terminal_state"] = "FAILED"

    current["correction_count"] = correction_number
    current["attempts"].append(
        {
            "correction_number": correction_number,
            "candidate_path": candidate_path,
            "instruction_sha256": instruction_sha256,
            "instruction_plan_sha256": instruction_plan_sha256,
            "feedback_sha256": feedback_sha256,
            "execution_status": validated_feedback["execution_status"],
            "test_status": validated_feedback["test_status"],
            "failed_check_count": len(validated_feedback["failed_checks"]),
            "test_suite_sha256": validated_feedback["test_summary"][
                "test_suite_sha256"
            ],
            "judge_identity": validated_feedback["test_summary"][
                "judge_identity"
            ],
            "judge_mode": validated_feedback["test_summary"]["judge_mode"],
            "passed_criteria": sum(
                result["passed"]
                for result in validated_feedback["validation_results"]
            ),
            "total_criteria": len(validated_feedback["validation_results"]),
            "decision": decision,
            "resources": resources,
            "stop_reason": deepcopy(stop_reason),
            "recorded_at": utc_now(),
        }
    )
    return current


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_bytes().decode("utf-8-sig"),
            parse_constant=_reject_nonstandard_constant,
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label} JSON in {path}: {error}") from None
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _write_state(path: Path, state: Mapping[str, Any], *, new: bool) -> None:
    target = path if new else path.with_name(f".{path.name}.tmp")
    mode = "x" if new else "w"
    with target.open(mode, encoding="utf-8", newline="\n") as stream:
        json.dump(
            state,
            stream,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        stream.write("\n")
    if not new:
        target.replace(path)


def create_agent_execution_state_file(
    state_path: Path,
    claim_path: Path,
    *,
    claim_id: str,
    operator_agent_id: str,
    builder_agent_id: str,
    pair_nonce: str,
) -> dict[str, Any]:
    """Create a new Operator-owned execution state file without replacement."""
    claim = _read_json_object(claim_path, "immutable claim")
    state = create_agent_execution_state(
        claim=claim,
        claim_id=claim_id,
        operator_agent_id=operator_agent_id,
        builder_agent_id=builder_agent_id,
        pair_nonce=pair_nonce,
    )
    _write_state(state_path, state, new=True)
    return state


def advance_agent_execution_from_paths(
    state_path: Path,
    instruction_path: Path,
    feedback_path: Path,
) -> dict[str, Any]:
    """Atomically advance an Operator-owned state from two direct messages."""
    state = _read_json_object(state_path, "Agent execution state")
    instruction = _read_json_object(instruction_path, "Operator instruction")
    feedback = _read_json_object(feedback_path, "Builder feedback")
    advanced = advance_agent_execution(state, instruction, feedback)
    _write_state(state_path, advanced, new=False)
    return advanced


def check_agent_execution_budget(state_path: Path) -> dict[str, Any]:
    """Control-only preflight before the Operator starts another bounded action."""
    state = _validate_state(_read_json_object(state_path, "Agent execution state"))
    if "budget" not in state:
        return {"allowed": state["status"] in {"ACTIVE", "CORRECTION_REQUIRED"}, "stop_reason": None, "remaining_seconds": None}
    resources = state.get("prior_resources", []) + [a.get("resources", unknown_resources()) for a in state["attempts"]]
    reason = budget_stop(state["budget"], state["started_at"], resources)
    limit = state["budget"]["time_limit_seconds"]
    remaining = max(0, limit - (datetime.now(timezone.utc) - timestamp(state["started_at"])).total_seconds()) if limit is not None else None
    return {"allowed": reason is None and state["status"] in {"ACTIVE", "CORRECTION_REQUIRED"},
            "stop_reason": reason, "remaining_seconds": remaining}


def load_agent_execution_state_file(
    state_path: Path,
    claim: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    """Load a terminal state and bind it to the immutable claim digest."""
    try:
        raw = state_path.read_bytes()
    except OSError as error:
        raise ValueError(f"cannot read Agent execution state: {error}") from None
    state = _validate_state(_read_json_object(state_path, "Agent execution state"))
    if (
        state["claim_sha256"] != _canonical_sha256(claim)
        or state["success_criteria"] != replica_success_criteria(claim)
        or ("execution_policy" in claim and state.get("budget") != claim["execution_policy"]["budget"])
    ):
        raise ValueError("Agent execution state does not match immutable claim")
    return state, hashlib.sha256(raw).hexdigest()
