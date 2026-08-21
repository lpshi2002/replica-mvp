import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from replica_mvp import (
    advance_agent_execution,
    create_agent_execution_state,
    finish_agent_continuity,
    finish_agent_harness,
    prepare_agent_harness,
    record_agent_continuity_round,
    record_agent_premature_completion,
    record_agent_spawn,
    record_direct_agent_message,
    start_agent_claim,
    start_agent_continuity,
)
from replica_mvp.cli import main
from tests.test_agent_execution import _feedback, _instruction


REPOSITORY_ROOT = Path(__file__).parents[1]
LEGACY_EXAMPLE = REPOSITORY_ROOT / "examples/second-pass-lead-qualification.json"
CLAIM_ID = "growth-labs-lead-qualification"
OPERATOR_ID = "/root/replica_agent/operator_001"
BUILDER_ID = "/root/replica_agent/builder_001"
NONCE = "continuity-nonce"


def _prepare_ready_pair(run_dir: Path) -> Path:
    registry_path = run_dir / "agent-harness.json"
    claim = json.loads(LEGACY_EXAMPLE.read_text(encoding="utf-8"))
    prepare_agent_harness(
        claim,
        run_dir,
        replica_agent_id="/root/replica_agent",
        parent_agent_id="/root",
    )
    start_agent_claim(registry_path, CLAIM_ID)
    record_agent_spawn(
        registry_path,
        CLAIM_ID,
        role="operator",
        agent_id=OPERATOR_ID,
        parent_agent_id="/root/replica_agent",
        requested_model="gpt-5.6-sol",
    )
    record_agent_spawn(
        registry_path,
        CLAIM_ID,
        role="builder",
        agent_id=BUILDER_ID,
        parent_agent_id="/root/replica_agent",
        requested_model="gpt-5.6-terra",
    )
    record_direct_agent_message(
        registry_path,
        CLAIM_ID,
        direction="operator_to_builder",
        sender_agent_id=OPERATOR_ID,
        recipient_agent_id=BUILDER_ID,
        nonce=NONCE,
    )
    record_direct_agent_message(
        registry_path,
        CLAIM_ID,
        direction="builder_to_operator",
        sender_agent_id=BUILDER_ID,
        recipient_agent_id=OPERATOR_ID,
        nonce=NONCE,
    )
    return registry_path


def _prepare_two_active_continuity_pairs(run_dir: Path) -> tuple[Path, list[dict]]:
    first = json.loads(LEGACY_EXAMPLE.read_text(encoding="utf-8"))
    second = dict(first)
    second["replica_id"] = "growth-labs-seat-guidance"
    registry_path = run_dir / "agent-harness.json"
    prepare_agent_harness(
        {
            "schema_version": "replica-second-pass-claim-collection/v1",
            "claims": [first, second],
        },
        run_dir,
        replica_agent_id="/root/replica_agent",
        parent_agent_id="/root",
    )
    bindings = []
    for index, claim_id in enumerate(
        (CLAIM_ID, "growth-labs-seat-guidance"),
        start=1,
    ):
        operator_id = f"/root/replica_agent/operator_{index:03d}"
        builder_id = f"/root/replica_agent/builder_{index:03d}"
        nonce = f"continuity-nonce-{index}"
        start_agent_claim(registry_path, claim_id)
        record_agent_spawn(
            registry_path,
            claim_id,
            role="operator",
            agent_id=operator_id,
            parent_agent_id="/root/replica_agent",
            requested_model="gpt-5.6-sol",
        )
        record_agent_spawn(
            registry_path,
            claim_id,
            role="builder",
            agent_id=builder_id,
            parent_agent_id="/root/replica_agent",
            requested_model="gpt-5.6-terra",
        )
        for direction, sender, recipient in (
            ("operator_to_builder", operator_id, builder_id),
            ("builder_to_operator", builder_id, operator_id),
        ):
            record_direct_agent_message(
                registry_path,
                claim_id,
                direction=direction,
                sender_agent_id=sender,
                recipient_agent_id=recipient,
                nonce=nonce,
            )
        start_agent_continuity(
            registry_path,
            claim_id,
            operator_agent_id=operator_id,
            builder_agent_id=builder_id,
            nonce=nonce,
        )
        bindings.append(
            {
                "claim_id": claim_id,
                "operator_agent_id": operator_id,
                "builder_agent_id": builder_id,
                "nonce": nonce,
            }
        )
    return registry_path, bindings


def _write_execution_state(
    registry_path: Path,
    binding: dict,
    *,
    terminal_state: str | None,
    correction_count: int,
) -> Path:
    claim_path = (
        registry_path.parent
        / "claims"
        / binding["claim_id"]
        / "claim.json"
    )
    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    state = create_agent_execution_state(
        claim=claim,
        claim_id=binding["claim_id"],
        operator_agent_id=binding["operator_agent_id"],
        builder_agent_id=binding["builder_agent_id"],
        pair_nonce=binding["nonce"],
    )
    for round_number in range(correction_count + 1):
        state = advance_agent_execution(
            state,
            _instruction(
                round_number,
                responds_to=(
                    None
                    if round_number == 0
                    else state["attempts"][-1]["feedback_sha256"]
                ),
                changes=(
                    None
                    if round_number == 0
                    else [f"Apply correction {round_number}."]
                ),
                claim=claim,
                claim_id=binding["claim_id"],
                operator_id=binding["operator_agent_id"],
                builder_id=binding["builder_agent_id"],
                nonce=binding["nonce"],
            ),
            _feedback(
                round_number,
                passed=(
                    terminal_state == "SUCCESS"
                    and round_number == correction_count
                ),
                claim=claim,
                claim_id=binding["claim_id"],
                operator_id=binding["operator_agent_id"],
                builder_id=binding["builder_agent_id"],
                nonce=binding["nonce"],
            ),
        )
    state_path = (
        registry_path.parent
        / "claims"
        / binding["claim_id"]
        / "operator"
        / "execution-state.json"
    )
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return state_path


class AgentContinuityTest(unittest.TestCase):
    def test_ready_pair_starts_one_long_lived_claim_session(self):
        with TemporaryDirectory() as tmp:
            registry_path = _prepare_ready_pair(Path(tmp) / "run")

            started = start_agent_continuity(
                registry_path,
                CLAIM_ID,
                operator_agent_id=OPERATOR_ID,
                builder_agent_id=BUILDER_ID,
                nonce=NONCE,
            )

            continuity = started["claims"][0]["continuity"]
            self.assertEqual("PAIR_ACTIVE", continuity["phase"])
            self.assertEqual(OPERATOR_ID, continuity["operator_agent_id"])
            self.assertEqual(BUILDER_ID, continuity["builder_agent_id"])
            self.assertEqual("ACTIVE_FOR_CLAIM", continuity["operator_status"])
            self.assertEqual("ACTIVE_FOR_CLAIM", continuity["builder_status"])
            self.assertEqual([], continuity["completed_rounds"])
            self.assertIsNone(continuity["terminal_state"])

    def test_same_pair_records_four_direct_round_trips_in_order(self):
        with TemporaryDirectory() as tmp:
            registry_path = _prepare_ready_pair(Path(tmp) / "run")
            start_agent_continuity(
                registry_path,
                CLAIM_ID,
                operator_agent_id=OPERATOR_ID,
                builder_agent_id=BUILDER_ID,
                nonce=NONCE,
            )

            current = None
            for round_number in range(4):
                current = record_agent_continuity_round(
                    registry_path,
                    CLAIM_ID,
                    round_number=round_number,
                    operator_agent_id=OPERATOR_ID,
                    builder_agent_id=BUILDER_ID,
                    nonce=NONCE,
                    operator_to_builder_direct=True,
                    builder_to_operator_direct=True,
                )

            continuity = current["claims"][0]["continuity"]
            self.assertEqual([0, 1, 2, 3], continuity["completed_rounds"])
            self.assertEqual(4, continuity["next_round"])
            self.assertEqual(3, continuity["correction_count"])
            self.assertEqual("ROUND_TRIP_COMPLETE", continuity["phase"])
            self.assertEqual(OPERATOR_ID, continuity["operator_agent_id"])
            self.assertEqual(BUILDER_ID, continuity["builder_agent_id"])
            self.assertEqual("WAITING_FOR_PEER", continuity["operator_status"])
            self.assertEqual("WAITING_FOR_PEER", continuity["builder_status"])

    def test_pair_completes_only_after_an_explicit_direct_terminal(self):
        with TemporaryDirectory() as tmp:
            registry_path = _prepare_ready_pair(Path(tmp) / "run")
            start_agent_continuity(
                registry_path,
                CLAIM_ID,
                operator_agent_id=OPERATOR_ID,
                builder_agent_id=BUILDER_ID,
                nonce=NONCE,
            )
            for round_number in range(4):
                record_agent_continuity_round(
                    registry_path,
                    CLAIM_ID,
                    round_number=round_number,
                    operator_agent_id=OPERATOR_ID,
                    builder_agent_id=BUILDER_ID,
                    nonce=NONCE,
                    operator_to_builder_direct=True,
                    builder_to_operator_direct=True,
                )

            finished = finish_agent_continuity(
                registry_path,
                CLAIM_ID,
                terminal_state="SUCCESS",
                operator_agent_id=OPERATOR_ID,
                builder_agent_id=BUILDER_ID,
                nonce=NONCE,
                terminal_acknowledged_directly=True,
            )

            continuity = finished["claims"][0]["continuity"]
            self.assertEqual("TERMINAL_SUCCESS", continuity["phase"])
            self.assertEqual("SUCCESS", continuity["terminal_state"])
            self.assertEqual("COMPLETED", continuity["operator_status"])
            self.assertEqual("COMPLETED", continuity["builder_status"])
            with self.assertRaisesRegex(ValueError, "not active"):
                record_agent_continuity_round(
                    registry_path,
                    CLAIM_ID,
                    round_number=4,
                    operator_agent_id=OPERATOR_ID,
                    builder_agent_id=BUILDER_ID,
                    nonce=NONCE,
                    operator_to_builder_direct=True,
                    builder_to_operator_direct=True,
                )

    def test_success_terminal_requires_initial_plus_three_corrections(self):
        with TemporaryDirectory() as tmp:
            registry_path = _prepare_ready_pair(Path(tmp) / "run")
            start_agent_continuity(
                registry_path,
                CLAIM_ID,
                operator_agent_id=OPERATOR_ID,
                builder_agent_id=BUILDER_ID,
                nonce=NONCE,
            )

            for round_number in range(3):
                record_agent_continuity_round(
                    registry_path,
                    CLAIM_ID,
                    round_number=round_number,
                    operator_agent_id=OPERATOR_ID,
                    builder_agent_id=BUILDER_ID,
                    nonce=NONCE,
                    operator_to_builder_direct=True,
                    builder_to_operator_direct=True,
                )
                with self.assertRaisesRegex(ValueError, "four completed rounds"):
                    finish_agent_continuity(
                        registry_path,
                        CLAIM_ID,
                        terminal_state="SUCCESS",
                        operator_agent_id=OPERATOR_ID,
                        builder_agent_id=BUILDER_ID,
                        nonce=NONCE,
                        terminal_acknowledged_directly=True,
                    )

    def test_execution_terminal_accepts_initial_pass_with_zero_corrections(self):
        with TemporaryDirectory() as tmp:
            registry_path = _prepare_ready_pair(Path(tmp) / "run")
            start_agent_continuity(
                registry_path,
                CLAIM_ID,
                operator_agent_id=OPERATOR_ID,
                builder_agent_id=BUILDER_ID,
                nonce=NONCE,
            )
            record_agent_continuity_round(
                registry_path,
                CLAIM_ID,
                round_number=0,
                operator_agent_id=OPERATOR_ID,
                builder_agent_id=BUILDER_ID,
                nonce=NONCE,
                operator_to_builder_direct=True,
                builder_to_operator_direct=True,
            )
            binding = {
                "claim_id": CLAIM_ID,
                "operator_agent_id": OPERATOR_ID,
                "builder_agent_id": BUILDER_ID,
                "nonce": NONCE,
            }
            state_path = _write_execution_state(
                registry_path,
                binding,
                terminal_state="SUCCESS",
                correction_count=0,
            )

            finished = finish_agent_continuity(
                registry_path,
                CLAIM_ID,
                terminal_state="SUCCESS",
                execution_state_path=state_path,
                operator_agent_id=OPERATOR_ID,
                builder_agent_id=BUILDER_ID,
                nonce=NONCE,
                terminal_acknowledged_directly=True,
            )

            continuity = finished["claims"][0]["continuity"]
            self.assertEqual("TERMINAL_SUCCESS", continuity["phase"])
            self.assertEqual(0, continuity["correction_count"])
            self.assertEqual("EXECUTION_SUCCESS", finished["claims"][0]["status"])
            execution_result = finished["claims"][0]["execution_result"]
            self.assertEqual("SUCCESS", execution_result["status"])
            self.assertEqual(0, execution_result["correction_count"])
            self.assertEqual([0], execution_result["completed_rounds"])
            self.assertEqual(0, execution_result["failed_check_count"])
            self.assertEqual(
                execution_result["passed_criteria"],
                execution_result["total_criteria"],
            )

            aggregate = finish_agent_harness(registry_path)
            self.assertEqual("EXECUTION_SUCCESS", aggregate["status"])

    def test_execution_failure_cannot_finish_before_correction_three(self):
        with TemporaryDirectory() as tmp:
            registry_path = _prepare_ready_pair(Path(tmp) / "run")
            start_agent_continuity(
                registry_path,
                CLAIM_ID,
                operator_agent_id=OPERATOR_ID,
                builder_agent_id=BUILDER_ID,
                nonce=NONCE,
            )
            record_agent_continuity_round(
                registry_path,
                CLAIM_ID,
                round_number=0,
                operator_agent_id=OPERATOR_ID,
                builder_agent_id=BUILDER_ID,
                nonce=NONCE,
                operator_to_builder_direct=True,
                builder_to_operator_direct=True,
            )
            binding = {
                "claim_id": CLAIM_ID,
                "operator_agent_id": OPERATOR_ID,
                "builder_agent_id": BUILDER_ID,
                "nonce": NONCE,
            }
            state_path = _write_execution_state(
                registry_path,
                binding,
                terminal_state=None,
                correction_count=0,
            )

            for claimed_terminal in ("SUCCESS", "FAILED"):
                with self.subTest(claimed_terminal=claimed_terminal):
                    with self.assertRaisesRegex(ValueError, "terminal result"):
                        finish_agent_continuity(
                            registry_path,
                            CLAIM_ID,
                            terminal_state=claimed_terminal,
                            execution_state_path=state_path,
                            operator_agent_id=OPERATOR_ID,
                            builder_agent_id=BUILDER_ID,
                            nonce=NONCE,
                            terminal_acknowledged_directly=True,
                        )

    def test_failed_claim_does_not_change_a_successful_claim(self):
        with TemporaryDirectory() as tmp:
            registry_path, bindings = _prepare_two_active_continuity_pairs(
                Path(tmp) / "run"
            )
            terminal_states = ("SUCCESS", "FAILED")
            correction_counts = (0, 3)
            for binding, terminal_state, correction_count in zip(
                bindings,
                terminal_states,
                correction_counts,
                strict=True,
            ):
                for round_number in range(correction_count + 1):
                    record_agent_continuity_round(
                        registry_path,
                        binding["claim_id"],
                        round_number=round_number,
                        operator_agent_id=binding["operator_agent_id"],
                        builder_agent_id=binding["builder_agent_id"],
                        nonce=binding["nonce"],
                        operator_to_builder_direct=True,
                        builder_to_operator_direct=True,
                    )
                state_path = _write_execution_state(
                    registry_path,
                    binding,
                    terminal_state=terminal_state,
                    correction_count=correction_count,
                )
                finish_agent_continuity(
                    registry_path,
                    binding["claim_id"],
                    terminal_state=terminal_state,
                    execution_state_path=state_path,
                    operator_agent_id=binding["operator_agent_id"],
                    builder_agent_id=binding["builder_agent_id"],
                    nonce=binding["nonce"],
                    terminal_acknowledged_directly=True,
                )

            aggregate = finish_agent_harness(registry_path)

            self.assertEqual(
                "EXECUTION_COMPLETED_WITH_FAILURES",
                aggregate["status"],
            )
            self.assertEqual(
                ["EXECUTION_SUCCESS", "EXECUTION_FAILED"],
                [claim["status"] for claim in aggregate["claims"]],
            )

    def test_premature_completion_aborts_without_replacing_the_pair(self):
        with TemporaryDirectory() as tmp:
            registry_path = _prepare_ready_pair(Path(tmp) / "run")
            start_agent_continuity(
                registry_path,
                CLAIM_ID,
                operator_agent_id=OPERATOR_ID,
                builder_agent_id=BUILDER_ID,
                nonce=NONCE,
            )

            aborted = record_agent_premature_completion(
                registry_path,
                CLAIM_ID,
                completed_agent_id=BUILDER_ID,
                reason="Builder returned final before terminal",
            )

            continuity = aborted["claims"][0]["continuity"]
            self.assertEqual("ABORTED", continuity["phase"])
            self.assertEqual("ABORTED", continuity["terminal_state"])
            self.assertEqual(OPERATOR_ID, continuity["operator_agent_id"])
            self.assertEqual(BUILDER_ID, continuity["builder_agent_id"])
            self.assertEqual("CONTINUITY_FAILED", continuity["operator_status"])
            self.assertEqual(
                "PREMATURELY_COMPLETED",
                continuity["builder_status"],
            )
            self.assertEqual(
                {
                    "agent_id": BUILDER_ID,
                    "reason": "Builder returned final before terminal",
                },
                continuity["failure"],
            )
            with self.assertRaisesRegex(ValueError, "not active"):
                record_agent_continuity_round(
                    registry_path,
                    CLAIM_ID,
                    round_number=0,
                    operator_agent_id=OPERATOR_ID,
                    builder_agent_id=BUILDER_ID,
                    nonce=NONCE,
                    operator_to_builder_direct=True,
                    builder_to_operator_direct=True,
                )

    def test_cli_records_a_four_round_session_and_terminal(self):
        with TemporaryDirectory() as tmp:
            registry_path = _prepare_ready_pair(Path(tmp) / "run")
            commands = [
                [
                    "agent-continuity-start",
                    str(registry_path),
                    CLAIM_ID,
                    "--operator-agent-id",
                    OPERATOR_ID,
                    "--builder-agent-id",
                    BUILDER_ID,
                    "--nonce",
                    NONCE,
                ],
                *[
                    [
                        "agent-continuity-round",
                        str(registry_path),
                        CLAIM_ID,
                        "--round-number",
                        str(round_number),
                        "--operator-agent-id",
                        OPERATOR_ID,
                        "--builder-agent-id",
                        BUILDER_ID,
                        "--nonce",
                        NONCE,
                        "--operator-to-builder-direct",
                        "--builder-to-operator-direct",
                    ]
                    for round_number in range(4)
                ],
                [
                    "agent-continuity-terminal",
                    str(registry_path),
                    CLAIM_ID,
                    "--terminal-state",
                    "SUCCESS",
                    "--operator-agent-id",
                    OPERATOR_ID,
                    "--builder-agent-id",
                    BUILDER_ID,
                    "--nonce",
                    NONCE,
                    "--terminal-acknowledged-directly",
                ],
            ]

            result = None
            for command in commands:
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    self.assertEqual(0, main(command))
                result = json.loads(stdout.getvalue())

            continuity = result["claims"][0]["continuity"]
            self.assertEqual([0, 1, 2, 3], continuity["completed_rounds"])
            self.assertEqual("TERMINAL_SUCCESS", continuity["phase"])

    def test_round_metadata_fails_closed_on_identity_order_or_relay(self):
        with TemporaryDirectory() as tmp:
            registry_path = _prepare_ready_pair(Path(tmp) / "run")
            start_agent_continuity(
                registry_path,
                CLAIM_ID,
                operator_agent_id=OPERATOR_ID,
                builder_agent_id=BUILDER_ID,
                nonce=NONCE,
            )

            invalid_rounds = (
                {
                    "round_number": 0,
                    "builder_agent_id": "/root/replica_agent/builder_002",
                    "operator_to_builder_direct": True,
                    "builder_to_operator_direct": True,
                    "error": "changed sibling identities",
                },
                {
                    "round_number": 1,
                    "builder_agent_id": BUILDER_ID,
                    "operator_to_builder_direct": True,
                    "builder_to_operator_direct": True,
                    "error": "out of sequence",
                },
                {
                    "round_number": 0,
                    "builder_agent_id": BUILDER_ID,
                    "operator_to_builder_direct": False,
                    "builder_to_operator_direct": True,
                    "error": "directly bidirectional",
                },
            )
            for invalid in invalid_rounds:
                with self.subTest(error=invalid["error"]):
                    with self.assertRaisesRegex(ValueError, invalid["error"]):
                        record_agent_continuity_round(
                            registry_path,
                            CLAIM_ID,
                            round_number=invalid["round_number"],
                            operator_agent_id=OPERATOR_ID,
                            builder_agent_id=invalid["builder_agent_id"],
                            nonce=NONCE,
                            operator_to_builder_direct=(
                                invalid["operator_to_builder_direct"]
                            ),
                            builder_to_operator_direct=(
                                invalid["builder_to_operator_direct"]
                            ),
                        )


if __name__ == "__main__":
    unittest.main()
