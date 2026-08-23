from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, NoReturn


OPERATOR_INSTRUCTION = "replica-operator-instruction/v1"
BUILDER_FEEDBACK = "replica-builder-feedback/v1"
OPERATOR_EXECUTION_INSTRUCTION = "replica-operator-execution-instruction/v1"
BUILDER_EXECUTION_FEEDBACK = "replica-builder-execution-feedback/v1"

_COMMON_FIELDS = {
    "message_type",
    "claim_id",
    "sender_agent_id",
    "recipient_agent_id",
    "pair_nonce",
    "correction_number",
}
_OPERATOR_FIELDS = _COMMON_FIELDS | {
    "objective",
    "replication_strategy",
    "implementation_instructions",
    "implementation_actions",
    "expected_result",
    "expected_artifact",
    "validation_expectations",
}
_BUILDER_FIELDS = _COMMON_FIELDS | {
    "execution_status",
    "test_status",
    "failed_checks",
    "error",
    "observed_behavior",
    "artifact_state",
    "relevant_diagnostics",
}
_EXECUTION_OPERATOR_FIELDS = _OPERATOR_FIELDS | {
    "success_criteria",
    "responds_to_feedback_sha256",
    "correction_changes",
}
_EXECUTION_BUILDER_FIELDS = _BUILDER_FIELDS | {
    "validation_results",
    "test_summary",
}


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _reject_nonstandard_constant(value: str) -> NoReturn:
    raise ValueError(f"non-standard JSON constant: {value}")


def _require_text(value: Any, field: str) -> None:
    if not _is_text(value):
        raise ValueError(f"protocol field must be non-empty text: {field}")


def _require_text_list(value: Any, field: str) -> None:
    if (
        not isinstance(value, list)
        or not value
        or not all(_is_text(item) for item in value)
    ):
        raise ValueError(f"protocol field must be a non-empty text list: {field}")


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _require_builder_namespace_path(value: Any, claim_id: str) -> None:
    _require_text(value, "artifact path")
    prefix = f"claims/{claim_id}/builder/"
    if (
        not value.startswith(prefix)
        or "\\" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError("artifact path must remain inside the claim Builder namespace")


def _candidate_paths(claim_id: str) -> set[str]:
    prefix = f"claims/{claim_id}/builder/"
    return {
        f"{prefix}operator.json",
        f"{prefix}implementation/manifest.json",
    }


def _validate_operator_instruction(
    message: dict[str, Any],
    claim_id: str,
) -> None:
    if set(message) != _OPERATOR_FIELDS:
        raise ValueError("malformed Operator instruction fields")
    for field in (
        "objective",
        "replication_strategy",
        "expected_result",
    ):
        _require_text(message.get(field), field)
    _require_text_list(
        message.get("implementation_instructions"),
        "implementation_instructions",
    )
    _require_text_list(
        message.get("validation_expectations"),
        "validation_expectations",
    )
    actions = message.get("implementation_actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError("implementation_actions must be a non-empty list")
    for action in actions:
        if not isinstance(action, dict) or set(action) != {
            "action_type",
            "content",
        }:
            raise ValueError("malformed implementation action")
        if action.get("action_type") not in {"code", "patch", "execute"}:
            raise ValueError("invalid implementation action type")
        _require_text(action.get("content"), "implementation action content")
    artifact = message.get("expected_artifact")
    if not isinstance(artifact, dict) or set(artifact) != {
        "path",
        "description",
    }:
        raise ValueError("malformed expected_artifact")
    _require_builder_namespace_path(artifact.get("path"), claim_id)
    _require_text(
        artifact.get("description"),
        "expected_artifact.description",
    )


def _validate_execution_criteria(value: Any) -> None:
    fields = {"id", "what", "why", "pass_condition", "fail_condition"}
    if not isinstance(value, list) or not value:
        raise ValueError("success_criteria must be a non-empty list")
    criterion_ids = []
    for criterion in value:
        if not isinstance(criterion, dict) or set(criterion) != fields:
            raise ValueError("malformed success criterion")
        for field in fields:
            _require_text(criterion.get(field), f"success_criteria.{field}")
        criterion_ids.append(criterion["id"])
    if len(set(criterion_ids)) != len(criterion_ids):
        raise ValueError("success criterion ids must be unique")


def _validate_execution_instruction(
    message: dict[str, Any],
    claim_id: str,
) -> None:
    if set(message) != _EXECUTION_OPERATOR_FIELDS:
        raise ValueError("malformed Operator execution instruction fields")
    base = {field: message[field] for field in _OPERATOR_FIELDS}
    base["message_type"] = OPERATOR_INSTRUCTION
    _validate_operator_instruction(base, claim_id)
    if message["expected_artifact"]["path"] not in _candidate_paths(claim_id):
        raise ValueError(
            "execution candidate must be Builder operator.json or "
            "implementation/manifest.json"
        )
    _validate_execution_criteria(message.get("success_criteria"))
    correction_number = message.get("correction_number")
    responds_to = message.get("responds_to_feedback_sha256")
    changes = message.get("correction_changes")
    if correction_number == 0:
        if responds_to is not None or changes != []:
            raise ValueError("initial instruction cannot claim a correction")
    elif not _is_sha256(responds_to):
        raise ValueError("correction must reference prior feedback sha256")
    else:
        _require_text_list(changes, "correction_changes")


def _validate_builder_feedback(
    message: dict[str, Any],
    claim_id: str,
) -> None:
    if set(message) != _BUILDER_FIELDS:
        raise ValueError("malformed Builder feedback fields")
    execution_status = message.get("execution_status")
    test_status = message.get("test_status")
    if execution_status not in {"succeeded", "failed", "blocked"}:
        raise ValueError("invalid Builder execution_status")
    if test_status not in {"passed", "failed", "not_run"}:
        raise ValueError("invalid Builder test_status")
    failed_checks = message.get("failed_checks")
    diagnostics = message.get("relevant_diagnostics")
    if not isinstance(failed_checks, list) or not all(
        _is_text(item) for item in failed_checks
    ):
        raise ValueError("failed_checks must be a text list")
    if not isinstance(diagnostics, list) or not all(
        _is_text(item) for item in diagnostics
    ):
        raise ValueError("relevant_diagnostics must be a text list")
    error = message.get("error")
    if error is not None:
        if not isinstance(error, dict) or set(error) != {
            "error_type",
            "message",
        }:
            raise ValueError("malformed Builder error")
        _require_text(error.get("error_type"), "error.error_type")
        _require_text(error.get("message"), "error.message")
    _require_text(message.get("observed_behavior"), "observed_behavior")
    artifacts = message.get("artifact_state")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("artifact_state must be a non-empty list")
    for artifact in artifacts:
        if not isinstance(artifact, dict) or set(artifact) != {
            "path",
            "status",
            "details",
        }:
            raise ValueError("malformed artifact_state entry")
        _require_builder_namespace_path(artifact.get("path"), claim_id)
        if artifact.get("status") not in {
            "created",
            "updated",
            "unchanged",
            "missing",
        }:
            raise ValueError("invalid artifact_state status")
        _require_text(artifact.get("details"), "artifact_state.details")
    if (
        execution_status == "succeeded"
        and test_status == "passed"
        and (failed_checks or error is not None)
    ):
        raise ValueError("successful Builder feedback cannot contain failure state")
    if execution_status != "succeeded" or test_status != "passed":
        if not failed_checks and error is None and not diagnostics:
            raise ValueError("unsuccessful Builder feedback requires diagnostics")


def _validate_execution_feedback(
    message: dict[str, Any],
    claim_id: str,
) -> None:
    if set(message) != _EXECUTION_BUILDER_FIELDS:
        raise ValueError("malformed Builder execution feedback fields")
    base = {field: message[field] for field in _BUILDER_FIELDS}
    base["message_type"] = BUILDER_FEEDBACK
    _validate_builder_feedback(base, claim_id)
    if not any(
        artifact["path"] in _candidate_paths(claim_id)
        for artifact in message["artifact_state"]
    ):
        raise ValueError(
            "Builder feedback must report operator.json or implementation/manifest.json"
        )
    results = message.get("validation_results")
    result_fields = {"criterion_id", "passed", "evidence"}
    if not isinstance(results, list) or not results:
        raise ValueError("validation_results must be a non-empty list")
    criterion_ids = []
    for result in results:
        if not isinstance(result, dict) or set(result) != result_fields:
            raise ValueError("malformed validation result")
        _require_text(result.get("criterion_id"), "validation criterion_id")
        if not isinstance(result.get("passed"), bool):
            raise ValueError("validation result passed must be boolean")
        _require_text(result.get("evidence"), "validation evidence")
        criterion_ids.append(result["criterion_id"])
    if len(set(criterion_ids)) != len(criterion_ids):
        raise ValueError("validation criterion ids must be unique")
    summary = message.get("test_summary")
    if not isinstance(summary, dict) or set(summary) != {
        "passed",
        "failed",
        "total",
        "kinds",
        "test_suite_sha256",
        "judge_identity",
        "judge_mode",
    }:
        raise ValueError("malformed test_summary")
    counts = [summary.get(field) for field in ("passed", "failed", "total")]
    if any(type(count) is not int or count < 0 for count in counts):
        raise ValueError("test_summary counts must be non-negative integers")
    if summary["passed"] + summary["failed"] != summary["total"]:
        raise ValueError("test_summary counts do not add up")
    _require_text_list(summary.get("kinds"), "test_summary.kinds")
    if not _is_sha256(summary.get("test_suite_sha256")):
        raise ValueError("test_summary requires a frozen suite sha256")
    _require_text(summary.get("judge_identity"), "test_summary.judge_identity")
    if summary.get("judge_mode") not in {
        "independent",
        "same_session",
        "not_required",
    }:
        raise ValueError("invalid test_summary judge_mode")


def validate_agent_protocol_message(
    message: Any,
    *,
    claim_id: str,
    operator_agent_id: str,
    builder_agent_id: str,
    pair_nonce: str,
    expected_correction_number: int | None = None,
) -> dict[str, Any]:
    """Validate one direct sibling message against its immutable pair binding."""
    if not isinstance(message, dict):
        raise ValueError("Agent protocol message must be a JSON object")
    message_type = message.get("message_type")
    if message_type not in {
        OPERATOR_INSTRUCTION,
        BUILDER_FEEDBACK,
        OPERATOR_EXECUTION_INSTRUCTION,
        BUILDER_EXECUTION_FEEDBACK,
    }:
        raise ValueError("unsupported Agent protocol message type")
    if message.get("claim_id") != claim_id:
        raise ValueError("Agent protocol claim identity mismatch")
    if message_type in {OPERATOR_INSTRUCTION, OPERATOR_EXECUTION_INSTRUCTION}:
        sender_agent_id = operator_agent_id
        recipient_agent_id = builder_agent_id
        identity_error = "Operator instruction does not match sibling identities"
    else:
        sender_agent_id = builder_agent_id
        recipient_agent_id = operator_agent_id
        identity_error = "Builder feedback does not match sibling identities"
    if (
        message.get("sender_agent_id") != sender_agent_id
        or message.get("recipient_agent_id") != recipient_agent_id
    ):
        raise ValueError(identity_error)
    if message.get("pair_nonce") != pair_nonce:
        raise ValueError("Agent protocol pair nonce mismatch")
    correction_number = message.get("correction_number")
    if (
        not isinstance(correction_number, int)
        or isinstance(correction_number, bool)
        or correction_number < 0
    ):
        raise ValueError("correction_number must be a non-negative integer")
    if (
        expected_correction_number is not None
        and correction_number != expected_correction_number
    ):
        raise ValueError("Agent protocol correction number mismatch")
    if message_type == OPERATOR_INSTRUCTION:
        _validate_operator_instruction(message, claim_id)
    elif message_type == BUILDER_FEEDBACK:
        _validate_builder_feedback(message, claim_id)
    elif message_type == OPERATOR_EXECUTION_INSTRUCTION:
        _validate_execution_instruction(message, claim_id)
    else:
        _validate_execution_feedback(message, claim_id)
    return deepcopy(message)


def validate_agent_protocol_message_from_path(
    message_path: Path,
    *,
    claim_id: str,
    operator_agent_id: str,
    builder_agent_id: str,
    pair_nonce: str,
    expected_correction_number: int | None = None,
) -> dict[str, Any]:
    """Read and validate one claim-scoped direct sibling message artifact."""
    try:
        message = json.loads(
            message_path.read_bytes().decode("utf-8-sig"),
            parse_constant=_reject_nonstandard_constant,
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ValueError(
            f"invalid Agent protocol JSON in {message_path}: {error}"
        ) from None
    return validate_agent_protocol_message(
        message,
        claim_id=claim_id,
        operator_agent_id=operator_agent_id,
        builder_agent_id=builder_agent_id,
        pair_nonce=pair_nonce,
        expected_correction_number=expected_correction_number,
    )
