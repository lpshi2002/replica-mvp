import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from replica_mvp.agent_harness import finish_agent_harness
from replica_mvp.bundle_evaluation import digest, evaluate_agent_bundle, retry_agent_bundle
from replica_mvp.single_agent import (
    prepare_single_harness, start_single_implementation, bind_single_implementation,
    fail_single_implementation, validate_single_implementation,
)
from tests.test_bundle_evaluation import SOURCE, _fixture_judge
from tests.test_second_pass import _research


def prepare(root):
    research = _research()
    fragments = root / "second_pass"
    fragments.mkdir()
    for claim in research["claims"]:
        claim["second_pass"]["handoff"]["experiment_budget"] = {
            "time_limit_seconds": 7200, "cost_limit": None, "stop_on_blocked": True,
        }
        fragment = f"second_pass/{claim['id']}.json"
        claim["second_pass"]["run"] = {"fragment": fragment}
        (root / fragment).write_text(json.dumps(claim["second_pass"]))
    source = root / "research.json"
    source.write_text(json.dumps(research))
    registry = prepare_single_harness(source, root / "run", orchestrator_id="root")
    path = root / "run" / "agent-harness.json"
    return path, registry


def implement(path):
    start_single_implementation(path, "claim-001", agent_id="real-child", model="gpt-6-astra", reasoning_effort="low")
    workspace = path.parent / "claims/claim-001/implementer"
    bundle = workspace / "implementation"
    bundle.mkdir()
    code = bundle / "entry.py"
    code.write_text(SOURCE)
    claim = json.loads((workspace.parent / "claim.json").read_text())
    manifest = {
        "schema_version": "replica-implementation-bundle/v1", "claim_id": "claim-001", "scenario_id": "s-oss",
        "implementation_type": "code", "dependency_level": "oss_only", "input_contract": claim["input_contract"],
        "output_contract": claim["output_contract"], "entrypoint": "entry.py", "command": [sys.executable, "entry.py"],
        "dependencies": [], "environment_variables": [], "files": [{"path": "entry.py", "sha256": digest(code)}],
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    (workspace / "development.json").write_text(json.dumps({"status": "passed", "checks": [
        {"command": "controlled fixture receipt", "exit_code": 0}]}))
    return workspace


class SingleAgentTest(unittest.TestCase):
    def test_single_agent_reaches_existing_sealed_evaluator_and_company_result(self):
        with TemporaryDirectory() as tmp:
            path, registry = prepare(Path(tmp))
            claim = registry["claims"][0]
            self.assertNotIn("operator", claim)
            self.assertNotIn("builder", claim)
            public = json.loads((path.parent / claim["implementation_context_path"]).read_text())
            self.assertNotIn("tests", public["selected_scenario"])
            workspace = implement(path)
            bind_single_implementation(path, "claim-001", agent_id="real-child")
            with self.assertRaisesRegex(ValueError, "before final bundle evaluation"):
                finish_agent_harness(path)
            failed = evaluate_agent_bundle(path, "claim-001", semantic_judge=lambda request: {"pass": False, "reason": "Fixture failure"})
            self.assertEqual("RESULT_FAILED", failed["claims"][0]["status"])
            (workspace / "development-log.jsonl").write_text('{"attempt": 1}\n')
            retried = retry_agent_bundle(path, "claim-001")
            # The next code review separates this submission's log entries from the following ones.
            archived = retried["claims"][0]["bundle_submissions"][-1]["development_archive"]
            self.assertIn("development-log.jsonl", archived["artifacts"])
            self.assertEqual("real-child", retried["claims"][0]["implementer"]["agent_id"])
            self.assertEqual(failed["claims"][0]["started_at"], retried["claims"][0]["started_at"])
            with self.assertRaisesRegex(ValueError, "same candidate"):
                bind_single_implementation(path, "claim-001", agent_id="real-child")
            code = workspace / "implementation/entry.py"
            code.write_text(code.read_text() + "\n# revised fixture\n")
            manifest = workspace / "implementation/manifest.json"
            value = json.loads(manifest.read_text())
            value["files"][0]["sha256"] = digest(code)
            manifest.write_text(json.dumps(value))
            bind_single_implementation(path, "claim-001", agent_id="real-child")
            evaluated = evaluate_agent_bundle(path, "claim-001", semantic_judge=_fixture_judge)
            self.assertEqual("RESULT_SUCCESS", evaluated["claims"][0]["status"])
            finished = finish_agent_harness(path)
            company = json.loads((path.parent / finished["company_result"]["path"]).read_text())
            self.assertEqual(2, company["claim_total"])
            self.assertEqual({"reproduced": 1, "not_executed": 1}, company["outcome_counts"])
            result = json.loads((path.parent / evaluated["claims"][0]["final_result"]["public_run_dir"] / "replica-result.json").read_text())
            self.assertEqual({"implementer": "low"}, result["experiment_record"]["environment"]["requested_reasoning_efforts"])

    def test_wrong_identity_effort_and_changed_artifact_cannot_be_bound(self):
        with TemporaryDirectory() as tmp:
            path, registry = prepare(Path(tmp))
            with self.assertRaisesRegex(ValueError, "reasoning effort"):
                start_single_implementation(path, "claim-001", agent_id="real-child", model="gpt-6-astra", reasoning_effort="high")
            workspace = implement(path)
            with self.assertRaisesRegex(ValueError, "bound single implementer"):
                bind_single_implementation(path, "claim-001", agent_id="other")
            bound = bind_single_implementation(path, "claim-001", agent_id="real-child")
            code = workspace / "implementation/entry.py"
            code.write_text(code.read_text() + "\n# changed after submission\n")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                validate_single_implementation(path.parent, bound["claims"][0])

    def test_development_budget_is_preserved(self):
        with TemporaryDirectory() as tmp:
            path, _ = prepare(Path(tmp))
            implement(path)
            registry = json.loads(path.read_text())
            registry["claims"][0]["started_at"] = "2000-01-01T00:00:00+00:00"
            path.write_text(json.dumps(registry))
            # A spent budget ends the claim with its reason instead of leaving it open forever.
            closed = bind_single_implementation(path, "claim-001", agent_id="real-child")
            claim = closed["claims"][0]
            self.assertEqual(("EXECUTION_FAILED", "budget_exhausted"), (claim["status"], claim["failure"]["category"]))
            self.assertFalse((path.parent / "claims/claim-001/implementer/execution-state.json").exists())
            company = json.loads((path.parent / finish_agent_harness(path)["company_result"]["path"]).read_text())
            entry = next(c for c in company["claims"] if c["claim_id"] == "claim-001")
            self.assertEqual(("experiment_blocked", "budget_exhausted"), (entry["outcome"], entry["failure_category"]))

    def test_claim_without_a_bindable_bundle_can_be_closed(self):
        with TemporaryDirectory() as tmp:
            path, _ = prepare(Path(tmp))
            start_single_implementation(path, "claim-001", agent_id="real-child", model="gpt-6-astra",
                                        reasoning_effort="low")
            with self.assertRaisesRegex(ValueError, "failure category"):
                fail_single_implementation(path, "claim-001", category="gave_up", reason="x")
            closed = fail_single_implementation(path, "claim-001", category="development_checks_failed",
                                                reason="The browser self-check still fails after two resumes.")
            self.assertEqual("EXECUTION_FAILED", closed["claims"][0]["status"])
            with self.assertRaisesRegex(ValueError, "pending or implementing"):
                fail_single_implementation(path, "claim-001", category="development_checks_failed", reason="again")
            company = json.loads((path.parent / finish_agent_harness(path)["company_result"]["path"]).read_text())
            entry = next(c for c in company["claims"] if c["claim_id"] == "claim-001")
            self.assertEqual(("experiment_incomplete", "development_checks_failed"),
                             (entry["outcome"], entry["failure_category"]))
            self.assertIn("still fails", entry["failure_reason"])

    def test_evaluation_interrupted_after_the_last_submission_is_terminal(self):
        with TemporaryDirectory() as tmp:
            path, _ = prepare(Path(tmp))
            implement(path)
            bind_single_implementation(path, "claim-001", agent_id="real-child")

            def crash(registry_path, claim_id, **_):
                registry = json.loads(registry_path.read_text())
                registry["claims"][0].setdefault("bundle_submissions", []).append(
                    {"attempt": 1, "candidate_sha256": "x", "status": "RUNNING"})
                registry_path.write_text(json.dumps(registry))
                raise RuntimeError("judge process vanished")
            with patch("replica_mvp.bundle_evaluation._evaluate_agent_bundle", crash), \
                    self.assertRaisesRegex(RuntimeError, "vanished"):
                evaluate_agent_bundle(path, "claim-001")
            claim = json.loads(path.read_text())["claims"][0]
            self.assertEqual("EVALUATION_INTERRUPTED", claim["status"])
            self.assertIn("vanished", claim["bundle_submissions"][-1]["error"])
            company = json.loads((path.parent / finish_agent_harness(path)["company_result"]["path"]).read_text())
            entry = next(c for c in company["claims"] if c["claim_id"] == "claim-001")
            self.assertEqual(("experiment_blocked", "evaluation_interrupted"), (entry["outcome"], entry["failure_category"]))
            self.assertIn("vanished", entry["failure_reason"])
