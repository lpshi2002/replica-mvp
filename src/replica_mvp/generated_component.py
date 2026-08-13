from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping
from typing import Any, NoReturn

from .python_component import (
    PYTHON_COMPONENT_LANGUAGE,
    execute_python_component,
    python_language_contract,
    validate_python_component_source,
)


ComponentGenerator = Callable[[dict[str, Any]], Any]

MAX_EXPRESSION_DEPTH = 32
MAX_EXPRESSION_NODES = 512
MAX_COMPONENT_BYTES = 100_000
MAX_RUNTIME_VALUE_BYTES = 1_000_000
MAX_GENERATION_ATTEMPTS = 3
GENERATION_FIELDS = {
    "schema_version",
    "generator_identity",
    "component",
}
EXPRESSION_COMPONENT_FIELDS = {
    "schema_version",
    "language",
    "input_contract",
    "output_contract",
    "expression",
}
PYTHON_COMPONENT_FIELDS = {
    "schema_version",
    "language",
    "input_contract",
    "output_contract",
    "source",
}
RECORD_FIELDS = {
    "schema_version",
    "generator_identity",
    "request_sha256",
    "component_sha256",
    "request",
    "component",
}
REQUEST_FIELDS = {
    "schema_version",
    "replica_id",
    "capability",
    "canonical_claim",
    "input_contract",
    "output_contract",
    "acceptance_criteria",
    "supported_scope",
    "unsupported_scope",
    "limitations",
    "implementation_instructions",
    "component_language",
    "attempt_context",
}
EXPRESSION_OPERATORS = {
    "input",
    "literal",
    "missing",
    "object",
    "array",
    "if",
    "not",
    "equal",
    "greater_than",
    "greater_than_or_equal",
    "less_than",
    "less_than_or_equal",
    "add",
    "subtract",
    "multiply",
    "divide",
    "concat",
    "and",
    "or",
    "lower",
    "upper",
    "trim",
    "replace",
    "split",
    "join",
    "starts_with",
    "ends_with",
    "length",
    "contains",
    "get",
    "keys",
    "values",
    "merge",
    "array_concat",
    "coalesce",
    "is_null",
    "sum",
    "minimum",
    "maximum",
    "average",
    "absolute",
    "round",
    "modulo",
}
EXACT_UNARY_OPERATORS = {
    "lower",
    "upper",
    "trim",
    "length",
    "keys",
    "values",
    "is_null",
    "sum",
    "minimum",
    "maximum",
    "average",
    "absolute",
}
EXACT_BINARY_OPERATORS = {
    "equal",
    "greater_than",
    "greater_than_or_equal",
    "less_than",
    "less_than_or_equal",
    "subtract",
    "divide",
    "split",
    "join",
    "starts_with",
    "ends_with",
    "contains",
    "get",
    "round",
    "modulo",
}
EXACT_TERNARY_OPERATORS = {
    "replace",
}
VARIABLE_ARGUMENT_OPERATORS = {
    "add",
    "multiply",
    "concat",
    "and",
    "or",
    "merge",
    "array_concat",
    "coalesce",
}


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError):
        raise ValueError("generated component must contain standard JSON") from None


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _reject_nonstandard_constant(value: str) -> NoReturn:
    raise ValueError(f"non-standard JSON constant: {value}")


def _is_nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_path(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(_is_nonempty_text(segment) for segment in value)
    )


def _component_language_contract() -> dict[str, Any]:
    return {
        "schema_version": "replica-component-languages/v2",
        "preferred_order": [
            "replica-expression/v1",
            PYTHON_COMPONENT_LANGUAGE,
        ],
        "languages": {
            "replica-expression/v1": {
                "expression_field": "expression",
                "allowed_operators": sorted(EXPRESSION_OPERATORS),
                "limits": {
                    "max_depth": MAX_EXPRESSION_DEPTH,
                    "max_nodes": MAX_EXPRESSION_NODES,
                    "max_component_bytes": MAX_COMPONENT_BYTES,
                    "max_runtime_value_bytes": MAX_RUNTIME_VALUE_BYTES,
                },
            },
            PYTHON_COMPONENT_LANGUAGE: python_language_contract(),
        },
    }


def _default_attempt_context() -> dict[str, Any]:
    return {
        "attempt": 1,
        "max_attempts": MAX_GENERATION_ATTEMPTS,
        "previous_attempt": None,
    }


def _is_valid_attempt_context(value: Any) -> bool:
    if (
        not isinstance(value, dict)
        or set(value) != {"attempt", "max_attempts", "previous_attempt"}
        or type(value.get("attempt")) is not int
        or not 1 <= value["attempt"] <= MAX_GENERATION_ATTEMPTS
        or value.get("max_attempts") != MAX_GENERATION_ATTEMPTS
    ):
        return False
    previous = value["previous_attempt"]
    if value["attempt"] == 1:
        return previous is None
    return (
        isinstance(previous, dict)
        and set(previous) == {"language", "status", "passed", "total"}
        and _is_nonempty_text(previous.get("language"))
        and previous.get("status")
        in {
            "VALIDATION_FAILED",
            "RUNTIME_FAILED",
            "EVALUATION_FAILED",
        }
        and (
            previous["status"] != "EVALUATION_FAILED"
            and previous.get("passed") is None
            and previous.get("total") is None
            or previous["status"] == "EVALUATION_FAILED"
            and type(previous.get("passed")) is int
            and type(previous.get("total")) is int
            and 0 <= previous["passed"] < previous["total"]
        )
    )


def make_generation_request(
    second_pass: Mapping[str, Any],
    *,
    attempt_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    implementation = second_pass["implementation"]
    request = {
        "schema_version": "replica-component-generation-request/v1",
        "replica_id": second_pass["replica_id"],
        "capability": second_pass["capability"],
        "canonical_claim": second_pass["canonical_claim"],
        "input_contract": second_pass["input_contract"],
        "output_contract": second_pass["output_contract"],
        "acceptance_criteria": second_pass["acceptance_criteria"],
        "supported_scope": second_pass["supported_scope"],
        "unsupported_scope": second_pass["unsupported_scope"],
        "limitations": second_pass["limitations"],
        "implementation_instructions": implementation["instructions"],
        "component_language": _component_language_contract(),
        "attempt_context": (
            dict(attempt_context)
            if attempt_context is not None
            else _default_attempt_context()
        ),
    }
    return json.loads(_canonical_bytes(request))


def _validate_generation_request(
    request: Any,
    *,
    input_contract: Mapping[str, Any],
    output_contract: Mapping[str, Any],
) -> dict[str, Any]:
    if (
        not isinstance(request, dict)
        or set(request) != REQUEST_FIELDS
        or request.get("schema_version")
        != "replica-component-generation-request/v1"
        or not all(
            _is_nonempty_text(request.get(field))
            for field in (
                "replica_id",
                "capability",
                "canonical_claim",
                "implementation_instructions",
            )
        )
        or request.get("input_contract") != input_contract
        or request.get("output_contract") != output_contract
        or request.get("component_language") != _component_language_contract()
        or not _is_valid_attempt_context(request.get("attempt_context"))
        or not isinstance(request.get("acceptance_criteria"), list)
        or not all(
            isinstance(request.get(field), list)
            for field in (
                "supported_scope",
                "unsupported_scope",
                "limitations",
            )
        )
    ):
        raise ValueError("invalid generated component request")
    return request


def _validate_expression(expression: Any) -> None:
    node_count = 0

    def visit(node: Any, depth: int) -> None:
        nonlocal node_count
        node_count += 1
        if node_count > MAX_EXPRESSION_NODES or depth > MAX_EXPRESSION_DEPTH:
            raise ValueError("generated component expression exceeds safety limits")
        if not isinstance(node, dict):
            raise ValueError("generated component expression node must be an object")
        operation = node.get("op")
        if operation not in EXPRESSION_OPERATORS:
            raise ValueError("generated component uses an unsupported operator")

        if operation == "input":
            if set(node) != {"op", "path"} or not _is_path(node.get("path")):
                raise ValueError("invalid generated input expression")
            return
        if operation == "literal":
            if set(node) != {"op", "value"}:
                raise ValueError("invalid generated literal expression")
            _canonical_bytes(node["value"])
            return
        if operation == "missing":
            paths = node.get("paths")
            if (
                set(node) != {"op", "paths"}
                or not isinstance(paths, list)
                or not paths
                or not all(_is_path(path) for path in paths)
            ):
                raise ValueError("invalid generated missing expression")
            return
        if operation == "object":
            fields = node.get("fields")
            if (
                set(node) != {"op", "fields"}
                or not isinstance(fields, dict)
                or not fields
                or not all(_is_nonempty_text(key) for key in fields)
            ):
                raise ValueError("invalid generated object expression")
            for child in fields.values():
                visit(child, depth + 1)
            return
        if operation == "array":
            items = node.get("items")
            if set(node) != {"op", "items"} or not isinstance(items, list):
                raise ValueError("invalid generated array expression")
            for child in items:
                visit(child, depth + 1)
            return
        if operation == "if":
            if set(node) != {"op", "condition", "then", "else"}:
                raise ValueError("invalid generated conditional expression")
            visit(node["condition"], depth + 1)
            visit(node["then"], depth + 1)
            visit(node["else"], depth + 1)
            return
        if operation == "not":
            if set(node) != {"op", "argument"}:
                raise ValueError("invalid generated not expression")
            visit(node["argument"], depth + 1)
            return

        arguments = node.get("args")
        required_count = (
            1
            if operation in EXACT_UNARY_OPERATORS
            else 2
            if operation in EXACT_BINARY_OPERATORS
            else 3
            if operation in EXACT_TERNARY_OPERATORS
            else None
        )
        if (
            set(node) != {"op", "args"}
            or not isinstance(arguments, list)
            or (required_count is not None and len(arguments) != required_count)
            or (
                operation in VARIABLE_ARGUMENT_OPERATORS
                and len(arguments) < 2
            )
        ):
            raise ValueError("invalid generated operator arguments")
        for child in arguments:
            visit(child, depth + 1)

    visit(expression, 1)


def _validate_component(
    component: Any,
    *,
    input_contract: Mapping[str, Any],
    output_contract: Mapping[str, Any],
) -> dict[str, Any]:
    if (
        not isinstance(component, dict)
        or component.get("schema_version")
        != "replica-generated-component/v1"
        or component.get("input_contract") != input_contract
        or component.get("output_contract") != output_contract
    ):
        raise ValueError("generated component does not match the Replica contract")
    if len(_canonical_bytes(component)) > MAX_COMPONENT_BYTES:
        raise ValueError("generated component exceeds its size limit")
    language = component.get("language")
    if language == "replica-expression/v1":
        if set(component) != EXPRESSION_COMPONENT_FIELDS:
            raise ValueError(
                "generated component does not match the Replica contract"
            )
        _validate_expression(component["expression"])
    elif language == PYTHON_COMPONENT_LANGUAGE:
        if set(component) != PYTHON_COMPONENT_FIELDS:
            raise ValueError(
                "generated component does not match the Replica contract"
            )
        validate_python_component_source(component["source"])
    else:
        raise ValueError("generated component uses an unsupported language")
    return component


def prepare_generated_component(
    second_pass: Mapping[str, Any],
    generator: ComponentGenerator,
    *,
    attempt_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    request = make_generation_request(
        second_pass,
        attempt_context=attempt_context,
    )
    _validate_generation_request(
        request,
        input_contract=second_pass["input_contract"],
        output_contract=second_pass["output_contract"],
    )
    generator_request = json.loads(_canonical_bytes(request))
    generation = generator(generator_request)
    _canonical_bytes(generation)
    if (
        not isinstance(generation, dict)
        or set(generation) != GENERATION_FIELDS
        or generation.get("schema_version")
        != "replica-component-generation/v1"
        or not _is_nonempty_text(generation.get("generator_identity"))
    ):
        raise ValueError("invalid component generator result")
    component = _validate_component(
        generation["component"],
        input_contract=second_pass["input_contract"],
        output_contract=second_pass["output_contract"],
    )
    return {
        "schema_version": "replica-generated-component-record/v1",
        "generator_identity": generation["generator_identity"],
        "request_sha256": _digest(request),
        "component_sha256": _digest(component),
        "request": request,
        "component": component,
    }


def validate_generated_component_record(
    value: Any,
    *,
    input_contract: Mapping[str, Any],
    output_contract: Mapping[str, Any],
) -> dict[str, Any]:
    _canonical_bytes(value)
    if (
        not isinstance(value, dict)
        or set(value) != RECORD_FIELDS
        or value.get("schema_version")
        != "replica-generated-component-record/v1"
        or not _is_nonempty_text(value.get("generator_identity"))
        or value.get("request_sha256") != _digest(value.get("request"))
    ):
        raise ValueError("invalid generated component record")
    _validate_generation_request(
        value.get("request"),
        input_contract=input_contract,
        output_contract=output_contract,
    )
    component = _validate_component(
        value.get("component"),
        input_contract=input_contract,
        output_contract=output_contract,
    )
    if value.get("component_sha256") != _digest(component):
        raise ValueError("generated component digest does not match")
    return value


def _read_path(runtime_input: Mapping[str, Any], path: list[str]) -> tuple[bool, Any]:
    current: Any = runtime_input
    for segment in path:
        if not isinstance(current, Mapping) or segment not in current:
            return False, None
        current = current[segment]
    return True, current


def _require_number(value: Any) -> int | float:
    if type(value) is int:
        return value
    if type(value) is not float or not math.isfinite(value):
        raise ValueError("generated arithmetic requires finite numbers")
    return value


def _require_boolean(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError("generated logical expression requires booleans")
    return value


def _require_text(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("generated text expression requires strings")
    return value


def _require_text_array(value: Any) -> list[str]:
    if (
        not isinstance(value, list)
        or not all(isinstance(item, str) for item in value)
    ):
        raise ValueError("generated join requires an array of strings")
    return value


def _require_array(value: Any, operation: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"generated {operation} requires arrays")
    return value


def _require_object(value: Any, operation: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"generated {operation} requires objects")
    return value


def _require_number_array(value: Any, operation: str) -> list[int | float]:
    values = _require_array(value, operation)
    return [_require_number(item) for item in values]


def _json_equal(left: Any, right: Any) -> bool:
    return _canonical_bytes(left) == _canonical_bytes(right)


def _ensure_runtime_value_limit(value: Any) -> Any:
    if len(_canonical_bytes(value)) > MAX_RUNTIME_VALUE_BYTES:
        raise ValueError(
            "generated component exceeded its runtime value limit"
        )
    return value


def _validate_generated_output(
    output: Any,
    output_contract: Mapping[str, Any],
) -> Any:
    expected_type = output_contract["type"]
    valid_type = {
        "object": isinstance(output, dict),
        "array": isinstance(output, list),
        "string": isinstance(output, str),
        "number": type(output) in {int, float},
        "boolean": isinstance(output, bool),
        "null": output is None,
    }.get(expected_type, False)
    if not valid_type:
        raise ValueError("generated component output violates its contract")
    _ensure_runtime_value_limit(output)
    return output


def execute_generated_component(
    component: Mapping[str, Any],
    runtime_input: Mapping[str, Any],
) -> Any:
    if component.get("language") == PYTHON_COMPONENT_LANGUAGE:
        return _validate_generated_output(
            execute_python_component(component["source"], runtime_input),
            component["output_contract"],
        )

    def evaluate(node: Mapping[str, Any]) -> Any:
        return _ensure_runtime_value_limit(evaluate_unchecked(node))

    def evaluate_unchecked(node: Mapping[str, Any]) -> Any:
        operation = node["op"]
        if operation == "input":
            found, value = _read_path(runtime_input, node["path"])
            if not found:
                raise ValueError(
                    f"generated component input is missing: {'.'.join(node['path'])}"
                )
            return value
        if operation == "literal":
            return node["value"]
        if operation == "missing":
            return [
                ".".join(path)
                for path in node["paths"]
                if not _read_path(runtime_input, path)[0]
            ]
        if operation == "object":
            result: dict[str, Any] = {}
            for key, child in node["fields"].items():
                result[key] = evaluate(child)
                _ensure_runtime_value_limit(result)
            return result
        if operation == "array":
            result = []
            for child in node["items"]:
                result.append(evaluate(child))
                _ensure_runtime_value_limit(result)
            return result
        if operation == "if":
            condition = _require_boolean(evaluate(node["condition"]))
            return evaluate(node["then"] if condition else node["else"])
        if operation == "not":
            return not _require_boolean(evaluate(node["argument"]))
        if operation == "coalesce":
            for child in node["args"]:
                value = evaluate(child)
                if value is not None:
                    return value
            return None

        arguments = [evaluate(child) for child in node["args"]]
        if operation == "equal":
            return _json_equal(arguments[0], arguments[1])
        if operation in {
            "greater_than",
            "greater_than_or_equal",
            "less_than",
            "less_than_or_equal",
        }:
            left, right = (_require_number(value) for value in arguments)
            if operation == "greater_than":
                return left > right
            if operation == "greater_than_or_equal":
                return left >= right
            if operation == "less_than":
                return left < right
            return left <= right
        if operation == "add":
            return sum(_require_number(value) for value in arguments)
        if operation == "subtract":
            return _require_number(arguments[0]) - _require_number(arguments[1])
        if operation == "multiply":
            result: int | float = 1
            for value in arguments:
                result *= _require_number(value)
            return result
        if operation == "divide":
            divisor = _require_number(arguments[1])
            if divisor == 0:
                raise ValueError("generated component cannot divide by zero")
            return _require_number(arguments[0]) / divisor
        if operation == "concat":
            if not all(isinstance(value, str) for value in arguments):
                raise ValueError("generated concat requires strings")
            if sum(len(value.encode()) for value in arguments) > (
                MAX_RUNTIME_VALUE_BYTES
            ):
                raise ValueError(
                    "generated component exceeded its runtime value limit"
                )
            return "".join(arguments)
        if operation == "and":
            return all(_require_boolean(value) for value in arguments)
        if operation == "or":
            return any(_require_boolean(value) for value in arguments)
        if operation == "lower":
            return _require_text(arguments[0]).lower()
        if operation == "upper":
            return _require_text(arguments[0]).upper()
        if operation == "trim":
            return _require_text(arguments[0]).strip()
        if operation == "replace":
            source, old, new = (_require_text(value) for value in arguments)
            if not old:
                raise ValueError(
                    "generated replace target must not be empty"
                )
            occurrences = source.count(old)
            predicted_bytes = (
                len(source.encode())
                - occurrences * len(old.encode())
                + occurrences * len(new.encode())
            )
            if predicted_bytes > MAX_RUNTIME_VALUE_BYTES:
                raise ValueError(
                    "generated component exceeded its runtime value limit"
                )
            return source.replace(old, new)
        if operation == "split":
            source, delimiter = (
                _require_text(value) for value in arguments
            )
            if not delimiter:
                raise ValueError("generated split delimiter must not be empty")
            part_count = source.count(delimiter) + 1
            predicted_bytes = len(_canonical_bytes(source)) + (
                3 * part_count
            )
            if predicted_bytes > MAX_RUNTIME_VALUE_BYTES:
                raise ValueError(
                    "generated component exceeded its runtime value limit"
                )
            return source.split(delimiter)
        if operation == "join":
            values = _require_text_array(arguments[0])
            delimiter = _require_text(arguments[1])
            predicted_bytes = sum(len(value.encode()) for value in values)
            if values:
                predicted_bytes += (len(values) - 1) * len(
                    delimiter.encode()
                )
            if predicted_bytes > MAX_RUNTIME_VALUE_BYTES:
                raise ValueError(
                    "generated component exceeded its runtime value limit"
                )
            return delimiter.join(values)
        if operation == "starts_with":
            source, prefix = (_require_text(value) for value in arguments)
            return source.startswith(prefix)
        if operation == "ends_with":
            source, suffix = (_require_text(value) for value in arguments)
            return source.endswith(suffix)
        if operation == "length":
            value = arguments[0]
            if not isinstance(value, (str, list, Mapping)):
                raise ValueError(
                    "generated length requires a string, array, or object"
                )
            return len(value)
        if operation == "contains":
            collection, sought = arguments
            if isinstance(collection, str):
                return _require_text(sought) in collection
            if isinstance(collection, list):
                sought_bytes = _canonical_bytes(sought)
                return any(
                    _canonical_bytes(item) == sought_bytes
                    for item in collection
                )
            if isinstance(collection, Mapping):
                return _require_text(sought) in collection
            raise ValueError(
                "generated contains requires a string, array, or object"
            )
        if operation == "get":
            collection, key = arguments
            if isinstance(collection, Mapping):
                object_key = _require_text(key)
                if object_key not in collection:
                    raise ValueError("generated get object key is missing")
                return collection[object_key]
            if isinstance(collection, list):
                if type(key) is not int or not 0 <= key < len(collection):
                    raise ValueError("generated get array index is invalid")
                return collection[key]
            raise ValueError("generated get requires an array or object")
        if operation == "keys":
            return list(_require_object(arguments[0], "keys").keys())
        if operation == "values":
            return list(_require_object(arguments[0], "values").values())
        if operation == "merge":
            merged: dict[str, Any] = {}
            for value in arguments:
                merged.update(_require_object(value, "merge"))
                _ensure_runtime_value_limit(merged)
            return merged
        if operation == "array_concat":
            combined: list[Any] = []
            payload_bytes = 0
            item_count = 0
            for value in arguments:
                items = _require_array(value, "array_concat")
                payload_bytes += sum(
                    len(_canonical_bytes(item)) for item in items
                )
                item_count += len(items)
                predicted_bytes = (
                    2
                    + payload_bytes
                    + max(0, item_count - 1)
                )
                if predicted_bytes > MAX_RUNTIME_VALUE_BYTES:
                    raise ValueError(
                        "generated component exceeded its runtime value limit"
                    )
                combined.extend(items)
            return combined
        if operation == "is_null":
            return arguments[0] is None
        if operation in {"sum", "minimum", "maximum", "average"}:
            values = _require_number_array(arguments[0], operation)
            if operation != "sum" and not values:
                raise ValueError(
                    f"generated {operation} requires a non-empty array"
                )
            if operation == "sum":
                return sum(values)
            if operation == "minimum":
                return min(values)
            if operation == "maximum":
                return max(values)
            return sum(values) / len(values)
        if operation == "absolute":
            return abs(_require_number(arguments[0]))
        if operation == "round":
            value = _require_number(arguments[0])
            digits = arguments[1]
            if type(digits) is not int or not -15 <= digits <= 15:
                raise ValueError(
                    "generated round digits must be an integer from -15 to 15"
                )
            return round(value, digits)
        if operation == "modulo":
            left = _require_number(arguments[0])
            divisor = _require_number(arguments[1])
            if divisor == 0:
                raise ValueError("generated component cannot modulo by zero")
            return left % divisor
        raise ValueError("generated component uses an unsupported operator")

    return _validate_generated_output(
        evaluate(component["expression"]),
        component["output_contract"],
    )
