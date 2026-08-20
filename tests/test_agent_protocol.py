import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from replica_mvp import validate_agent_protocol_message
from replica_mvp.cli import main


CLAIM_ID = "growth-labs-lead-qualification"
OPERATOR_ID = "/root/replica_agent/operator_001"
BUILDER_ID = "/root/replica_agent/builder_001"
NONCE = "claim-001-nonce"


def _operator_instruction():
    return {
        "message_type": "replica-operator-instruction/v1",
        "claim_id": CLAIM_ID,
        "sender_agent_id": OPERATOR_ID,
        "recipient_agent_id": BUILDER_ID,
        "pair_nonce": NONCE,
        "objective": "Implement the frozen claim contract.",
        "replication_strategy": "Use the deterministic supported path.",
        "implementation_instructions": [
            "Read only claim.json.",
            "Write generated files only in the Builder namespace.",
        ],
        "implementation_actions": [
            {
                "action_type": "patch",
                "content": "Add the deterministic transformation.",
            },
            {
                "action_type": "execute",
                "content": "Run the claim-scoped test command.",
            },
        ],
        "expected_result": "The frozen claim cases pass.",
        "expected_artifact": {
            "path": "claims/growth-labs-lead-qualification/builder/replica",
            "description": "Runnable Replica implementation.",
        },
        "validation_expectations": ["Run the supplied claim-scoped tests."],
        "correction_number": 0,
    }


def _builder_feedback():
    return {
        "message_type": "replica-builder-feedback/v1",
        "claim_id": CLAIM_ID,
        "sender_agent_id": BUILDER_ID,
        "recipient_agent_id": OPERATOR_ID,
        "pair_nonce": NONCE,
        "execution_status": "failed",
        "test_status": "failed",
        "failed_checks": ["test_expected_output"],
        "error": {
            "error_type": "AssertionError",
            "message": "Expected 3 rows but observed 2.",
        },
        "observed_behavior": "The transformation omitted the final input row.",
        "artifact_state": [
            {
                "path": "claims/growth-labs-lead-qualification/builder/replica",
                "status": "created",
                "details": "Runnable but the frozen test is failing.",
            }
        ],
        "relevant_diagnostics": ["Failure is deterministic across two runs."],
        "correction_number": 0,
    }


class AgentProtocolTest(unittest.TestCase):
    def test_operator_instruction_is_canonicalized_for_the_exact_builder(self):
        message = _operator_instruction()

        validated = validate_agent_protocol_message(
            message,
            claim_id=CLAIM_ID,
            operator_agent_id=OPERATOR_ID,
            builder_agent_id=BUILDER_ID,
            pair_nonce=NONCE,
        )

        self.assertEqual(message, validated)
        self.assertIsNot(message, validated)

    def test_builder_feedback_preserves_detailed_execution_observations(self):
        message = _builder_feedback()

        validated = validate_agent_protocol_message(
            message,
            claim_id=CLAIM_ID,
            operator_agent_id=OPERATOR_ID,
            builder_agent_id=BUILDER_ID,
            pair_nonce=NONCE,
        )

        self.assertEqual(message, validated)

    def test_feedback_must_match_the_active_correction_number(self):
        message = _builder_feedback()

        with self.assertRaisesRegex(ValueError, "correction number mismatch"):
            validate_agent_protocol_message(
                message,
                claim_id=CLAIM_ID,
                operator_agent_id=OPERATOR_ID,
                builder_agent_id=BUILDER_ID,
                pair_nonce=NONCE,
                expected_correction_number=1,
            )

    def test_malformed_or_summary_only_feedback_is_rejected(self):
        message = _builder_feedback()
        message["failed_checks"] = []
        message["error"] = None
        message["relevant_diagnostics"] = []

        with self.assertRaisesRegex(ValueError, "requires diagnostics"):
            validate_agent_protocol_message(
                message,
                claim_id=CLAIM_ID,
                operator_agent_id=OPERATOR_ID,
                builder_agent_id=BUILDER_ID,
                pair_nonce=NONCE,
            )

    def test_successful_feedback_cannot_contain_failure_state(self):
        message = _builder_feedback()
        message["execution_status"] = "succeeded"
        message["test_status"] = "passed"

        with self.assertRaisesRegex(ValueError, "successful Builder feedback"):
            validate_agent_protocol_message(
                message,
                claim_id=CLAIM_ID,
                operator_agent_id=OPERATOR_ID,
                builder_agent_id=BUILDER_ID,
                pair_nonce=NONCE,
            )

    def test_claim_identity_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "claim identity mismatch"):
            validate_agent_protocol_message(
                _operator_instruction(),
                claim_id="other-claim",
                operator_agent_id=OPERATOR_ID,
                builder_agent_id=BUILDER_ID,
                pair_nonce=NONCE,
            )

    def test_same_pair_is_preserved_across_a_correction(self):
        corrected_instruction = _operator_instruction()
        corrected_instruction["correction_number"] = 1
        corrected_feedback = _builder_feedback()
        corrected_feedback["correction_number"] = 1

        instruction = validate_agent_protocol_message(
            corrected_instruction,
            claim_id=CLAIM_ID,
            operator_agent_id=OPERATOR_ID,
            builder_agent_id=BUILDER_ID,
            pair_nonce=NONCE,
            expected_correction_number=1,
        )
        feedback = validate_agent_protocol_message(
            corrected_feedback,
            claim_id=CLAIM_ID,
            operator_agent_id=OPERATOR_ID,
            builder_agent_id=BUILDER_ID,
            pair_nonce=NONCE,
            expected_correction_number=1,
        )

        self.assertEqual(OPERATOR_ID, instruction["sender_agent_id"])
        self.assertEqual(BUILDER_ID, instruction["recipient_agent_id"])
        self.assertEqual(BUILDER_ID, feedback["sender_agent_id"])
        self.assertEqual(OPERATOR_ID, feedback["recipient_agent_id"])
        replacement = dict(corrected_instruction)
        replacement["recipient_agent_id"] = "/root/replica_agent/builder_002"
        with self.assertRaisesRegex(ValueError, "sibling identities"):
            validate_agent_protocol_message(
                replacement,
                claim_id=CLAIM_ID,
                operator_agent_id=OPERATOR_ID,
                builder_agent_id=BUILDER_ID,
                pair_nonce=NONCE,
                expected_correction_number=1,
            )

    def test_cross_claim_message_is_rejected(self):
        message = _builder_feedback()
        message["claim_id"] = "growth-labs-seat-guidance"
        message["sender_agent_id"] = "/root/replica_agent/builder_002"
        message["recipient_agent_id"] = "/root/replica_agent/operator_002"

        with self.assertRaisesRegex(ValueError, "claim identity mismatch"):
            validate_agent_protocol_message(
                message,
                claim_id=CLAIM_ID,
                operator_agent_id=OPERATOR_ID,
                builder_agent_id=BUILDER_ID,
                pair_nonce=NONCE,
            )

    def test_artifact_paths_cannot_escape_the_claim_builder_namespace(self):
        instruction = _operator_instruction()
        instruction["expected_artifact"]["path"] = "claims/other/builder/replica"
        feedback = _builder_feedback()
        feedback["artifact_state"][0]["path"] = "../operator/instruction-000.json"

        for message in (instruction, feedback):
            with self.subTest(message_type=message["message_type"]):
                with self.assertRaisesRegex(ValueError, "Builder namespace"):
                    validate_agent_protocol_message(
                        message,
                        claim_id=CLAIM_ID,
                        operator_agent_id=OPERATOR_ID,
                        builder_agent_id=BUILDER_ID,
                        pair_nonce=NONCE,
                    )

    def test_replica_agent_cannot_be_a_semantic_message_relay(self):
        message = _operator_instruction()
        message["recipient_agent_id"] = "/root/replica_agent"

        with self.assertRaisesRegex(ValueError, "sibling identities"):
            validate_agent_protocol_message(
                message,
                claim_id=CLAIM_ID,
                operator_agent_id=OPERATOR_ID,
                builder_agent_id=BUILDER_ID,
                pair_nonce=NONCE,
            )

    def test_operator_and_builder_message_roles_cannot_be_reversed(self):
        instruction = _operator_instruction()
        instruction["sender_agent_id"] = BUILDER_ID
        instruction["recipient_agent_id"] = OPERATOR_ID
        feedback = _builder_feedback()
        feedback["sender_agent_id"] = OPERATOR_ID
        feedback["recipient_agent_id"] = BUILDER_ID

        for message in (instruction, feedback):
            with self.subTest(message_type=message["message_type"]):
                with self.assertRaisesRegex(ValueError, "sibling identities"):
                    validate_agent_protocol_message(
                        message,
                        claim_id=CLAIM_ID,
                        operator_agent_id=OPERATOR_ID,
                        builder_agent_id=BUILDER_ID,
                        pair_nonce=NONCE,
                    )

    def test_unknown_contract_fields_are_rejected(self):
        message = _operator_instruction()
        message["replica_summary"] = "Relay this through the Replica Agent."

        with self.assertRaisesRegex(ValueError, "malformed Operator"):
            validate_agent_protocol_message(
                message,
                claim_id=CLAIM_ID,
                operator_agent_id=OPERATOR_ID,
                builder_agent_id=BUILDER_ID,
                pair_nonce=NONCE,
            )

    def test_cli_validates_a_claim_scoped_message_without_registry_mutation(self):
        with TemporaryDirectory() as tmp:
            message_path = Path(tmp) / "instruction-000.json"
            message_path.write_text(
                json.dumps(_operator_instruction()),
                encoding="utf-8",
            )
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                result = main(
                    [
                        "agent-protocol-validate",
                        str(message_path),
                        "--claim-id",
                        CLAIM_ID,
                        "--operator-agent-id",
                        OPERATOR_ID,
                        "--builder-agent-id",
                        BUILDER_ID,
                        "--pair-nonce",
                        NONCE,
                        "--expected-correction-number",
                        "0",
                    ]
                )

            self.assertEqual(0, result)
            self.assertEqual(_operator_instruction(), json.loads(stdout.getvalue()))

if __name__ == "__main__":
    unittest.main()
