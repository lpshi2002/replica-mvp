import unittest
from unittest.mock import patch

from replica_mvp import generated_component
from replica_mvp.generated_component import (
    execute_generated_component,
    make_generation_request,
    prepare_generated_component,
)


def _second_pass(output_type="object"):
    return {
        "replica_id": "operator-expansion",
        "capability": "deterministic data transformation",
        "canonical_claim": "Transforms supplied structured input.",
        "input_contract": {"type": "object"},
        "output_contract": {"type": output_type},
        "acceptance_criteria": ["The declared transformation is deterministic."],
        "supported_scope": ["Supplied structured input only."],
        "unsupported_scope": ["External data and side effects."],
        "limitations": ["Restricted expression language."],
        "implementation": {
            "instructions": "Implement the declared deterministic transformation."
        },
    }


def _prepare_and_execute(expression, runtime_input, *, output_type="object"):
    second_pass = _second_pass(output_type)

    def generator(request):
        return {
            "schema_version": "replica-component-generation/v1",
            "generator_identity": "operator-test-generator/v1",
            "component": {
                "schema_version": "replica-generated-component/v1",
                "language": "replica-expression/v1",
                "input_contract": request["input_contract"],
                "output_contract": request["output_contract"],
                "expression": expression,
            },
        }

    record = prepare_generated_component(second_pass, generator)
    return execute_generated_component(record["component"], runtime_input)


class ExpandedExpressionOperatorTest(unittest.TestCase):
    def test_advertises_the_runtime_value_limit_to_generators(self):
        request = make_generation_request(_second_pass())

        self.assertEqual(
            1_000_000,
            request["component_language"]["languages"][
                "replica-expression/v1"
            ]["limits"]["max_runtime_value_bytes"],
        )

    def test_normalizes_tokenizes_and_matches_supplied_text(self):
        source = {"op": "input", "path": ["company_name"]}
        trimmed = {"op": "trim", "args": [source]}
        lowered = {"op": "lower", "args": [trimmed]}

        output = _prepare_and_execute(
            {
                "op": "object",
                "fields": {
                    "normalized": lowered,
                    "upper": {"op": "upper", "args": [trimmed]},
                    "slug": {
                        "op": "join",
                        "args": [
                            {
                                "op": "split",
                                "args": [
                                    lowered,
                                    {"op": "literal", "value": " "},
                                ],
                            },
                            {"op": "literal", "value": "-"},
                        ],
                    },
                    "renamed": {
                        "op": "replace",
                        "args": [
                            lowered,
                            {"op": "literal", "value": "labs"},
                            {"op": "literal", "value": "systems"},
                        ],
                    },
                    "starts_with_replica": {
                        "op": "starts_with",
                        "args": [lowered, {"op": "literal", "value": "replica"}],
                    },
                    "ends_with_labs": {
                        "op": "ends_with",
                        "args": [lowered, {"op": "literal", "value": "labs"}],
                    },
                },
            },
            {"company_name": "  Replica Labs  "},
        )

        self.assertEqual(
            {
                "normalized": "replica labs",
                "upper": "REPLICA LABS",
                "slug": "replica-labs",
                "renamed": "replica systems",
                "starts_with_replica": True,
                "ends_with_labs": True,
            },
            output,
        )

    def test_reads_combines_and_inspects_supplied_collections(self):
        profile = {"op": "input", "path": ["profile"]}
        tags = {"op": "input", "path": ["tags"]}

        output = _prepare_and_execute(
            {
                "op": "object",
                "fields": {
                    "name": {
                        "op": "get",
                        "args": [profile, {"op": "literal", "value": "name"}],
                    },
                    "second_tag": {
                        "op": "get",
                        "args": [tags, {"op": "literal", "value": 1}],
                    },
                    "has_ai": {
                        "op": "contains",
                        "args": [tags, {"op": "literal", "value": "ai"}],
                    },
                    "name_has_da": {
                        "op": "contains",
                        "args": [
                            {
                                "op": "get",
                                "args": [
                                    profile,
                                    {"op": "literal", "value": "name"},
                                ],
                            },
                            {"op": "literal", "value": "da"},
                        ],
                    },
                    "profile_size": {"op": "length", "args": [profile]},
                    "profile_keys": {"op": "keys", "args": [profile]},
                    "profile_values": {"op": "values", "args": [profile]},
                    "combined_tags": {
                        "op": "array_concat",
                        "args": [
                            tags,
                            {"op": "literal", "value": ["operations"]},
                        ],
                    },
                    "enriched_profile": {
                        "op": "merge",
                        "args": [
                            profile,
                            {"op": "literal", "value": {"active": True}},
                        ],
                    },
                },
            },
            {
                "profile": {"name": "Ada", "tier": "pro"},
                "tags": ["ai", "finance"],
            },
        )

        self.assertEqual(
            {
                "name": "Ada",
                "second_tag": "finance",
                "has_ai": True,
                "name_has_da": True,
                "profile_size": 2,
                "profile_keys": ["name", "tier"],
                "profile_values": ["Ada", "pro"],
                "combined_tags": ["ai", "finance", "operations"],
                "enriched_profile": {
                    "name": "Ada",
                    "tier": "pro",
                    "active": True,
                },
            },
            output,
        )

    def test_aggregates_numbers_and_applies_explicit_fallbacks(self):
        numbers = {"op": "input", "path": ["numbers"]}
        primary = {"op": "input", "path": ["primary_score"]}

        output = _prepare_and_execute(
            {
                "op": "object",
                "fields": {
                    "score": {
                        "op": "coalesce",
                        "args": [
                            primary,
                            {"op": "input", "path": ["fallback_score"]},
                        ],
                    },
                    "primary_was_null": {
                        "op": "is_null",
                        "args": [primary],
                    },
                    "total": {"op": "sum", "args": [numbers]},
                    "minimum": {"op": "minimum", "args": [numbers]},
                    "maximum": {"op": "maximum", "args": [numbers]},
                    "average": {"op": "average", "args": [numbers]},
                    "absolute_first": {
                        "op": "absolute",
                        "args": [
                            {
                                "op": "get",
                                "args": [
                                    numbers,
                                    {"op": "literal", "value": 0},
                                ],
                            }
                        ],
                    },
                    "rounded_ratio": {
                        "op": "round",
                        "args": [
                            {
                                "op": "divide",
                                "args": [
                                    {"op": "literal", "value": 10},
                                    {"op": "literal", "value": 3},
                                ],
                            },
                            {"op": "literal", "value": 2},
                        ],
                    },
                    "remainder": {
                        "op": "modulo",
                        "args": [
                            {"op": "literal", "value": 10},
                            {"op": "literal", "value": 3},
                        ],
                    },
                },
            },
            {
                "primary_score": None,
                "fallback_score": 42,
                "numbers": [-3, 5, 10],
            },
        )

        self.assertEqual(
            {
                "score": 42,
                "primary_was_null": True,
                "total": 12,
                "minimum": -3,
                "maximum": 10,
                "average": 4,
                "absolute_first": 3,
                "rounded_ratio": 3.33,
                "remainder": 1,
            },
            output,
        )

    def test_rejects_invalid_expanded_operator_inputs(self):
        invalid_expressions = [
            (
                {
                    "op": "lower",
                    "args": [{"op": "literal", "value": 1}],
                },
                "requires strings",
            ),
            (
                {
                    "op": "replace",
                    "args": [
                        {"op": "literal", "value": "text"},
                        {"op": "literal", "value": ""},
                        {"op": "literal", "value": "expanded"},
                    ],
                },
                "replace target must not be empty",
            ),
            (
                {
                    "op": "get",
                    "args": [
                        {"op": "literal", "value": []},
                        {"op": "literal", "value": -1},
                    ],
                },
                "array index is invalid",
            ),
            (
                {
                    "op": "minimum",
                    "args": [{"op": "literal", "value": []}],
                },
                "requires a non-empty array",
            ),
            (
                {
                    "op": "round",
                    "args": [
                        {"op": "literal", "value": 1.25},
                        {"op": "literal", "value": 100},
                    ],
                },
                "integer from -15 to 15",
            ),
        ]

        for expression, message in invalid_expressions:
            with self.subTest(operation=expression["op"]):
                with self.assertRaisesRegex(ValueError, message):
                    _prepare_and_execute(
                        expression,
                        {},
                        output_type="number",
                    )

    def test_rejects_operator_output_that_exceeds_runtime_value_limit(self):
        with self.assertRaisesRegex(ValueError, "runtime value limit"):
            _prepare_and_execute(
                {
                    "op": "replace",
                    "args": [
                        {"op": "input", "path": ["source"]},
                        {"op": "literal", "value": "a"},
                        {"op": "input", "path": ["replacement"]},
                    ],
                },
                {
                    "source": "a" * 2_000,
                    "replacement": "b" * 1_000,
                },
                output_type="string",
            )

    def test_array_contains_canonicalizes_the_sought_value_once(self):
        sought = {"payload": "x" * 10_000}
        canonical_bytes = generated_component._canonical_bytes
        sought_calls = 0

        def count_sought(value):
            nonlocal sought_calls
            if value is sought:
                sought_calls += 1
                if sought_calls > 2:
                    raise AssertionError(
                        "contains repeatedly canonicalized the sought value"
                    )
            return canonical_bytes(value)

        with patch(
            "replica_mvp.generated_component._canonical_bytes",
            side_effect=count_sought,
        ):
            output = _prepare_and_execute(
                {
                    "op": "contains",
                    "args": [
                        {"op": "input", "path": ["items"]},
                        {"op": "input", "path": ["sought"]},
                    ],
                },
                {
                    "items": list(range(10_000)),
                    "sought": sought,
                },
                output_type="boolean",
            )

        self.assertFalse(output)
        self.assertEqual(2, sought_calls)


if __name__ == "__main__":
    unittest.main()
