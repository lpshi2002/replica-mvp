import json
import unittest
from pathlib import Path

from replica_mvp import parse_second_pass


REPOSITORY_ROOT = Path(__file__).parents[1]
LEGACY_EXAMPLE = REPOSITORY_ROOT / "examples" / "second-pass-lead-qualification.json"


def _legacy_claim():
    return json.loads(LEGACY_EXAMPLE.read_text(encoding="utf-8"))


def _research():
    scenario = {
        "id": "s-commercial",
        "self_sufficiency": "commercial_api",
        "boundaries": "Text only.",
        "input": "A UTF-8 document and question.",
        "output": "A cited JSON answer.",
        "acceptance_criteria": ["Answers with a valid citation."],
        "tests": [
            {
                "id": "normal",
                "input": "example",
                "expected_behavior": "answer",
                "reference_facts": ["fact"],
            }
        ],
    }
    oss = dict(scenario)
    oss.update({"id": "s-oss", "self_sufficiency": "oss_only"})
    second_pass = {
        "claim_id": "claim-001",
        "status": "confirmed",
        "workflow": {"input": "document", "steps": [], "output": "answer"},
        "findings": {
            "impl_path": {"state": "filled", "note": "Use a local retriever."},
            "datasets_apis": {"state": "filled", "note": "Use public text."},
        },
        "readiness": {"status": "ready"},
        "handoff": {"action": "build"},
        "replication_contract": [scenario, oss],
    }
    return {
        "schema_version": 2,
        "company": {"name": "Example", "url": "https://example.com"},
        "claims": [
            {
                "id": "claim-001",
                "first_pass": {"claim": "Answers from supplied documents."},
                "second_pass": second_pass,
            },
            {
                "id": "claim-002",
                "first_pass": {"claim": "Not ready."},
                "second_pass": {
                    **second_pass,
                    "claim_id": "claim-002",
                    "readiness": {"status": "partial"},
                },
            },
        ],
    }


class SecondPassParserTest(unittest.TestCase):
    def test_company_research_preserves_the_full_ready_claim_for_sol(self):
        research = _research()

        parsed = parse_second_pass(research)

        self.assertEqual(1, parsed["claim_count"])
        claim = parsed["claims"][0]
        payload = claim["payload"]
        self.assertEqual("claim-001", claim["claim_id"])
        self.assertEqual("replica-agent-claim/v2", payload["schema_version"])
        self.assertEqual("s-oss", payload["selected_scenario_id"])
        self.assertEqual(
            research["claims"][0]["second_pass"],
            payload["second_pass"],
        )
        self.assertEqual(
            "Use a local retriever.",
            payload["second_pass"]["findings"]["impl_path"]["note"],
        )
        self.assertEqual(
            [{"id": "criterion-001", "description": "Answers with a valid citation."}],
            payload["acceptance_criteria"],
        )

    def test_model_runtime_does_not_replace_the_self_sufficient_scenario(self):
        parsed = parse_second_pass(_research(), model_runtime="claude")

        payload = parsed["claims"][0]["payload"]
        self.assertEqual("s-oss", payload["selected_scenario_id"])
        self.assertEqual(
            {"provider": "claude", "transport": "local_cli"},
            payload["model_runtime"],
        )

    def test_unknown_model_runtime_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "model runtime"):
            parse_second_pass(_research(), model_runtime="other")

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
