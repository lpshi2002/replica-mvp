import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from replica_mvp import (
    advance_agent_execution,
    create_agent_execution_state,
    replica_success_criteria,
)
from replica_mvp.cli import main


CLAIM_ID = "growth-labs-lead-qualification"
OPERATOR_ID = "/root/replica_agent/operator_001"
BUILDER_ID = "/root/replica_agent/builder_001"
NONCE = "execution-nonce"


def _claim(claim_id=CLAIM_ID):
    return {
        "claim_id": claim_id,
        "input_contract": {"type": "object"},
        "output_contract": {"type": "object"},
        "acceptance_criteria": [
            {
                "id": "criterion-score",
                "description": "The score follows the frozen claim formula.",
            },
            {
                "id": "criterion-threshold",
                "description": "The approved threshold classification is exact.",
            },
        ],
    }


def _instruction(
    correction_number=0,
    *,
    responds_to=None,
    changes=None,
    claim=None,
    claim_id=CLAIM_ID,
    operator_id=OPERATOR_ID,
    builder_id=BUILDER_ID,
    nonce=NONCE,
):
    claim = _claim(claim_id) if claim is None else claim
    return {
        "message_type": "replica-operator-execution-instruction/v1",
        "claim_id": claim_id,
        "sender_agent_id": operator_id,
        "recipient_agent_id": builder_id,
        "pair_nonce": nonce,
        "objective": "Implement and validate the frozen claim contract.",
        "replication_strategy": f"Deterministic strategy {correction_number}",
        "implementation_instructions": ["Implement the claim-scoped behavior."],
        "implementation_actions": [
            {"action_type": "execute", "content": "Run the frozen suite."},
        ],
        "expected_result": "Every medium-high success criterion passes.",
        "expected_artifact": {
            "path": f"claims/{claim_id}/builder/operator.json",
            "description": "Candidate component for the final result pipeline.",
        },
        "validation_expectations": ["Run all documented success checks."],
        "success_criteria": replica_success_criteria(claim),
        "responds_to_feedback_sha256": responds_to,
        "correction_changes": [] if changes is None else changes,
        "correction_number": correction_number,
    }


def _feedback(
    correction_number=0,
    *,
    passed=True,
    claim=None,
    claim_id=CLAIM_ID,
    operator_id=OPERATOR_ID,
    builder_id=BUILDER_ID,
    nonce=NONCE,
):
    claim = _claim(claim_id) if claim is None else claim
    criteria = replica_success_criteria(claim)
    return {
        "message_type": "replica-builder-execution-feedback/v1",
        "claim_id": claim_id,
        "sender_agent_id": builder_id,
        "recipient_agent_id": operator_id,
        "pair_nonce": nonce,
        "execution_status": "succeeded",
        "test_status": "passed" if passed else "failed",
        "failed_checks": [] if passed else ["functional_correctness"],
        "error": None,
        "observed_behavior": (
            "All documented checks passed."
            if passed
            else "The normal case returned the wrong result."
        ),
        "artifact_state": [
            {
                "path": f"claims/{claim_id}/builder/operator.json",
                "status": "created" if correction_number == 0 else "updated",
                "details": "Artifact was executed against the documented suite.",
            }
        ],
        "relevant_diagnostics": (
            ["normal expected QUALIFIED but observed NOT_QUALIFIED"]
            if not passed
            else []
        ),
        "validation_results": [
            {
                "criterion_id": criterion["id"],
                "passed": passed,
                "evidence": (
                    f"Observed {criterion['id']} check result in the executed suite."
                ),
            }
            for criterion in criteria
        ],
        "test_summary": {
            "passed": len(criteria) if passed else len(criteria) - 1,
            "failed": 0 if passed else 1,
            "total": len(criteria),
            "kinds": ["normal", "boundary", "negative", "structural"],
            "test_suite_sha256": "a" * 64,
            "judge_identity": "deterministic-evaluator/v1",
            "judge_mode": "not_required",
        },
        "correction_number": correction_number,
    }


class AgentExecutionTest(unittest.TestCase):
    def test_execution_requires_the_standard_terra_candidate_path(self):
        state = create_agent_execution_state(
            claim=_claim(),
            claim_id=CLAIM_ID,
            operator_agent_id=OPERATOR_ID,
            builder_agent_id=BUILDER_ID,
            pair_nonce=NONCE,
        )
        instruction = _instruction()
        instruction["expected_artifact"]["path"] = (
            f"claims/{CLAIM_ID}/builder/replica.json"
        )
        with self.assertRaisesRegex(ValueError, "operator.json"):
            advance_agent_execution(state, instruction, _feedback())

        feedback = _feedback()
        feedback["artifact_state"][0]["path"] = (
            f"claims/{CLAIM_ID}/builder/replica.json"
        )
        with self.assertRaisesRegex(ValueError, "operator.json"):
            advance_agent_execution(state, _instruction(), feedback)

    def test_initial_attempt_passes_only_with_all_medium_high_checks(self):
        state = create_agent_execution_state(
            claim=_claim(),
            claim_id=CLAIM_ID,
            operator_agent_id=OPERATOR_ID,
            builder_agent_id=BUILDER_ID,
            pair_nonce=NONCE,
        )

        result = advance_agent_execution(state, _instruction(), _feedback())

        self.assertEqual("SUCCESS", result["status"])
        self.assertEqual("SUCCESS", result["terminal_state"])
        self.assertEqual(0, result["correction_count"])
        self.assertEqual(1, len(result["attempts"]))
        self.assertEqual("PASS", result["attempts"][0]["decision"])
        self.assertNotIn("instruction", result["attempts"][0])
        self.assertNotIn("feedback", result["attempts"][0])
        for criterion in result["success_criteria"]:
            self.assertEqual(
                {"id", "what", "why", "pass_condition", "fail_condition"},
                set(criterion),
            )
            self.assertTrue(all(criterion.values()))
        claim_criteria = {
            criterion["id"]: criterion
            for criterion in result["success_criteria"]
            if criterion["id"].startswith("claim:")
        }
        self.assertEqual(
            {
                "claim:criterion-score",
                "claim:criterion-threshold",
            },
            set(claim_criteria),
        )
        self.assertIn(
            "frozen claim formula",
            claim_criteria["claim:criterion-score"]["what"],
        )

    def test_initial_failure_then_first_correction_passes(self):
        state = create_agent_execution_state(
            claim=_claim(),
            claim_id=CLAIM_ID,
            operator_agent_id=OPERATOR_ID,
            builder_agent_id=BUILDER_ID,
            pair_nonce=NONCE,
        )
        failed = advance_agent_execution(
            state,
            _instruction(),
            _feedback(passed=False),
        )

        corrected = advance_agent_execution(
            failed,
            _instruction(
                1,
                responds_to=failed["attempts"][0]["feedback_sha256"],
                changes=["Correct the qualification threshold implementation."],
            ),
            _feedback(1),
        )

        self.assertEqual("SUCCESS", corrected["status"])
        self.assertEqual(1, corrected["correction_count"])
        self.assertEqual(["RETRY", "PASS"], [
            attempt["decision"] for attempt in corrected["attempts"]
        ])

    def test_second_or_third_correction_can_pass(self):
        for pass_at in (2, 3):
            with self.subTest(pass_at=pass_at):
                state = create_agent_execution_state(
                    claim=_claim(),
                    claim_id=CLAIM_ID,
                    operator_agent_id=OPERATOR_ID,
                    builder_agent_id=BUILDER_ID,
                    pair_nonce=NONCE,
                )
                for correction_number in range(pass_at + 1):
                    prior_hash = (
                        None
                        if correction_number == 0
                        else state["attempts"][-1]["feedback_sha256"]
                    )
                    state = advance_agent_execution(
                        state,
                        _instruction(
                            correction_number,
                            responds_to=prior_hash,
                            changes=(
                                None
                                if correction_number == 0
                                else [f"Apply correction {correction_number}."]
                            ),
                        ),
                        _feedback(
                            correction_number,
                            passed=correction_number == pass_at,
                        ),
                    )

                self.assertEqual("SUCCESS", state["status"])
                self.assertEqual(pass_at, state["correction_count"])
                self.assertEqual(pass_at + 1, len(state["attempts"]))

    def test_third_correction_failure_is_terminal_and_blocks_a_fourth(self):
        state = create_agent_execution_state(
            claim=_claim(),
            claim_id=CLAIM_ID,
            operator_agent_id=OPERATOR_ID,
            builder_agent_id=BUILDER_ID,
            pair_nonce=NONCE,
        )
        for correction_number in range(4):
            state = advance_agent_execution(
                state,
                _instruction(
                    correction_number,
                    responds_to=(
                        None
                        if correction_number == 0
                        else state["attempts"][-1]["feedback_sha256"]
                    ),
                    changes=(
                        None
                        if correction_number == 0
                        else [f"Apply correction {correction_number}."]
                    ),
                ),
                _feedback(correction_number, passed=False),
            )

        self.assertEqual("FAILED", state["status"])
        self.assertEqual("FAILED", state["terminal_state"])
        self.assertEqual(3, state["correction_count"])
        self.assertEqual(["RETRY", "RETRY", "RETRY", "FAIL"], [
            attempt["decision"] for attempt in state["attempts"]
        ])
        with self.assertRaisesRegex(ValueError, "terminal"):
            advance_agent_execution(
                state,
                _instruction(
                    4,
                    responds_to=state["attempts"][-1]["feedback_sha256"],
                    changes=["Forbidden correction 4."],
                ),
                _feedback(4, passed=True),
            )

    def test_false_success_is_rejected_by_medium_high_criteria(self):
        state = create_agent_execution_state(
            claim=_claim(),
            claim_id=CLAIM_ID,
            operator_agent_id=OPERATOR_ID,
            builder_agent_id=BUILDER_ID,
            pair_nonce=NONCE,
        )
        contradictory = _feedback()
        contradictory["validation_results"][0]["passed"] = False
        contradictory["validation_results"][0]["evidence"] = (
            "The functional comparison failed despite the aggregate status."
        )

        result = advance_agent_execution(state, _instruction(), contradictory)

        self.assertEqual("CORRECTION_REQUIRED", result["status"])
        self.assertEqual("RETRY", result["attempts"][0]["decision"])

    def test_failed_feedback_must_remain_detailed_for_the_operator(self):
        state = create_agent_execution_state(
            claim=_claim(),
            claim_id=CLAIM_ID,
            operator_agent_id=OPERATOR_ID,
            builder_agent_id=BUILDER_ID,
            pair_nonce=NONCE,
        )
        summary_only = _feedback(passed=False)
        summary_only["failed_checks"] = []
        summary_only["relevant_diagnostics"] = []

        with self.assertRaisesRegex(ValueError, "requires diagnostics"):
            advance_agent_execution(state, _instruction(), summary_only)

    def test_correction_must_reference_feedback_and_change_the_actionable_plan(self):
        state = create_agent_execution_state(
            claim=_claim(),
            claim_id=CLAIM_ID,
            operator_agent_id=OPERATOR_ID,
            builder_agent_id=BUILDER_ID,
            pair_nonce=NONCE,
        )
        failed = advance_agent_execution(
            state,
            _instruction(),
            _feedback(passed=False),
        )
        unchanged = _instruction(
            1,
            responds_to=failed["attempts"][0]["feedback_sha256"],
            changes=["Claim that the plan changed."],
        )
        unchanged["replication_strategy"] = _instruction()["replication_strategy"]

        with self.assertRaisesRegex(ValueError, "actionable plan"):
            advance_agent_execution(failed, unchanged, _feedback(1))

    def test_same_builder_is_required_for_every_execution(self):
        state = create_agent_execution_state(
            claim=_claim(),
            claim_id=CLAIM_ID,
            operator_agent_id=OPERATOR_ID,
            builder_agent_id=BUILDER_ID,
            pair_nonce=NONCE,
        )
        replaced_builder = _feedback()
        replaced_builder["sender_agent_id"] = "/root/replica_agent/builder_002"

        with self.assertRaisesRegex(ValueError, "sibling identities"):
            advance_agent_execution(state, _instruction(), replaced_builder)

    def test_tampered_execution_counter_fails_closed(self):
        state = create_agent_execution_state(
            claim=_claim(),
            claim_id=CLAIM_ID,
            operator_agent_id=OPERATOR_ID,
            builder_agent_id=BUILDER_ID,
            pair_nonce=NONCE,
        )
        state["status"] = "CORRECTION_REQUIRED"
        state["next_correction_number"] = 1

        with self.assertRaisesRegex(ValueError, "invalid Agent execution state"):
            advance_agent_execution(state, _instruction(1), _feedback(1))

    def test_tampered_terminal_pass_counts_fail_closed(self):
        state = create_agent_execution_state(
            claim=_claim(),
            claim_id=CLAIM_ID,
            operator_agent_id=OPERATOR_ID,
            builder_agent_id=BUILDER_ID,
            pair_nonce=NONCE,
        )
        passed = advance_agent_execution(state, _instruction(), _feedback())
        passed["attempts"][0]["passed_criteria"] = 0

        with self.assertRaisesRegex(ValueError, "invalid Agent execution state"):
            advance_agent_execution(passed, _instruction(), _feedback())

    def test_one_claim_result_does_not_mutate_another_claim(self):
        first = create_agent_execution_state(
            claim=_claim(),
            claim_id=CLAIM_ID,
            operator_agent_id=OPERATOR_ID,
            builder_agent_id=BUILDER_ID,
            pair_nonce=NONCE,
        )
        second = create_agent_execution_state(
            claim=_claim("growth-labs-seat-guidance"),
            claim_id="growth-labs-seat-guidance",
            operator_agent_id="/root/replica_agent/operator_002",
            builder_agent_id="/root/replica_agent/builder_002",
            pair_nonce="other-nonce",
        )

        first_result = advance_agent_execution(first, _instruction(), _feedback())

        self.assertEqual("SUCCESS", first_result["status"])
        self.assertEqual("ACTIVE", first["status"])
        self.assertEqual("ACTIVE", second["status"])
        self.assertEqual([], second["attempts"])

    def test_cli_persists_only_sanitized_execution_state(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "execution-state.json"
            claim_path = root / "claim.json"
            instruction_path = root / "instruction-000.json"
            feedback_path = root / "feedback-000.json"
            instruction_path.write_text(
                json.dumps(_instruction()),
                encoding="utf-8",
            )
            feedback_path.write_text(
                json.dumps(_feedback()),
                encoding="utf-8",
            )
            claim_path.write_text(json.dumps(_claim()), encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    0,
                    main(
                        [
                            "agent-execution-start",
                            str(state_path),
                            str(claim_path),
                            "--claim-id",
                            CLAIM_ID,
                            "--operator-agent-id",
                            OPERATOR_ID,
                            "--builder-agent-id",
                            BUILDER_ID,
                            "--pair-nonce",
                            NONCE,
                        ]
                    ),
                )
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    0,
                    main(
                        [
                            "agent-execution-advance",
                            str(state_path),
                            str(instruction_path),
                            str(feedback_path),
                        ]
                    ),
                )

            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual("SUCCESS", persisted["status"])
            self.assertEqual(persisted, json.loads(stdout.getvalue()))
            serialized = state_path.read_text(encoding="utf-8")
            self.assertNotIn("Observed functional_correctness", serialized)
            self.assertNotIn("Implement the claim-scoped behavior", serialized)


if __name__ == "__main__":
    unittest.main()
