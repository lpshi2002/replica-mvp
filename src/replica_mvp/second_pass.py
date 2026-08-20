from __future__ import annotations

import copy
import json
import re
from typing import Any

from .completion import _valid_completion_contract
from .experience import validate_experience_profile


LEGACY_SECOND_PASS_SCHEMA = "replica-second-pass-result/v1"
MULTI_SECOND_PASS_SCHEMA = "replica-second-pass-claim-collection/v1"
CANONICAL_CLAIM_COLLECTION_SCHEMA = "replica-claim-collection/v1"
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


def parse_second_pass(value: Any) -> dict[str, Any]:
    """Normalize a Second-pass input to the canonical claim collection."""
    if not isinstance(value, dict):
        raise ValueError("invalid second-pass claim collection")
    if value.get("schema_version") == LEGACY_SECOND_PASS_SCHEMA:
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
    claims = [
        copy.deepcopy(
            validate_second_pass_claim(
                claim,
                allow_missing_implementation=True,
            )
        )
        for claim in source_claims
    ]
    claim_ids = [claim["replica_id"] for claim in claims]
    seen_claim_ids: set[str] = set()
    for claim_id in claim_ids:
        if claim_id in seen_claim_ids:
            raise ValueError(f"duplicate claim identity: {claim_id}")
        seen_claim_ids.add(claim_id)
    return {
        "schema_version": CANONICAL_CLAIM_COLLECTION_SCHEMA,
        "claim_count": len(claims),
        "claims": [
            {
                "claim_id": claim_id,
                "payload": claim,
            }
            for claim_id, claim in zip(claim_ids, claims, strict=True)
        ],
    }
