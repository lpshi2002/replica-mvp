import hashlib
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from replica_mvp import (
    advance_agent_execution,
    create_agent_execution_state,
    finalize_agent_candidate,
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
from replica_mvp.agent_harness import resume_agent_continuity, retry_agent_preflight
from tests.test_agent_execution import _feedback, _instruction
from tests.test_second_pass import _research


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
        requested_model="gpt-6-astra",
        requested_reasoning_effort="medium",
    )
    record_agent_spawn(
        registry_path,
        CLAIM_ID,
        role="builder",
        agent_id=BUILDER_ID,
        parent_agent_id="/root/replica_agent",
        requested_model="gpt-5.6-terra",
        requested_reasoning_effort="high",
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


def _prepare_rich_ready_pair(run_dir: Path) -> tuple[Path, dict]:
    claim_id = "claim-001"
    operator_id = "/root/replica_agent/operator_rich"
    builder_id = "/root/replica_agent/builder_rich"
    nonce = "rich-continuity-nonce"
    registry_path = run_dir / "agent-harness.json"
    prepare_agent_harness(
        _research(),
        run_dir,
        replica_agent_id="/root/replica_agent",
        parent_agent_id="/root",
    )
    start_agent_claim(registry_path, claim_id)
    record_agent_spawn(
        registry_path,
        claim_id,
        role="operator",
        agent_id=operator_id,
        parent_agent_id="/root/replica_agent",
        requested_model="gpt-6-astra",
        requested_reasoning_effort="medium",
    )
    record_agent_spawn(
        registry_path,
        claim_id,
        role="builder",
        agent_id=builder_id,
        parent_agent_id="/root/replica_agent",
        requested_model="gpt-5.6-terra",
        requested_reasoning_effort="high",
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
    return registry_path, {
        "claim_id": claim_id,
        "operator_agent_id": operator_id,
        "builder_agent_id": builder_id,
        "nonce": nonce,
    }


def _prepare_active_continuity_pairs(run_dir: Path, *, claim_count: int = 2) -> tuple[Path, list[dict]]:
    first = json.loads(LEGACY_EXAMPLE.read_text(encoding="utf-8"))
    second = dict(first)
    second["replica_id"] = "growth-labs-seat-guidance"
    claims = [first, second]
    for index in range(3, claim_count + 1):
        claims.append({**first, "replica_id": f"growth-labs-feature-{index}"})
    registry_path = run_dir / "agent-harness.json"
    prepare_agent_harness(
        {
            "schema_version": "replica-second-pass-claim-collection/v1",
            "claims": claims,
        },
        run_dir,
        replica_agent_id="/root/replica_agent",
        parent_agent_id="/root",
    )
    bindings = []
    for index, claim_id in enumerate(
        (claim["replica_id"] for claim in claims),
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
            requested_model="gpt-6-astra",
            requested_reasoning_effort="medium",
        )
        record_agent_spawn(
            registry_path,
            claim_id,
            role="builder",
            agent_id=builder_id,
            parent_agent_id="/root/replica_agent",
            requested_model="gpt-5.6-terra",
            requested_reasoning_effort="high",
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
    candidate_path: str | None = None,
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
                candidate_path=candidate_path,
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
                candidate_path=candidate_path,
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


def _write_candidate(registry_path: Path, claim_id: str = CLAIM_ID) -> Path:
    claim_path = registry_path.parent / "claims" / claim_id / "claim.json"
    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    missing = {
        "op": "missing",
        "paths": [["annual_budget"], ["requested_seats"]],
    }
    score = {
        "op": "add",
        "args": [
            {"op": "input", "path": ["annual_budget"]},
            {
                "op": "multiply",
                "args": [
                    {"op": "input", "path": ["requested_seats"]},
                    {"op": "literal", "value": 1000},
                ],
            },
        ],
    }
    candidate = {
        "schema_version": "replica-component-generation/v1",
        "generator_identity": "terra-builder/test",
        "component": {
            "schema_version": "replica-generated-component/v1",
            "language": "replica-expression/v1",
            "input_contract": claim["input_contract"],
            "output_contract": claim["output_contract"],
            "expression": {
                "op": "if",
                "condition": {
                    "op": "greater_than",
                    "args": [
                        {"op": "length", "args": [missing]},
                        {"op": "literal", "value": 0},
                    ],
                },
                "then": {
                    "op": "object",
                    "fields": {
                        "status": {
                            "op": "literal",
                            "value": "INSUFFICIENT_INFORMATION",
                        },
                        "missing": missing,
                    },
                },
                "else": {
                    "op": "object",
                    "fields": {
                        "status": {
                            "op": "if",
                            "condition": {
                                "op": "greater_than_or_equal",
                                "args": [
                                    score,
                                    {"op": "literal", "value": 75000},
                                ],
                            },
                            "then": {"op": "literal", "value": "QUALIFIED"},
                            "else": {
                                "op": "literal",
                                "value": "NOT_QUALIFIED",
                            },
                        },
                        "score": score,
                    },
                },
            },
        },
    }
    candidate_path = (
        registry_path.parent / "claims" / claim_id / "builder" / "operator.json"
    )
    candidate_path.write_text(
        json.dumps(candidate, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return candidate_path


class AgentContinuityTest(unittest.TestCase):
    def test_company_result_distinguishes_blocked_development_from_failed_checks(self):
        for category in ("access_missing", "budget_exhausted", "development_checks_failed"):
            with self.subTest(category=category), TemporaryDirectory() as tmp:
                registry, binding = _prepare_rich_ready_pair(Path(tmp) / "run")
                start_agent_continuity(registry, **binding)
                corrections = 3 if category == "development_checks_failed" else 0
                for round_number in range(corrections + 1):
                    record_agent_continuity_round(registry, **binding, round_number=round_number,
                                                  operator_to_builder_direct=True, builder_to_operator_direct=True)
                if category == "development_checks_failed":
                    state_path = _write_execution_state(registry, binding, terminal_state="FAILED", correction_count=corrections)
                else:
                    payload = json.loads((registry.parent / "claims/claim-001/claim.json").read_text())
                    state = create_agent_execution_state(claim=payload, claim_id=binding["claim_id"],
                                                         operator_agent_id=binding["operator_agent_id"],
                                                         builder_agent_id=binding["builder_agent_id"], pair_nonce=binding["nonce"])
                    messages = {"claim": payload, "claim_id": binding["claim_id"], "operator_id": binding["operator_agent_id"],
                                "builder_id": binding["builder_agent_id"], "nonce": binding["nonce"]}
                    feedback = _feedback(passed=False, **messages)
                    reason = f"Execution stopped because of {category}."
                    feedback.update(execution_status="blocked", stop_reason={
                        "category": category, "reason": reason, "evidence": ["Private development diagnostic."],
                    })
                    state = advance_agent_execution(state, _instruction(**messages), feedback)
                    state_path = registry.parent / "claims/claim-001/operator/execution-state.json"
                    state_path.write_text(json.dumps(state))
                finish_agent_continuity(registry, **binding, terminal_state="FAILED",
                                        terminal_acknowledged_directly=True, execution_state_path=state_path)
                finished = finish_agent_harness(registry)
                result_path = registry.parent / finished["company_result"]["path"]
                result = json.loads(result_path.read_text())["claims"][0]
                self.assertEqual(category, result["failure_category"])
                self.assertIsNone(result["reproduction_status"])
                self.assertIsNone(result["result_path"])
                if category == "development_checks_failed":
                    self.assertEqual("experiment_incomplete", result["outcome"])
                    self.assertIn("3 corrections", result["failure_reason"])
                else:
                    self.assertEqual("experiment_blocked", result["outcome"])
                    self.assertEqual(reason, result["failure_reason"])
                    self.assertNotIn("Private development diagnostic", result_path.read_text())
                state_path.write_text(state_path.read_text() + "\n")
                previous_result = result_path.read_bytes()
                with self.assertRaisesRegex(ValueError, "failed development state changed"):
                    finish_agent_harness(registry)
                self.assertEqual(previous_result, result_path.read_bytes())

    def test_company_result_keeps_protocol_interruption_reason(self):
        with TemporaryDirectory() as tmp:
            registry, binding = _prepare_rich_ready_pair(Path(tmp) / "run")
            start_agent_continuity(registry, **binding)
            reason = "The Builder stopped before acknowledging a terminal result."
            record_agent_premature_completion(registry, binding["claim_id"],
                                             completed_agent_id=binding["builder_agent_id"], reason=reason)
            finished = finish_agent_harness(registry)
            result = json.loads((registry.parent / finished["company_result"]["path"]).read_text())["claims"][0]
            self.assertEqual("experiment_blocked", result["outcome"])
            self.assertEqual("agent_protocol_interrupted", result["failure_category"])
            self.assertEqual(reason, result["failure_reason"])
            self.assertIsNone(result["reproduction_status"])

    def test_delivery_resume_allows_received_feedback_awaiting_operator_decision(self):
        with TemporaryDirectory() as tmp:
            registry, binding = _prepare_rich_ready_pair(Path(tmp) / "run")
            start_agent_continuity(registry, **binding)
            payload = json.loads((registry.parent / "claims" / binding["claim_id"] / "claim.json").read_text())
            state = create_agent_execution_state(claim=payload, claim_id=binding["claim_id"],
                                                 operator_agent_id=binding["operator_agent_id"],
                                                 builder_agent_id=binding["builder_agent_id"], pair_nonce=binding["nonce"])
            state_path = registry.parent / "claims" / binding["claim_id"] / "operator/execution-state.json"
            state_path.write_text(json.dumps(state))
            record_agent_continuity_round(registry, **binding, round_number=0,
                                         operator_to_builder_direct=True, builder_to_operator_direct=True)
            record_agent_premature_completion(registry, binding["claim_id"],
                                              completed_agent_id=binding["builder_agent_id"], reason="Terminal delivery interrupted.")
            resumed = resume_agent_continuity(registry, binding["claim_id"])["claims"][0]
            self.assertEqual(1, resumed["continuity"]["next_round"])
            self.assertEqual(state, json.loads(state_path.read_text()))

    def test_delivery_resume_keeps_round_state_budget_and_one_abort_record(self):
        with TemporaryDirectory() as tmp:
            registry_path, binding = _prepare_rich_ready_pair(Path(tmp) / "run")
            start_agent_continuity(registry_path, **binding)
            record_agent_continuity_round(registry_path, **binding, round_number=0,
                                         operator_to_builder_direct=True, builder_to_operator_direct=True)
            state_path = _write_execution_state(registry_path, binding, terminal_state=None, correction_count=0)
            before = state_path.read_bytes()
            record_agent_premature_completion(registry_path, binding["claim_id"],
                                              completed_agent_id=binding["builder_agent_id"], reason="Required direct delivery missing.")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(0, main(["agent-continuity-resume", str(registry_path), binding["claim_id"]]))
            resumed = json.loads(registry_path.read_text())["claims"][0]
            self.assertEqual(before, state_path.read_bytes())
            self.assertEqual("PAIR_ACTIVE", resumed["continuity"]["phase"])
            self.assertEqual([0], resumed["continuity"]["completed_rounds"])
            self.assertEqual(1, resumed["continuity"]["next_round"])
            self.assertEqual("ABORTED", resumed["continuity"]["recovered_aborts"][0]["continuity"]["phase"])
            self.assertNotIn("execution_result", resumed)
            record_agent_premature_completion(registry_path, binding["claim_id"],
                                              completed_agent_id=binding["builder_agent_id"], reason="Delivery still missing.")
            with self.assertRaisesRegex(ValueError, "one recorded abort"):
                resume_agent_continuity(registry_path, binding["claim_id"])

    def test_preflight_recovery_preserves_evidence_identity_and_budget(self):
        original_feedback = _feedback
        def blocked_feedback(*args, **kwargs):
            feedback = original_feedback(*args, **kwargs)
            feedback.update(execution_status="blocked", test_status="not_run",
                            stop_reason={"category": "environment_error", "reason": "Missing runtime control.",
                                         "evidence": ["Control preflight stopped before implementation."]},
                            resources={"human_interventions": [], "measurements": [{
                                "metric": "implementation_actions_started", "phase": "preflight", "value": 0,
                                "unit": "actions", "status": "measured", "basis": "Control-only stop.",
                                "recorded_at": "2026-09-08T00:00:00+00:00"}]})
            return feedback
        with TemporaryDirectory() as tmp:
            registry_path, binding = _prepare_rich_ready_pair(Path(tmp) / "run")
            claim_id = binding["claim_id"]
            start_agent_continuity(registry_path, **binding)
            record_agent_continuity_round(registry_path, **binding, round_number=0,
                                         operator_to_builder_direct=True, builder_to_operator_direct=True)
            with patch(f"{__name__}._feedback", side_effect=blocked_feedback):
                state_path = _write_execution_state(registry_path, binding, terminal_state=None, correction_count=0)
            previous = json.loads(state_path.read_text())
            finish_agent_continuity(registry_path, **binding, terminal_state="FAILED",
                                    terminal_acknowledged_directly=True, execution_state_path=state_path)
            candidate = registry_path.parent / previous["attempts"][0]["candidate_path"]
            candidate.write_text("{}")
            with self.assertRaisesRegex(ValueError, "no candidate"):
                retry_agent_preflight(registry_path, claim_id)
            candidate.unlink()
            with redirect_stdout(io.StringIO()):
                self.assertEqual(0, main(["agent-continuity-retry-preflight", str(registry_path), claim_id]))
            registry = json.loads(registry_path.read_text())
            claim = registry["claims"][0]
            recovery = claim["preflight_recovery"]
            archive = registry_path.parent / recovery["archive_path"]
            self.assertEqual(previous, json.loads(archive.read_text())["execution_state"])
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), recovery["sha256"])
            resumed = json.loads(state_path.read_text())
            for field in ("started_at", "budget", "operator_agent_id", "builder_agent_id", "pair_nonce", "claim_sha256"):
                self.assertEqual(previous[field], resumed[field])
            self.assertEqual([previous["attempts"][0]["resources"]], resumed["prior_resources"])
            self.assertEqual("ACTIVE", resumed["status"])
            self.assertEqual("READY", claim["continuity"]["phase"])
            self.assertNotIn("finished_at", claim["continuity"])
            with self.assertRaisesRegex(ValueError, "unrecovered"):
                retry_agent_preflight(registry_path, claim_id)

    def test_all_selected_pairs_overlap_without_waiting_for_completion(self):
        for claim_count in (3, 10):
            with self.subTest(claim_count=claim_count), TemporaryDirectory() as tmp:
                registry_path, _ = _prepare_active_continuity_pairs(
                    Path(tmp) / "run", claim_count=claim_count
                )
                registry = json.loads(registry_path.read_text())
                self.assertEqual(claim_count, registry["scheduling"]["max_concurrent_pairs"])
                self.assertEqual(claim_count, registry["scheduling"]["peak_active_pairs"])
                for claim in registry["claims"]:
                    self.assertEqual("PAIR_ACTIVE", claim["continuity"]["phase"])
                    self.assertTrue(claim["continuity"]["started_at"])
                    self.assertNotIn("finished_at", claim["continuity"])
                with self.assertRaisesRegex(ValueError, "active execution pairs"):
                    finish_agent_harness(registry_path)

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

            with self.assertRaisesRegex(ValueError, "candidate finalization"):
                finish_agent_harness(registry_path)

            candidate_path = _write_candidate(registry_path)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    0,
                    main(
                        [
                            "agent-candidate-finalize",
                            str(registry_path),
                            CLAIM_ID,
                            str(candidate_path),
                        ]
                    ),
                )
            finalized = json.loads(stdout.getvalue())
            claim = finalized["claims"][0]
            self.assertEqual("RESULT_SUCCESS", claim["status"])
            self.assertEqual("BUILT_AND_PASSED", claim["final_result"]["status"])
            self.assertEqual(
                "replica-agent-final-result/v1",
                claim["final_result"]["schema_version"],
            )
            for artifact in claim["final_result"]["artifacts"].values():
                self.assertTrue((registry_path.parent / artifact["path"]).is_file())

            report_record = claim["final_result"]["artifacts"]["report_markdown"]
            report_path = registry_path.parent / report_record["path"]
            report_bytes = report_path.read_bytes()
            report_path.write_text("tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                finish_agent_harness(registry_path)
            report_path.write_bytes(report_bytes)

            aggregate = finish_agent_harness(registry_path)
            self.assertEqual("EXECUTION_SUCCESS", aggregate["status"])

    def test_rich_second_pass_binds_a_multi_file_implementation_bundle(self):
        with TemporaryDirectory() as tmp:
            registry_path, binding = _prepare_rich_ready_pair(Path(tmp) / "run")
            start_agent_continuity(
                registry_path,
                binding["claim_id"],
                operator_agent_id=binding["operator_agent_id"],
                builder_agent_id=binding["builder_agent_id"],
                nonce=binding["nonce"],
            )
            record_agent_continuity_round(
                registry_path,
                binding["claim_id"],
                round_number=0,
                operator_agent_id=binding["operator_agent_id"],
                builder_agent_id=binding["builder_agent_id"],
                nonce=binding["nonce"],
                operator_to_builder_direct=True,
                builder_to_operator_direct=True,
            )
            candidate_relative_path = (
                "claims/claim-001/builder/implementation/manifest.json"
            )
            state_path = _write_execution_state(
                registry_path,
                binding,
                terminal_state="SUCCESS",
                correction_count=0,
                candidate_path=candidate_relative_path,
            )
            finish_agent_continuity(
                registry_path,
                binding["claim_id"],
                terminal_state="SUCCESS",
                execution_state_path=state_path,
                operator_agent_id=binding["operator_agent_id"],
                builder_agent_id=binding["builder_agent_id"],
                nonce=binding["nonce"],
                terminal_acknowledged_directly=True,
            )

            implementation_dir = (
                registry_path.parent / "claims/claim-001/builder/implementation"
            )
            implementation_dir.mkdir()
            source_path = implementation_dir / "replica.py"
            source_path.write_text(
                "import json, sys\njson.dump(json.load(sys.stdin), sys.stdout)\n",
                encoding="utf-8",
            )
            claim = json.loads(
                (registry_path.parent / "claims/claim-001/claim.json").read_text(
                    encoding="utf-8"
                )
            )
            selected = next(
                scenario
                for scenario in claim["second_pass"]["replication_contract"]
                if scenario["id"] == claim["selected_scenario_id"]
            )
            self.assertEqual("s-oss", selected["id"])
            manifest_path = implementation_dir / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": "replica-implementation-bundle/v1",
                        "claim_id": "claim-001",
                        "scenario_id": selected["id"],
                        "implementation_type": "hybrid",
                        "dependency_level": "commercial_api",
                        "input_contract": selected["input"],
                        "output_contract": selected["output"],
                        "entrypoint": "replica.py",
                        "command": ["python3", "replica.py"],
                        "dependencies": [
                            {
                                "name": "codex-cli",
                                "version": "0.149.0",
                                "source": "https://developers.openai.com/codex/cli",
                                "license": "OpenAI service terms",
                            }
                        ],
                        "environment_variables": [],
                        "files": [
                            {
                                "path": "replica.py",
                                "sha256": hashlib.sha256(
                                    source_path.read_bytes()
                                ).hexdigest(),
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            wrong_runtime = json.loads(manifest_path.read_text(encoding="utf-8"))
            wrong_runtime["dependencies"][0]["name"] = "claude-code"
            manifest_path.write_text(
                json.dumps(wrong_runtime, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "selected scenario"):
                finalize_agent_candidate(
                    registry_path,
                    binding["claim_id"],
                    manifest_path,
                )
            wrong_runtime["dependencies"][0]["name"] = "codex-cli"
            manifest_path.write_text(
                json.dumps(wrong_runtime, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            finalized = finalize_agent_candidate(
                registry_path,
                binding["claim_id"],
                manifest_path,
            )

            result = finalized["claims"][0]["implementation_result"]
            self.assertEqual("IMPLEMENTATION_READY", finalized["claims"][0]["status"])
            self.assertEqual("hybrid", result["implementation_type"])
            self.assertEqual("commercial_api", result["dependency_level"])
            self.assertEqual(
                candidate_relative_path,
                result["candidate_path"],
            )
            source_bytes = source_path.read_bytes()
            source_path.write_text("tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                finish_agent_harness(registry_path)
            source_path.write_bytes(source_bytes)
            with self.assertRaisesRegex(ValueError, "before final bundle evaluation"):
                finish_agent_harness(registry_path)

    def test_invalid_terra_candidate_fails_the_final_result(self):
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
            finish_agent_continuity(
                registry_path,
                CLAIM_ID,
                terminal_state="SUCCESS",
                execution_state_path=state_path,
                operator_agent_id=OPERATOR_ID,
                builder_agent_id=BUILDER_ID,
                nonce=NONCE,
                terminal_acknowledged_directly=True,
            )
            candidate_path = (
                registry_path.parent
                / "claims"
                / CLAIM_ID
                / "builder"
                / "operator.json"
            )
            candidate_path.write_text("{}\n", encoding="utf-8")

            finalized = finalize_agent_candidate(
                registry_path,
                CLAIM_ID,
                candidate_path,
            )

            self.assertEqual("RESULT_FAILED", finalized["claims"][0]["status"])
            self.assertEqual(
                "VALIDATION_FAILED",
                finalized["claims"][0]["final_result"]["status"],
            )
            aggregate = finish_agent_harness(registry_path)
            self.assertEqual("EXECUTION_COMPLETED_WITH_FAILURES", aggregate["status"])

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
            registry_path, bindings = _prepare_active_continuity_pairs(
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

            _write_candidate(registry_path, bindings[0]["claim_id"])
            finalize_agent_candidate(
                registry_path,
                bindings[0]["claim_id"],
                registry_path.parent
                / "claims"
                / bindings[0]["claim_id"]
                / "builder"
                / "operator.json",
            )

            aggregate = finish_agent_harness(registry_path)

            self.assertEqual(
                "EXECUTION_COMPLETED_WITH_FAILURES",
                aggregate["status"],
            )
            self.assertEqual(
                ["RESULT_SUCCESS", "EXECUTION_FAILED"],
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

    def test_premature_completion_does_not_abort_another_claim(self):
        with TemporaryDirectory() as tmp:
            registry_path, bindings = _prepare_active_continuity_pairs(
                Path(tmp) / "run"
            )

            aborted = record_agent_premature_completion(
                registry_path,
                bindings[0]["claim_id"],
                completed_agent_id=bindings[0]["builder_agent_id"],
                reason="Builder returned final before terminal",
            )

            self.assertEqual("EXECUTION_ABORTED", aborted["claims"][0]["status"])
            self.assertEqual("READY_FOR_PROTOCOL", aborted["claims"][1]["status"])
            self.assertEqual(
                "PAIR_ACTIVE",
                aborted["claims"][1]["continuity"]["phase"],
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
