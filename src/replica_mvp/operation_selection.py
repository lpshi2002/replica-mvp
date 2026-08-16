from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any


GENERATED_COMPONENT_OPERATION = "execute_generated_component"


def _generated_component_instructions(second_pass: Mapping[str, Any]) -> str:
    evidence = {
        "canonical_claim": second_pass["canonical_claim"],
        "input_contract": second_pass["input_contract"],
        "output_contract": second_pass["output_contract"],
        "acceptance_criteria": second_pass["acceptance_criteria"],
        "supported_scope": second_pass["supported_scope"],
        "unsupported_scope": second_pass["unsupported_scope"],
        "limitations": second_pass["limitations"],
    }
    completion = second_pass.get("completion_contract")
    if isinstance(completion, Mapping):
        evidence["dependency_policy"] = {
            "dependency_level": completion.get("dependency_level"),
            "dependencies": completion.get("dependencies"),
        }
    return (
        "Implement only the deterministic capability described by this "
        "Second-pass evidence. Use only caller-supplied runtime inputs, return "
        "insufficient-information results instead of inventing missing facts, "
        "and do not add behavior outside the supported scope. Evidence:\n"
        + json.dumps(
            evidence,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    )


def select_codex_operator_implementation(
    second_pass: Mapping[str, Any],
    *,
    source_intake_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved = copy.deepcopy(dict(second_pass))
    supplied_implementation = copy.deepcopy(resolved.get("implementation"))
    instructions = _generated_component_instructions(resolved)
    if supplied_implementation is not None:
        instructions += (
            "\nTreat this Second-pass implementation only as a non-binding "
            "evidence hint; write a new component instead of selecting it:\n"
            + json.dumps(
                supplied_implementation,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        )
    implementation = {
        "strategy": "generated_component",
        "instructions": instructions,
    }
    resolved["implementation"] = implementation
    decision = {
        "schema_version": "replica-operation-selection/v1",
        "selector_identity": "codex-operator-builder/v1",
        "source_intake_sha256": source_intake_sha256,
        "mode": "codex",
        "status": "SELECTED",
        "selected": {
            "strategy": "generated_component",
            "operation": GENERATED_COMPONENT_OPERATION,
            "implementation": copy.deepcopy(implementation),
        },
        "evidence": [
            {
                "source": "second_pass_result",
                "finding": (
                    "The Codex operator workflow derives a new implementation "
                    "from the evidence-bound contract fields."
                ),
            },
            {
                "source": "codex_operator_policy",
                "finding": (
                    "Registered operations and supplied implementation choices "
                    "are not selected by this workflow."
                ),
            },
        ],
    }
    return resolved, decision
