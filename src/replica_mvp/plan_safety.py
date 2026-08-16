from __future__ import annotations

from collections.abc import Mapping
from typing import Any


MAX_STEP_TIMEOUT_SECONDS = 120
MAX_STEP_OUTPUT_BYTES = 10_000_000
PLAN_FIELDS = {"schema_version", "steps"}
STEP_FIELDS = {
    "id",
    "strategy",
    "operation",
    "depends_on",
    "access",
    "limits",
    "inputs",
    "outputs",
    "criterion_ids",
}
ACCESS_FIELDS = {"network", "external_credentials"}
LIMIT_FIELDS = {"timeout_seconds", "max_output_bytes"}


def _invalid_plan() -> dict[str, Any]:
    return {
        "status": "BLOCKED",
        "violations": [{"code": "INVALID_PLAN_SCHEMA", "step_id": ""}],
    }


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _has_valid_step_shape(step: dict[str, Any]) -> bool:
    access = step.get("access", {})
    limits = step.get("limits", {})
    return (
        set(step) <= STEP_FIELDS
        and isinstance(step.get("strategy"), str)
        and isinstance(step.get("operation"), str)
        and isinstance(step.get("depends_on"), list)
        and all(isinstance(item, str) for item in step["depends_on"])
        and isinstance(access, dict)
        and set(access) <= ACCESS_FIELDS
        and (
            "network" not in access
            or isinstance(access["network"], bool)
        )
        and (
            "external_credentials" not in access
            or _is_string_list(access["external_credentials"])
        )
        and isinstance(limits, dict)
        and set(limits) <= LIMIT_FIELDS
        and (
            "inputs" not in step
            or isinstance(step["inputs"], dict)
        )
        and (
            "outputs" not in step
            or _is_string_list(step["outputs"])
        )
        and (
            "criterion_ids" not in step
            or _is_string_list(step["criterion_ids"])
        )
    )


def _first_cyclic_step(steps: list[dict[str, Any]]) -> str | None:
    graph = {step.get("id"): step.get("depends_on", []) for step in steps}
    visited: set[Any] = set()
    active: set[Any] = set()

    def visit(step_id: Any) -> bool:
        if step_id in active:
            return True
        if step_id in visited:
            return False
        active.add(step_id)
        for dependency in graph.get(step_id, []):
            if visit(dependency):
                return True
        active.remove(step_id)
        visited.add(step_id)
        return False

    for step in steps:
        step_id = step.get("id")
        if visit(step_id):
            return str(step_id)
    return None


def assess_plan_safety(
    plan: Any,
    *,
    available_operations: set[str],
    operation_input_fields: Mapping[str, set[str]] | None = None,
    generated_component_operations: set[str] | None = None,
    generated_code_operations: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(plan, dict):
        return _invalid_plan()
    steps = plan.get("steps")
    if (
        not set(plan) <= PLAN_FIELDS
        or plan.get("schema_version") != "replica-execution-plan/v1"
        or not isinstance(steps, list)
        or not steps
        or not all(isinstance(step, dict) for step in steps)
    ):
        return _invalid_plan()
    raw_step_ids = [step.get("id") for step in steps]
    if (
        not all(isinstance(step_id, str) and step_id for step_id in raw_step_ids)
        or len(set(raw_step_ids)) != len(raw_step_ids)
        or not all(_has_valid_step_shape(step) for step in steps)
    ):
        return _invalid_plan()

    violations: list[dict[str, str]] = []
    step_ids = set(raw_step_ids)
    allowed_inputs_by_operation = operation_input_fields or {}
    allowed_generated_operations = generated_component_operations or set()
    allowed_generated_code_operations = generated_code_operations or set()
    for step in steps:
        step_id = str(step.get("id", ""))
        strategy = step.get("strategy")
        operation = step.get("operation")
        if not (
            strategy == "known_component"
            or (
                strategy == "generated_component"
                and operation in allowed_generated_operations
            )
            or (
                strategy == "generated_code"
                and operation in allowed_generated_code_operations
            )
        ):
            violations.append(
                {
                    "code": (
                        "GENERATED_CODE_FORBIDDEN"
                        if strategy == "generated_code"
                        else "GENERATED_COMPONENT_FORBIDDEN"
                    ),
                    "step_id": step_id,
                }
            )
        if operation not in available_operations:
            violations.append(
                {
                    "code": "UNAVAILABLE_OPERATION",
                    "step_id": step_id,
                }
            )
        allowed_input_fields = allowed_inputs_by_operation.get(
            operation,
            set(),
        )
        if not set(step.get("inputs", {})) <= allowed_input_fields:
            violations.append(
                {
                    "code": "UNDECLARED_OPERATION_INPUT",
                    "step_id": step_id,
                }
            )
        if step.get("access", {}).get("network") is not False:
            violations.append(
                {
                    "code": "NETWORK_ACCESS_FORBIDDEN",
                    "step_id": step_id,
                }
            )
        if step.get("access", {}).get("external_credentials") != []:
            violations.append(
                {
                    "code": "EXTERNAL_CREDENTIALS_FORBIDDEN",
                    "step_id": step_id,
                }
            )
        limits = step.get("limits", {})
        if not (
            _is_positive_int(limits.get("timeout_seconds"))
            and _is_positive_int(limits.get("max_output_bytes"))
        ):
            violations.append(
                {
                    "code": "RESOURCE_LIMITS_REQUIRED",
                    "step_id": step_id,
                }
            )
        elif (
            limits["timeout_seconds"] > MAX_STEP_TIMEOUT_SECONDS
            or limits["max_output_bytes"] > MAX_STEP_OUTPUT_BYTES
        ):
            violations.append(
                {
                    "code": "RESOURCE_LIMITS_EXCEEDED",
                    "step_id": step_id,
                }
            )
        if any(dependency not in step_ids for dependency in step.get("depends_on", [])):
            violations.append(
                {
                    "code": "UNKNOWN_DEPENDENCY",
                    "step_id": step_id,
                }
            )

    cyclic_step = _first_cyclic_step(steps)
    if cyclic_step is not None:
        violations.append(
            {
                "code": "CYCLIC_DEPENDENCY",
                "step_id": cyclic_step,
            }
        )

    return {
        "status": "BLOCKED" if violations else "SAFE_TO_EXECUTE",
        "violations": violations,
    }
