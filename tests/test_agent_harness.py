import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from replica_mvp import (
    finish_agent_harness,
    prepare_agent_harness,
    record_direct_agent_message,
    record_agent_spawn_failure,
    record_agent_spawn,
    record_released_agent,
    start_agent_claim,
)
from replica_mvp.cli import main
from tests.test_second_pass import _research


REPOSITORY_ROOT = Path(__file__).parents[1]
LEGACY_EXAMPLE = REPOSITORY_ROOT / "examples" / "second-pass-lead-qualification.json"


def _legacy_claim():
    return json.loads(LEGACY_EXAMPLE.read_text(encoding="utf-8"))


def _multi_claim_input():
    first = _legacy_claim()
    second = _legacy_claim()
    second["replica_id"] = "growth-labs-seat-guidance"
    return {
        "schema_version": "replica-second-pass-claim-collection/v1",
        "claims": [first, second],
    }


class ReplicaAgentHarnessTest(unittest.TestCase):
    def test_empty_research_finishes_from_the_real_first_pass_and_completed_second_pass(self):
        from replica_mvp import finalize_first_pass
        from tests.test_first_pass import FinalizeFirstPassTest

        with TemporaryDirectory() as tmp:
            root, _ = FinalizeFirstPassTest()._setup(tmp)
            source = root / "research.json"
            research = json.loads(source.read_text())
            research["claims"] = []
            for resolution in research["candidate_resolutions"]:
                resolution.update(decision="excluded", target_id=None, rationale="Only internal use was documented.")
            source.write_text(json.dumps(research))
            research = finalize_first_pass(root)
            self.assertEqual("no_ai_claims", research["summary"]["next_step"])
            for status in ("pass_1_complete", "pass_2_complete"):
                with self.subTest(status=status):
                    research["workflow"]["status"] = status
                    source.write_text(json.dumps(research))
                    run = root / status
                    with redirect_stdout(io.StringIO()):
                        self.assertEqual(0, main([
                            "agent-harness-init", str(source), str(run),
                            "--replica-agent-id", "/root/replica_agent", "--parent-agent-id", "/root",
                        ]))
                    registry = json.loads((run / "agent-harness.json").read_text())
                    self.assertEqual("COMPLETED_WITHOUT_EXECUTION", registry["status"])
                    result = json.loads((run / registry["company_result"]["path"]).read_text())
                    self.assertEqual((0, 0, [], {}), (result["claim_total"], result["selected_for_execution"],
                                                    result["claims"], result["outcome_counts"]))
                    self.assertEqual(str(source.resolve()), result["research_source"]["path"])

    def test_empty_research_does_not_bypass_completion_or_contract_checks(self):
        for invalid in ("missing_claims", "null_claims", "unfinished", "unfinalized", "unexplained_empty", "wrong_counts"):
            with self.subTest(invalid=invalid), TemporaryDirectory() as tmp:
                research = _research()
                research["claims"] = []
                research["summary"].update(ready_count=0, partial_count=0, blocked_count=0, next_step="no_ai_claims")
                if invalid == "missing_claims":
                    del research["claims"]
                elif invalid == "null_claims":
                    research["claims"] = None
                elif invalid == "unfinished":
                    research["workflow"]["status"] = "pass_1_running"
                elif invalid == "unfinalized":
                    research["workflow"]["pass_1"]["completed_at"] = None
                elif invalid == "unexplained_empty":
                    research["workflow"]["status"] = "pass_1_complete"
                    research["summary"]["next_step"] = "run_pass_2"
                else:
                    research["summary"]["ready_count"] = 1
                with self.assertRaises(ValueError):
                    prepare_agent_harness(research, Path(tmp) / "run",
                                          replica_agent_id="/root/replica_agent", parent_agent_id="/root")

    def test_company_result_keeps_research_and_creation_failure_reasons(self):
        for failure in ("research", "creation"):
            with self.subTest(failure=failure), TemporaryDirectory() as tmp:
                research = _research()
                if failure == "research":
                    evaluation = research["claims"][0]["second_pass"]["replication_contract"][1]["evaluation"]
                    evaluation["additional_cases"] = [c for c in evaluation["additional_cases"] if c["kind"] != "novel"]
                root = Path(tmp) / "run"
                prepared = prepare_agent_harness(research, root,
                                                replica_agent_id="/root/replica_agent", parent_agent_id="/root")
                registry = root / "agent-harness.json"
                if failure == "creation":
                    reason = "Requested model is unavailable in this execution environment."
                    start_agent_claim(registry, "claim-001")
                    record_agent_spawn_failure(registry, "claim-001", role="operator", reason=reason)
                else:
                    reason = "; ".join(prepared["claims"][0]["research_gaps"])
                    self.assertIn("novel", reason)
                finished = finish_agent_harness(registry)
                result = json.loads((root / finished["company_result"]["path"]).read_text())["claims"][0]
                self.assertEqual("experiment_blocked", result["outcome"])
                self.assertEqual(reason, result["failure_reason"])
                self.assertEqual(reason, result["not_executed_reason"])
                self.assertEqual("research_gap" if failure == "research" else "agent_creation_failed", result["failure_category"])
                self.assertIsNotNone(result["stop_reason"])
                self.assertIsNone(result["result_path"])
                self.assertIsNone(result["reproduction_status"])

    def test_astra_and_terra_spawns_require_their_explicit_efforts(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            registry = prepare_agent_harness(_legacy_claim(), run_dir,
                                             replica_agent_id="/root/replica_agent", parent_agent_id="/root")
            registry_path = run_dir / "agent-harness.json"
            claim_id = registry["claims"][0]["claim_id"]
            start_agent_claim(registry_path, claim_id)
            arguments = {"role": "operator", "agent_id": "/root/replica_agent/operator_001",
                         "parent_agent_id": "/root/replica_agent", "requested_model": "gpt-6-astra"}
            for effort in (None, "high"):
                with self.subTest(effort=effort), self.assertRaisesRegex(ValueError, "reasoning effort"):
                    record_agent_spawn(registry_path, claim_id, **arguments, requested_reasoning_effort=effort)
            recorded = record_agent_spawn(registry_path, claim_id, **arguments, requested_reasoning_effort="medium")
            self.assertEqual("SPAWNED", recorded["claims"][0]["operator"]["status"])
            arguments.update(role="builder", agent_id="/root/replica_agent/builder_001", requested_model="gpt-5.6-terra")
            for effort in (None, "medium"):
                with self.subTest(builder_effort=effort), self.assertRaisesRegex(ValueError, "reasoning effort"):
                    record_agent_spawn(registry_path, claim_id, **arguments, requested_reasoning_effort=effort)
            recorded = record_agent_spawn(registry_path, claim_id, **arguments, requested_reasoning_effort="high")
            self.assertEqual("PEER_LINKED", recorded["claims"][0]["builder"]["status"])

    def test_research_claim_gives_sol_full_context_and_terra_a_public_build_context(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"

            registry = prepare_agent_harness(
                _research(),
                run_dir,
                replica_agent_id="/root/replica_agent",
                parent_agent_id="/root",
            )

            claim = registry["claims"][0]
            sol_claim = json.loads(
                (run_dir / claim["claim_payload_path"]).read_text(encoding="utf-8")
            )
            terra_context_path = run_dir / claim["builder_context_path"]
            terra_context = json.loads(terra_context_path.read_text(encoding="utf-8"))
            self.assertEqual("replica-agent-claim/v2", sol_claim["schema_version"])
            # The Operator claim is public; sealed tests stay in the evaluator vault.
            self.assertNotIn('"tests"', json.dumps(sol_claim))
            self.assertNotIn("evaluation", sol_claim["second_pass"]["replication_contract"][1])
            sealed = json.loads((run_dir / claim["sealed_claim_path"]).read_text(encoding="utf-8"))
            self.assertTrue(claim["sealed_claim_path"].startswith("evaluator-vault/"))
            self.assertIn("tests", sealed["second_pass"]["replication_contract"][0])
            self.assertEqual("replica-builder-context/v1", terra_context["schema_version"])
            self.assertEqual("s-oss", terra_context["selected_scenario"]["id"])
            self.assertEqual(
                {"provider": "codex", "transport": "local_cli"},
                terra_context["model_runtime"],
            )
            self.assertEqual(
                "Use a local retriever.",
                terra_context["findings"]["impl_path"]["note"],
            )
            serialized = json.dumps(terra_context)
            self.assertNotIn("expected_behavior", serialized)
            self.assertNotIn("reference_facts", serialized)
            self.assertNotIn('"tests"', serialized)

    def test_research_without_executable_claims_is_a_complete_company_result(self):
        research = _research()
        research["claims"][0]["second_pass"]["readiness"] = {"status": "blocked", "reasons": "No public input."}
        research["summary"].update(ready_count=0, blocked_count=1)
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "research.json"
            (Path(tmp) / "second_pass").mkdir()
            for claim in research["claims"]:
                claim["second_pass"]["run"] = {"fragment": f"second_pass/{claim['id']}.json"}
                (Path(tmp) / claim["second_pass"]["run"]["fragment"]).write_text(json.dumps(claim["second_pass"]))
            source.write_text(json.dumps(research))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(0, main([
                    "agent-harness-init", str(source), str(Path(tmp) / "run"),
                    "--replica-agent-id", "/root/replica_agent", "--parent-agent-id", "/root",
                ]))
            registry = json.loads((Path(tmp) / "run" / "agent-harness.json").read_text())
            self.assertEqual("COMPLETED_WITHOUT_EXECUTION", registry["status"])
            self.assertEqual([], registry["claims"])
            result = json.loads((Path(tmp) / "run" / registry["company_result"]["path"]).read_text())
            self.assertEqual(2, result["claim_total"])
            self.assertEqual(0, result["selected_for_execution"])
            self.assertEqual({"not_executed": 2}, result["outcome_counts"])
            self.assertEqual("No public input.", result["claims"][0]["readiness_reasons"])
            self.assertEqual(str(source.resolve()), result["research_source"]["path"])

    def test_legacy_single_claim_prepares_one_sol_terra_pair(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            source_claim = _legacy_claim()

            registry = prepare_agent_harness(
                source_claim,
                run_dir,
                replica_agent_id="/root/replica_agent",
                parent_agent_id="/root",
            )

            self.assertEqual("replica-agent-harness/v1", registry["schema_version"])
            self.assertEqual(1, registry["claim_count"])
            self.assertEqual(
                "gpt-6-astra",
                registry["replica_agent"]["requested_model"],
            )
            claim = registry["claims"][0]
            self.assertEqual(
                "growth-labs-lead-qualification",
                claim["claim_id"],
            )
            self.assertEqual("operator", claim["operator"]["role"])
            self.assertEqual("gpt-6-astra", claim["operator"]["requested_model"])
            self.assertEqual("medium", registry["replica_agent"]["requested_reasoning_effort"])
            self.assertEqual("medium", claim["operator"]["requested_reasoning_effort"])
            self.assertEqual("high", claim["builder"]["requested_reasoning_effort"])
            self.assertEqual("builder", claim["builder"]["role"])
            self.assertEqual("gpt-5.6-terra", claim["builder"]["requested_model"])
            self.assertTrue((run_dir / "claims" / claim["claim_id"] / "operator").is_dir())
            self.assertTrue((run_dir / "claims" / claim["claim_id"] / "builder").is_dir())
            self.assertEqual(
                source_claim,
                json.loads(
                    (run_dir / claim["claim_payload_path"]).read_text(
                        encoding="utf-8"
                    )
                ),
            )
            self.assertEqual(
                "replica_agent",
                claim["claim_payload_owner"],
            )
            self.assertEqual(
                "operator",
                claim["operator"]["artifact_owner"],
            )
            self.assertEqual(
                "builder",
                claim["builder"]["artifact_owner"],
            )
            self.assertEqual(
                registry,
                json.loads(
                    (run_dir / "agent-harness.json").read_text(encoding="utf-8")
                ),
            )

    def test_pair_creation_is_serialized_separately_from_execution(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            registry = prepare_agent_harness(
                _multi_claim_input(),
                run_dir,
                replica_agent_id="/root/replica_agent",
                parent_agent_id="/root",
            )

            started = start_agent_claim(
                run_dir / "agent-harness.json",
                "growth-labs-lead-qualification",
            )

            self.assertEqual(2, registry["claim_count"])
            self.assertEqual(
                [
                    "growth-labs-lead-qualification",
                    "growth-labs-seat-guidance",
                ],
                [claim["claim_id"] for claim in registry["claims"]],
            )
            self.assertEqual(
                "parallel_claim_pairs",
                started["scheduling"]["policy"],
            )
            self.assertEqual(
                "growth-labs-lead-qualification",
                started["scheduling"]["active_claim_id"],
            )
            with self.assertRaisesRegex(ValueError, "claim already active"):
                start_agent_claim(
                    run_dir / "agent-harness.json",
                    "growth-labs-seat-guidance",
                )

    def test_model_policy_is_configurable_and_still_binds_every_spawn(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            registry_path = run_dir / "agent-harness.json"
            claim_id = "growth-labs-lead-qualification"
            registry = prepare_agent_harness(
                _legacy_claim(),
                run_dir,
                replica_agent_id="/root/replica_agent",
                parent_agent_id="/root",
                replica_agent_model="claude-opus-5",
                operator_model="claude-opus-5",
                builder_model="claude-sonnet-5",
                model_runtime="claude",
            )

            self.assertEqual(
                "claude-opus-5",
                registry["replica_agent"]["requested_model"],
            )
            self.assertEqual(
                {"provider": "claude", "transport": "local_cli"},
                registry["model_runtime"],
            )
            claim = registry["claims"][0]
            self.assertEqual("claude-opus-5", claim["operator"]["requested_model"])
            self.assertEqual("claude-sonnet-5", claim["builder"]["requested_model"])

            start_agent_claim(registry_path, claim_id)
            with self.assertRaises(ValueError):
                record_agent_spawn(
                    registry_path,
                    claim_id,
                    role="operator",
                    agent_id="/root/replica_agent/operator_001",
                    parent_agent_id="/root/replica_agent",
                    requested_model="gpt-6-astra",
                    requested_reasoning_effort="medium",
                )
            linked = record_agent_spawn(
                registry_path,
                claim_id,
                role="operator",
                agent_id="/root/replica_agent/operator_001",
                parent_agent_id="/root/replica_agent",
                requested_model="claude-opus-5",
            )
            self.assertEqual(
                "claude-opus-5",
                linked["claims"][0]["operator"]["requested_model"],
            )

    def test_model_policy_rejects_an_empty_model_request(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                prepare_agent_harness(
                    _legacy_claim(),
                    Path(tmp) / "run",
                    replica_agent_id="/root/replica_agent",
                    parent_agent_id="/root",
                    builder_model="",
                )

    def test_unknown_model_runtime_is_rejected(self):
        with TemporaryDirectory() as tmp, self.assertRaisesRegex(
            ValueError,
            "model runtime",
        ):
            prepare_agent_harness(
                _legacy_claim(),
                Path(tmp) / "run",
                replica_agent_id="/root/replica_agent",
                parent_agent_id="/root",
                model_runtime="other",
            )

    def test_spawned_agents_are_same_parent_siblings_and_exact_peers(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            registry_path = run_dir / "agent-harness.json"
            claim_id = "growth-labs-lead-qualification"
            prepare_agent_harness(
                _legacy_claim(),
                run_dir,
                replica_agent_id="/root/replica_agent",
                parent_agent_id="/root",
            )
            start_agent_claim(registry_path, claim_id)

            record_agent_spawn(
                registry_path,
                claim_id,
                role="operator",
                agent_id="/root/replica_agent/operator_001",
                parent_agent_id="/root/replica_agent",
                requested_model="gpt-6-astra",
                requested_reasoning_effort="medium",
            )
            linked = record_agent_spawn(
                registry_path,
                claim_id,
                role="builder",
                agent_id="/root/replica_agent/builder_001",
                parent_agent_id="/root/replica_agent",
                requested_model="gpt-5.6-terra",
                requested_reasoning_effort="high",
            )

            claim = linked["claims"][0]
            operator = claim["operator"]
            builder = claim["builder"]
            self.assertEqual("PEER_LINKED", claim["status"])
            self.assertEqual(operator["parent_agent_id"], builder["parent_agent_id"])
            self.assertEqual(builder["agent_id"], operator["allowed_peer_agent_id"])
            self.assertEqual(operator["agent_id"], builder["allowed_peer_agent_id"])
            self.assertEqual("PEER_LINKED", operator["status"])
            self.assertEqual("PEER_LINKED", builder["status"])

    def test_partial_spawn_failure_is_fail_closed_without_model_fallback(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            registry_path = run_dir / "agent-harness.json"
            claim_id = "growth-labs-lead-qualification"
            prepare_agent_harness(
                _legacy_claim(),
                run_dir,
                replica_agent_id="/root/replica_agent",
                parent_agent_id="/root",
            )
            start_agent_claim(registry_path, claim_id)
            record_agent_spawn(
                registry_path,
                claim_id,
                role="operator",
                agent_id="/root/replica_agent/operator_001",
                parent_agent_id="/root/replica_agent",
                requested_model="gpt-6-astra",
                requested_reasoning_effort="medium",
            )

            failed = record_agent_spawn_failure(
                registry_path,
                claim_id,
                role="builder",
                reason="Terra spawn rejected",
            )

            claim = failed["claims"][0]
            self.assertEqual(
                "RELEASING_AFTER_CREATION_FAILURE",
                claim["status"],
            )
            self.assertEqual("RELEASE_REQUIRED", claim["operator"]["status"])
            self.assertEqual("CREATION_FAILED", claim["builder"]["status"])
            self.assertEqual("gpt-5.6-terra", claim["builder"]["requested_model"])
            self.assertIsNone(claim["operator"]["allowed_peer_agent_id"])
            self.assertIsNone(claim["builder"]["allowed_peer_agent_id"])
            self.assertEqual(claim_id, failed["scheduling"]["active_claim_id"])
            with self.assertRaisesRegex(ValueError, "active claim"):
                finish_agent_harness(registry_path)
            released = record_released_agent(
                registry_path,
                claim_id,
                agent_id="/root/replica_agent/operator_001",
            )
            claim = released["claims"][0]
            self.assertEqual("CREATION_FAILED", claim["status"])
            self.assertEqual("RELEASED", claim["operator"]["status"])
            self.assertIsNone(released["scheduling"]["active_claim_id"])
            with self.assertRaisesRegex(ValueError, "claim is not active"):
                record_agent_spawn(
                    registry_path,
                    claim_id,
                    role="builder",
                    agent_id="/root/replica_agent/builder_001",
                    parent_agent_id="/root/replica_agent",
                    requested_model="gpt-5.6-terra",
                    requested_reasoning_effort="high",
                )

    def test_direct_ping_pong_is_pair_scoped_and_preserves_agent_continuity(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            registry_path = run_dir / "agent-harness.json"
            claim_id = "growth-labs-lead-qualification"
            operator_id = "/root/replica_agent/operator_001"
            builder_id = "/root/replica_agent/builder_001"
            prepare_agent_harness(
                _multi_claim_input(),
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

            pinged = record_direct_agent_message(
                registry_path,
                claim_id,
                direction="operator_to_builder",
                sender_agent_id=operator_id,
                recipient_agent_id=builder_id,
                nonce="claim-001-nonce",
            )

            self.assertTrue(pinged["claims"][0]["smoke"]["operator_to_builder"])
            with self.assertRaisesRegex(ValueError, "paired Agent identities"):
                record_direct_agent_message(
                    registry_path,
                    claim_id,
                    direction="builder_to_operator",
                    sender_agent_id=builder_id,
                    recipient_agent_id="/root/replica_agent/operator_002",
                    nonce="claim-001-nonce",
                )
            ready = record_direct_agent_message(
                registry_path,
                claim_id,
                direction="builder_to_operator",
                sender_agent_id=builder_id,
                recipient_agent_id=operator_id,
                nonce="claim-001-nonce",
            )

            claim = ready["claims"][0]
            self.assertEqual("READY_FOR_PROTOCOL", claim["status"])
            self.assertEqual(operator_id, claim["operator"]["agent_id"])
            self.assertEqual(builder_id, claim["builder"]["agent_id"])
            self.assertEqual("READY_FOR_PROTOCOL", claim["operator"]["status"])
            self.assertEqual("READY_FOR_PROTOCOL", claim["builder"]["status"])
            self.assertIsNone(ready["scheduling"]["active_claim_id"])
            self.assertEqual(1, ready["scheduling"]["linked_pair_count"])
            next_claim = start_agent_claim(
                registry_path,
                "growth-labs-seat-guidance",
            )
            self.assertEqual(
                "growth-labs-seat-guidance",
                next_claim["scheduling"]["active_claim_id"],
            )

    def test_cli_drives_the_agent_harness_lifecycle(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "second-pass.json"
            source.write_text(
                json.dumps(_legacy_claim(), ensure_ascii=False),
                encoding="utf-8",
            )
            run_dir = root / "run"
            registry_path = run_dir / "agent-harness.json"
            claim_id = "growth-labs-lead-qualification"
            operator_id = "/root/replica_agent/operator_001"
            builder_id = "/root/replica_agent/builder_001"

            commands = (
                [
                    "agent-harness-init",
                    str(source),
                    str(run_dir),
                    "--replica-agent-id",
                    "/root/replica_agent",
                    "--parent-agent-id",
                    "/root",
                    "--model-runtime",
                    "claude",
                ],
                ["agent-harness-start", str(registry_path), claim_id],
                [
                    "agent-harness-spawned",
                    str(registry_path),
                    claim_id,
                    "--role",
                    "operator",
                    "--agent-id",
                    operator_id,
                    "--parent-agent-id",
                    "/root/replica_agent",
                    "--requested-model",
                    "gpt-6-astra",
                    "--requested-reasoning-effort",
                    "medium",
                ],
                [
                    "agent-harness-spawned",
                    str(registry_path),
                    claim_id,
                    "--role",
                    "builder",
                    "--agent-id",
                    builder_id,
                    "--parent-agent-id",
                    "/root/replica_agent",
                    "--requested-model",
                    "gpt-5.6-terra",
                    "--requested-reasoning-effort",
                    "high",
                ],
                [
                    "agent-harness-message",
                    str(registry_path),
                    claim_id,
                    "--direction",
                    "operator_to_builder",
                    "--sender-agent-id",
                    operator_id,
                    "--recipient-agent-id",
                    builder_id,
                    "--nonce",
                    "runtime-nonce",
                ],
                [
                    "agent-harness-message",
                    str(registry_path),
                    claim_id,
                    "--direction",
                    "builder_to_operator",
                    "--sender-agent-id",
                    builder_id,
                    "--recipient-agent-id",
                    operator_id,
                    "--nonce",
                    "runtime-nonce",
                ],
                ["agent-harness-finish", str(registry_path)],
            )

            for command in commands:
                with self.subTest(command=command[0]):
                    stdout = io.StringIO()
                    with redirect_stdout(stdout):
                        self.assertEqual(0, main(command))
                    self.assertEqual(
                        "replica-agent-harness/v1",
                        json.loads(stdout.getvalue())["schema_version"],
                    )
            final = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertEqual("READY_FOR_PROTOCOL", final["status"])
            self.assertEqual("claude", final["model_runtime"]["provider"])
            self.assertEqual(
                "READY_FOR_PROTOCOL",
                final["replica_agent"]["status"],
            )
            self.assertEqual("READY_FOR_PROTOCOL", final["claims"][0]["status"])


if __name__ == "__main__":
    unittest.main()
