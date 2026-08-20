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
                "gpt-5.6-sol",
                registry["replica_agent"]["requested_model"],
            )
            claim = registry["claims"][0]
            self.assertEqual(
                "growth-labs-lead-qualification",
                claim["claim_id"],
            )
            self.assertEqual("operator", claim["operator"]["role"])
            self.assertEqual("gpt-5.6-sol", claim["operator"]["requested_model"])
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

    def test_multi_claims_are_scheduled_one_pair_at_a_time(self):
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
                "sequential_claim_pairs",
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
                requested_model="gpt-5.6-sol",
            )
            linked = record_agent_spawn(
                registry_path,
                claim_id,
                role="builder",
                agent_id="/root/replica_agent/builder_001",
                parent_agent_id="/root/replica_agent",
                requested_model="gpt-5.6-terra",
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
                requested_model="gpt-5.6-sol",
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
            self.assertEqual(1, ready["scheduling"]["completed_claim_count"])
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
                    "gpt-5.6-sol",
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
            self.assertEqual(
                "READY_FOR_PROTOCOL",
                final["replica_agent"]["status"],
            )
            self.assertEqual("READY_FOR_PROTOCOL", final["claims"][0]["status"])


if __name__ == "__main__":
    unittest.main()
