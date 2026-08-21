from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from .agent_protocol import (
    BUILDER_EXECUTION_FEEDBACK,
    OPERATOR_EXECUTION_INSTRUCTION,
    validate_agent_protocol_message,
)


EXECUTION_SCHEMA = "replica-agent-execution/v1"
MAX_CORRECTIONS = 3
REQUIRED_TEST_KINDS = {"normal", "boundary", "negative", "structural"}

_SUCCESS_CRITERIA = (
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


def replica_success_criteria() -> list[dict[str, str]]:
    """Return the documented Medium-High acceptance contract."""
    return deepcopy(list(_SUCCESS_CRITERIA))


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


def create_agent_execution_state(
    *,
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
    return {
        "schema_version": EXECUTION_SCHEMA,
        "claim_id": claim_id,
        "operator_agent_id": operator_agent_id,
        "builder_agent_id": builder_agent_id,
        "pair_nonce": pair_nonce,
        "status": "ACTIVE",
        "success_criteria": replica_success_criteria(),
        "attempts": [],
        "next_correction_number": 0,
        "correction_count": 0,
        "terminal_state": None,
    }


def _validate_state(state: Any) -> dict[str, Any]:
    fields = {
        "schema_version",
        "claim_id",
        "operator_agent_id",
        "builder_agent_id",
        "pair_nonce",
        "status",
        "success_criteria",
        "attempts",
        "next_correction_number",
        "correction_count",
        "terminal_state",
    }
    if (
        not isinstance(state, dict)
        or set(state) != fields
        or state.get("schema_version") != EXECUTION_SCHEMA
        or state.get("success_criteria") != replica_success_criteria()
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
            next_number == MAX_CORRECTIONS
            and correction_count == MAX_CORRECTIONS
            and len(attempts) == MAX_CORRECTIONS + 1
            and terminal_state == "FAILED"
            and attempts[-1].get("decision") == "FAIL"
        )
    else:
        valid_lifecycle = False
    attempt_fields = {
        "correction_number",
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
    valid_attempts = all(
        isinstance(attempt, dict)
        and set(attempt) == attempt_fields
        and attempt.get("correction_number") == index
        and all(
            _is_sha256(attempt.get(field))
            for field in (
                "instruction_sha256",
                "instruction_plan_sha256",
                "feedback_sha256",
                "test_suite_sha256",
            )
        )
        for index, attempt in enumerate(attempts)
    )
    if not valid_lifecycle or not valid_attempts:
        raise ValueError("invalid Agent execution state")
    return deepcopy(state)


def _criteria_pass(feedback: Mapping[str, Any]) -> bool:
    results = feedback["validation_results"]
    expected_ids = [criterion["id"] for criterion in _SUCCESS_CRITERIA]
    if [result["criterion_id"] for result in results] != expected_ids:
        raise ValueError("Builder validation results do not match success criteria")
    summary = feedback["test_summary"]
    return bool(
        all(result["passed"] for result in results)
        and summary["failed"] == 0
        and summary["passed"] == summary["total"]
        and summary["total"] >= len(_SUCCESS_CRITERIA)
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

    criteria_passed = _criteria_pass(validated_feedback)
    passed = _attempt_passed(validated_feedback, criteria_passed)
    if passed:
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
    *,
    claim_id: str,
    operator_agent_id: str,
    builder_agent_id: str,
    pair_nonce: str,
) -> dict[str, Any]:
    """Create a new Operator-owned execution state file without replacement."""
    state = create_agent_execution_state(
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
