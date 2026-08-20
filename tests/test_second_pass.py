import json
import unittest
from pathlib import Path

from replica_mvp import parse_second_pass


REPOSITORY_ROOT = Path(__file__).parents[1]
LEGACY_EXAMPLE = REPOSITORY_ROOT / "examples" / "second-pass-lead-qualification.json"


def _legacy_claim():
    return json.loads(LEGACY_EXAMPLE.read_text(encoding="utf-8"))


class SecondPassParserTest(unittest.TestCase):
    def test_legacy_single_claim_normalizes_to_canonical_collection(self):
        claim = _legacy_claim()

        parsed = parse_second_pass(claim)

        self.assertEqual("replica-claim-collection/v1", parsed["schema_version"])
        self.assertEqual(1, parsed["claim_count"])
        self.assertEqual(
            [
                {
                    "claim_id": claim["replica_id"],
                    "payload": claim,
                }
            ],
            parsed["claims"],
        )

    def test_multiple_claims_normalize_without_mixing_payloads(self):
        first = _legacy_claim()
        second = _legacy_claim()
        second["replica_id"] = "growth-labs-seat-guidance"
        second["capability"] = "recommend a seat band from supplied team size"
        second["canonical_claim"] = "Recommend a seat band without enrichment."
        source = {
            "schema_version": "replica-second-pass-claim-collection/v1",
            "claims": [first, second],
        }

        parsed = parse_second_pass(source)

        self.assertEqual(2, parsed["claim_count"])
        self.assertEqual(
            ["growth-labs-lead-qualification", "growth-labs-seat-guidance"],
            [claim["claim_id"] for claim in parsed["claims"]],
        )
        self.assertEqual(
            [first["canonical_claim"], second["canonical_claim"]],
            [claim["payload"]["canonical_claim"] for claim in parsed["claims"]],
        )

    def test_invalid_claim_is_rejected(self):
        claim = _legacy_claim()
        del claim["canonical_claim"]

        with self.assertRaisesRegex(
            ValueError,
            "invalid second-pass result contract",
        ):
            parse_second_pass(
                {
                    "schema_version": "replica-second-pass-claim-collection/v1",
                    "claims": [claim],
                }
            )

    def test_legacy_claim_without_implementation_remains_supported(self):
        claim = _legacy_claim()
        del claim["implementation"]

        parsed = parse_second_pass(claim)

        self.assertEqual(claim, parsed["claims"][0]["payload"])

    def test_unsupported_claim_type_and_unsafe_identity_are_rejected(self):
        unsafe_claim = _legacy_claim()
        unsafe_claim["replica_id"] = "../claim-001"
        invalid_claims = ("not-an-object", unsafe_claim)

        for claim in invalid_claims:
            with self.subTest(claim=claim):
                with self.assertRaisesRegex(
                    ValueError,
                    "invalid second-pass result contract",
                ):
                    parse_second_pass(
                        {
                            "schema_version": (
                                "replica-second-pass-claim-collection/v1"
                            ),
                            "claims": [claim],
                        }
                    )

    def test_duplicate_claim_identity_is_rejected(self):
        claim = _legacy_claim()

        with self.assertRaisesRegex(
            ValueError,
            "duplicate claim identity: growth-labs-lead-qualification",
        ):
            parse_second_pass(
                {
                    "schema_version": "replica-second-pass-claim-collection/v1",
                    "claims": [claim, claim],
                }
            )

    def test_n_input_claims_produce_n_stable_claim_identities(self):
        claims = []
        for index in range(1, 8):
            claim = _legacy_claim()
            claim["replica_id"] = f"growth-labs-claim-{index:03d}"
            claims.append(claim)
        source = {
            "schema_version": "replica-second-pass-claim-collection/v1",
            "claims": claims,
        }

        first_parse = parse_second_pass(source)
        second_parse = parse_second_pass(source)

        expected_ids = [claim["replica_id"] for claim in claims]
        self.assertEqual(len(claims), first_parse["claim_count"])
        self.assertEqual(
            expected_ids,
            [claim["claim_id"] for claim in first_parse["claims"]],
        )
        self.assertEqual(first_parse, second_parse)

    def test_invalid_claim_collection_is_rejected_fail_closed(self):
        invalid_values = (
            [],
            {"schema_version": "replica-second-pass-claim-collection/v1"},
            {
                "schema_version": "replica-second-pass-claim-collection/v1",
                "claims": [],
            },
            {
                "schema_version": "replica-second-pass-claim-collection/v1",
                "claims": [_legacy_claim()],
                "unexpected": True,
            },
            {
                "schema_version": "replica-second-pass-claim-collection/v1",
                "claims": "not-a-list",
            },
        )

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    ValueError,
                    "invalid second-pass claim collection",
                ):
                    parse_second_pass(value)

    def test_claim_payloads_are_isolated_and_source_input_is_not_mutated(self):
        shared_scope = ["shared source value"]
        first = _legacy_claim()
        second = _legacy_claim()
        second["replica_id"] = "growth-labs-seat-guidance"
        first["supported_scope"] = shared_scope
        second["supported_scope"] = shared_scope
        source = {
            "schema_version": "replica-second-pass-claim-collection/v1",
            "claims": [first, second],
        }

        parsed = parse_second_pass(source)
        parsed["claims"][0]["payload"]["supported_scope"].append(
            "first claim only"
        )

        self.assertEqual(["shared source value"], first["supported_scope"])
        self.assertEqual(["shared source value"], second["supported_scope"])
        self.assertEqual(
            ["shared source value"],
            parsed["claims"][1]["payload"]["supported_scope"],
        )


if __name__ == "__main__":
    unittest.main()
