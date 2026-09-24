import hashlib
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from replica_mvp.agent_harness import (
    finalize_agent_candidate, finish_agent_continuity, finish_agent_harness,
    record_agent_continuity_round, start_agent_continuity,
)
from replica_mvp.builder import run_built_replica
from replica_mvp.bundle_evaluation import evaluate_agent_bundle, prepare_bundle_evaluation, retry_agent_bundle
from replica_mvp.bundle_runtime import native_model_judge, observe_dependencies, run_json_command
from replica_mvp.cli import main
from tests.test_agent_continuity import _prepare_rich_ready_pair, _write_execution_state
from tests.test_second_pass import _research


SOURCE = """import json, sys, time
v = json.load(sys.stdin)
json.dump({'value': v['x'] * 2, 'wording': str(time.time_ns())}, sys.stdout)
"""


def _evaluation_research():
    research = _research()
    scenario = research["claims"][0]["second_pass"]["replication_contract"][1]
    scenario["acceptance_criteria"] = ["Double the supplied value; arbitrary wording may vary."]
    def case(name, kind, value):
        return {"id": name, "kind": kind, "input": {"x": value},
                "deterministic_assertions": [{"type": "equals", "path": ["value"], "value": value * 2}],
                "semantic_criteria": [], "criterion_ids": ["criterion-001"]}
    scenario["tests"] = [case("normal", "normal", 1), case("boundary", "boundary", -2),
                         case("insufficient", "insufficient_information", 0)]
    novel = case("unseen", "novel", 18)
    novel["novelty"] = {"difference": "A new supplied numeric range with independent input data.",
                        "development_inputs": [{"x": 7, "unrelated": ["sample"]}]}
    # This is a plumbing test fixture, not evidence of generalization for a company claim.
    invariant = case("invariant", "metamorphic", 1)
    invariant["input"]["unrelated"] = ["different", "ordering"]
    invariant["metamorphic"] = {"case_id": "normal", "relation": "equal", "path": ["value"], "reason": "Ignore unrelated metadata."}
    changed = case("changed", "metamorphic", 8)
    changed["metamorphic"] = {"case_id": "normal", "relation": "different", "path": ["value"], "reason": "Changed facts must change the result."}
    scenario["evaluation"] = {
        "runtime": {"transport": "stdio_json"}, "timeout_seconds": 2,
        "repeat_policy": "contract", "additional_cases": [novel, invariant, changed],
        "public_examples": [{"input": {"x": 100}, "description": "A separate public demonstration."}],
    }
    return research


def _bound_bundle(root, source=SOURCE, research=None, dependencies=None):
    with patch("tests.test_agent_continuity._research", return_value=research or _evaluation_research()):
        registry, binding = _prepare_rich_ready_pair(root)
    claim_id = binding["claim_id"]
    start_agent_continuity(registry, claim_id, operator_agent_id=binding["operator_agent_id"],
                           builder_agent_id=binding["builder_agent_id"], nonce=binding["nonce"])
    record_agent_continuity_round(registry, claim_id, round_number=0,
                                  operator_agent_id=binding["operator_agent_id"], builder_agent_id=binding["builder_agent_id"],
                                  nonce=binding["nonce"], operator_to_builder_direct=True, builder_to_operator_direct=True)
    candidate_relative = f"claims/{claim_id}/builder/implementation/manifest.json"
    state = _write_execution_state(registry, binding, terminal_state="SUCCESS", correction_count=0,
                                  candidate_path=candidate_relative)
    finish_agent_continuity(registry, claim_id, terminal_state="SUCCESS", execution_state_path=state,
                           operator_agent_id=binding["operator_agent_id"], builder_agent_id=binding["builder_agent_id"],
                           nonce=binding["nonce"], terminal_acknowledged_directly=True)
    manifest_path = root / candidate_relative
    manifest_path.parent.mkdir()
    code = manifest_path.parent / "entry.py"
    code.write_text(source)
    claim = json.loads((root / f"claims/{claim_id}/claim.json").read_text())
    manifest = {
        "schema_version": "replica-implementation-bundle/v1", "claim_id": claim_id, "scenario_id": "s-oss",
        "implementation_type": "code", "dependency_level": "oss_only", "input_contract": claim["input_contract"],
        "output_contract": claim["output_contract"], "entrypoint": "entry.py", "command": [sys.executable, "entry.py"],
        "dependencies": dependencies or [], "environment_variables": [],
        "files": [{"path": "entry.py", "sha256": hashlib.sha256(code.read_bytes()).hexdigest()}],
    }
    manifest_path.write_text(json.dumps(manifest))
    finalize_agent_candidate(registry, claim_id, manifest_path)
    return registry


def _fixture_judge(request):
    return {"pass": True, "reason": "Controlled test evaluator; not a real company assessment."}


class BundleEvaluationTest(unittest.TestCase):
    def test_generated_bytecode_is_excluded_without_relaxing_package_limits(self):
        from replica_mvp.agent_harness import _validate_implementation_bundle
        with TemporaryDirectory() as tmp:
            registry = _bound_bundle(Path(tmp) / "run")
            claim = json.loads(registry.read_text())["claims"][0]
            manifest = registry.parent / claim["implementation_result"]["candidate_path"]
            cache = manifest.parent / "__pycache__"
            cache.mkdir()
            (cache / "entry.cpython-312.pyc").write_bytes(b"Unused generated cache")
            payload = json.loads((registry.parent / claim["claim_payload_path"]).read_text())
            with patch("replica_mvp.agent_harness.MAX_BUNDLE_BYTES", 1):
                with self.assertRaisesRegex(ValueError, "size limit"):
                    _validate_implementation_bundle(registry.parent, "claim-001", manifest, payload)
            final = evaluate_agent_bundle(registry, "claim-001", semantic_judge=_fixture_judge)["claims"][0]
            public = registry.parent / final["final_result"]["public_run_dir"]
            self.assertFalse(list(public.rglob("*.pyc")))
            self.assertEqual("RESULT_SUCCESS", final["status"])

    def test_observes_stdlib_and_bundled_cli_versions(self):
        import sqlite3
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Version-probe fixture only; never a production workflow engine.
            binary = root / "dagu"
            binary.write_text(f"#!{sys.executable}\nimport sys\nassert sys.argv[1:] == ['version']\nprint('dagu v2.16.2')\n")
            binary.chmod(0o755)
            manifest = {"command": [sys.executable], "dependencies": [
                {"name": "Python sqlite3", "version": sys.version.split()[0]},
                {"name": "sqlite3", "version": sqlite3.sqlite_version},
                {"name": "dagu", "version": "2.16.2"}]}
            observations = observe_dependencies(manifest, root)
            self.assertTrue(all(d["status"] == "matched" for d in observations), observations)

    def test_rejected_packaging_reopens_same_pair_before_sealed_evaluation(self):
        from replica_mvp.agent_execution import advance_agent_execution
        from tests.test_agent_execution import _instruction, _feedback
        with TemporaryDirectory() as tmp:
            registry = _bound_bundle(Path(tmp) / "run")
            recorded = json.loads(registry.read_text())
            claim = recorded["claims"][0]
            manifest = registry.parent / claim["implementation_result"]["candidate_path"]
            claim.pop("implementation_result")
            claim["status"] = "EXECUTION_SUCCESS"
            registry.write_text(json.dumps(recorded))
            with self.assertRaisesRegex(ValueError, "valid package"):
                retry_agent_bundle(registry, "claim-001")
            (manifest.parent / "development-cache.txt").write_text("Disposable local test residue")
            with self.assertRaisesRegex(ValueError, "undeclared"):
                finalize_agent_candidate(registry, "claim-001", manifest)
            state_path = registry.parent / claim["operator"]["artifact_namespace"] / "execution-state.json"
            previous = json.loads(state_path.read_text())
            ready = retry_agent_bundle(registry, "claim-001")["claims"][0]
            self.assertEqual("READY_FOR_PROTOCOL", ready["status"])
            self.assertFalse(ready.get("bundle_submissions"))
            self.assertEqual(claim["operator"], ready["operator"])
            self.assertEqual(claim["builder"], ready["builder"])
            self.assertEqual(claim["smoke"], ready["smoke"])
            current = json.loads(state_path.read_text())
            self.assertEqual(previous["started_at"], current["started_at"])
            self.assertEqual(previous["budget"], current["budget"])
            archive = registry.parent / ready["packaging_retries"][0]["development_archive"]["path"]
            self.assertEqual(previous, json.loads((archive / "execution-state.json").read_text()))
            self.assertEqual(manifest.read_bytes(), (archive / "implementation" / "manifest.json").read_bytes())
            self.assertFalse((archive / "implementation" / "development-cache.txt").exists())
            binding = {"operator_agent_id": ready["operator"]["agent_id"],
                       "builder_agent_id": ready["builder"]["agent_id"], "nonce": ready["smoke"]["nonce"]}
            start_agent_continuity(registry, "claim-001", **binding)
            record_agent_continuity_round(registry, "claim-001", round_number=0, **binding,
                                         operator_to_builder_direct=True, builder_to_operator_direct=True)
            messages = {"claim": json.loads((registry.parent / ready["claim_payload_path"]).read_text()),
                        "claim_id": "claim-001", "operator_id": binding["operator_agent_id"],
                        "builder_id": binding["builder_agent_id"], "nonce": binding["nonce"],
                        "candidate_path": manifest.relative_to(registry.parent).as_posix()}
            current = advance_agent_execution(current, _instruction(**messages), _feedback(**messages))
            state_path.write_text(json.dumps(current))
            (manifest.parent / "development-cache.txt").unlink()
            finish_agent_continuity(registry, "claim-001", **binding, terminal_state="SUCCESS",
                                    terminal_acknowledged_directly=True, execution_state_path=state_path)
            self.assertEqual("IMPLEMENTATION_READY", finalize_agent_candidate(registry, "claim-001", manifest)["claims"][0]["status"])

    def test_cli_finalization_runs_the_default_evaluator(self):
        with TemporaryDirectory() as tmp:
            registry = _bound_bundle(Path(tmp) / "run")
            bound = json.loads(registry.read_text())
            manifest = registry.parent / bound["claims"][0]["implementation_result"]["candidate_path"]
            bound["claims"][0].pop("implementation_result")
            bound["claims"][0]["status"] = "EXECUTION_SUCCESS"
            registry.write_text(json.dumps(bound))
            with patch("replica_mvp.cli.native_model_judge", side_effect=lambda provider, request: _fixture_judge(request)) as judge:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(0, main(["agent-candidate-finalize", str(registry), "claim-001", str(manifest)]))
            self.assertTrue(judge.called)
            self.assertIn("selected_scenario", judge.call_args.args[1])
            self.assertEqual("RESULT_SUCCESS", json.loads(registry.read_text())["claims"][0]["status"])

    def test_native_judge_records_actual_cli_usage_and_rejects_invalid_verdict(self):
        def command(argv, value, cwd, timeout):
            (cwd / "verdict.json").write_text(json.dumps({"pass": True, "reason": "Fixture verdict."}))
            self.assertIn("--ignore-rules", argv)
            self.assertIn("read-only", argv)
            return b'{"type":"turn.completed","usage":{"input_tokens":31,"output_tokens":7}}\n'
        with patch("replica_mvp.bundle_runtime._run_command", side_effect=command):
            result = native_model_judge("codex", {"timeout_seconds": 2})
        self.assertEqual([31, 7], [m["value"] for m in result["resources"]["measurements"]])
        with patch("replica_mvp.bundle_runtime.run_json_command", return_value={"structured_output": {"pass": "true", "reason": "invalid"}}):
            with self.assertRaisesRegex(RuntimeError, "invalid verdict"):
                native_model_judge("claude", {"timeout_seconds": 2})

    def test_public_examples_and_repeats_start_without_sealed_state(self):
        source = '''import json,sys
from pathlib import Path
v=json.load(sys.stdin)
p=Path('history.json'); history=json.loads(p.read_text()) if p.exists() else []
history.append(v['x']);p.write_text(json.dumps(history))
json.dump({'value':v['x']*2,'history':history},sys.stdout)
'''
        with TemporaryDirectory() as tmp:
            registry = _bound_bundle(Path(tmp) / "run", source=source)
            result = evaluate_agent_bundle(registry, "claim-001", semantic_judge=_fixture_judge)
            claim = result["claims"][0]
            public = registry.parent / claim["final_result"]["public_run_dir"]
            self.assertEqual([100], json.loads((public / "public-examples.json").read_text())[0]["output"]["history"])
            self.assertEqual([[3], [3, 9]], [o["history"] for o in run_built_replica(public, [{"x": 3}, {"x": 9}], session=True)])
            vault = registry.parent / claim["final_result"]["vault_dir"]
            self.assertEqual([1], json.loads((vault / "repeated_outputs.jsonl").read_text().splitlines()[0])["output"]["history"])

    def test_new_input_assets_can_be_used_without_overwriting_code(self):
        source = '''import json,sys
from pathlib import Path
v=json.load(sys.stdin)
n=int(Path(v['path']).read_text()) if 'path' in v else v['x']
json.dump({'value':n*2},sys.stdout)
'''
        with TemporaryDirectory() as tmp:
            registry = _bound_bundle(Path(tmp) / "run", source=source)
            result = evaluate_agent_bundle(registry, "claim-001", semantic_judge=_fixture_judge)
            public = registry.parent / result["claims"][0]["final_result"]["public_run_dir"]
            asset = Path(tmp) / "new-number.txt"
            asset.write_text("39")
            self.assertEqual({"value": 78}, run_built_replica(public, {"path": "inputs/other.txt"}, input_assets={"inputs/other.txt": str(asset)}))
            with self.assertRaisesRegex(ValueError, "overwrite"):
                run_built_replica(public, {"x": 1}, input_assets={"entry.py": str(asset)})
            with self.assertRaisesRegex(ValueError, "safe runtime-relative"):
                run_built_replica(public, {"x": 1}, input_assets={"../escaped": str(asset)})

    def test_failed_evaluation_reopens_same_pair_preserving_budget_and_history(self):
        from replica_mvp.agent_execution import advance_agent_execution
        from tests.test_agent_execution import _instruction, _feedback
        with TemporaryDirectory() as tmp:
            registry = _bound_bundle(Path(tmp) / "run", source=SOURCE.replace("* 2", "* 3"))
            first = evaluate_agent_bundle(registry, "claim-001", semantic_judge=_fixture_judge)["claims"][0]
            previous_public = registry.parent / first["final_result"]["public_run_dir"]
            previous_bytes = (previous_public / "replica-result.json").read_bytes()
            finish_agent_harness(registry)
            ready = retry_agent_bundle(registry, "claim-001")["claims"][0]
            self.assertEqual("READY_FOR_PROTOCOL", json.loads(registry.read_text())["replica_agent"]["status"])
            binding = {"operator_agent_id": ready["operator"]["agent_id"], "builder_agent_id": ready["builder"]["agent_id"], "nonce": ready["smoke"]["nonce"]}
            self.assertEqual(first["operator"]["agent_id"], binding["operator_agent_id"])
            state_path = registry.parent / ready["operator"]["artifact_namespace"] / "execution-state.json"
            state = json.loads(state_path.read_text())
            self.assertEqual(1, len(state["prior_resources"]))
            start_agent_continuity(registry, "claim-001", **binding)
            record_agent_continuity_round(registry, "claim-001", round_number=0, **binding,
                                          operator_to_builder_direct=True, builder_to_operator_direct=True)
            candidate = first["implementation_result"]["candidate_path"]
            payload = json.loads((registry.parent / ready["claim_payload_path"]).read_text())
            messages = {"claim": payload, "claim_id": "claim-001", "operator_id": binding["operator_agent_id"],
                        "builder_id": binding["builder_agent_id"], "nonce": binding["nonce"], "candidate_path": candidate}
            state = advance_agent_execution(state, _instruction(0, **messages), _feedback(0, passed=True, **messages))
            state_path.write_text(json.dumps(state))
            finish_agent_continuity(registry, "claim-001", terminal_state="SUCCESS", **binding,
                                    terminal_acknowledged_directly=True, execution_state_path=state_path)
            manifest_path = registry.parent / candidate
            with self.assertRaisesRegex(ValueError, "same candidate"):
                finalize_agent_candidate(registry, "claim-001", manifest_path)
            manifest = json.loads(manifest_path.read_text())
            (manifest_path.parent / "entry.py").write_text(SOURCE)
            manifest["files"][0]["sha256"] = hashlib.sha256(SOURCE.encode()).hexdigest()
            manifest_path.write_text(json.dumps(manifest))
            finalize_agent_candidate(registry, "claim-001", manifest_path)
            second = evaluate_agent_bundle(registry, "claim-001", semantic_judge=_fixture_judge)["claims"][0]
            self.assertEqual("RESULT_SUCCESS", second["status"])
            self.assertEqual(2, len(second["bundle_submissions"]))
            self.assertEqual(previous_bytes, (previous_public / "replica-result.json").read_bytes())
            public = registry.parent / second["final_result"]["public_run_dir"]
            self.assertEqual(2, len(json.loads((public / "replica-result.json").read_text())["development_attempts"]))
            self.assertEqual("EXECUTION_SUCCESS", finish_agent_harness(registry)["status"])
            archive = registry.parent / second["bundle_submissions"][0]["development_archive"]["path"]
            (archive / "execution-state.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "prior development artifact"):
                finish_agent_harness(registry)

    def test_interruption_is_recorded_and_counts_as_a_submission(self):
        with TemporaryDirectory() as tmp:
            registry = _bound_bundle(Path(tmp) / "run")
            with patch("replica_mvp.bundle_evaluation._evaluate_cases", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    evaluate_agent_bundle(registry, "claim-001")
            claim = json.loads(registry.read_text())["claims"][0]
            self.assertEqual("EVALUATION_INTERRUPTED", claim["status"])
            self.assertEqual("INTERRUPTED", claim["bundle_submissions"][0]["status"])
            self.assertEqual("READY_FOR_PROTOCOL", retry_agent_bundle(registry, "claim-001")["claims"][0]["status"])

    def test_submission_and_cumulative_time_limits_prevent_another_retry(self):
        with TemporaryDirectory() as tmp:
            registry = _bound_bundle(Path(tmp) / "run", source="raise RuntimeError('broken')")
            state = evaluate_agent_bundle(registry, "claim-001")
            attempts = state["claims"][0]["bundle_submissions"]
            attempts[0]["elapsed_seconds"] = 600
            registry.write_text(json.dumps(state))
            with self.assertRaisesRegex(ValueError, "evaluation time budget"):
                retry_agent_bundle(registry, "claim-001")
            attempts.extend([dict(attempts[0]), dict(attempts[0])])
            registry.write_text(json.dumps(state))
            with self.assertRaisesRegex(ValueError, "three sealed submissions"):
                retry_agent_bundle(registry, "claim-001")

    def test_separate_evaluation_publishes_the_same_bundle_and_runs_new_input(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            registry = _bound_bundle(root)
            result = evaluate_agent_bundle(registry, "claim-001", semantic_judge=_fixture_judge, judge_identity="test-judge")
            claim = result["claims"][0]
            self.assertEqual("RESULT_SUCCESS", claim["status"])
            public = root / claim["final_result"]["public_run_dir"]
            self.assertEqual(26, run_built_replica(public, {"x": 13})["value"])
            names = {p.name for p in public.rglob("*")}
            self.assertTrue({"replica.json", "replica-result.json", "completion-assessment.json"} <= names)
            self.assertFalse({"tests.json", "results.jsonl", "replica_outputs.jsonl", "implementation-review.json", "report.md"} & names)
            value = json.loads((public / "replica-result.json").read_text())
            self.assertEqual(6, value["evaluation"]["total"])
            unknown = [m for m in value["resources"]["measurements"] if m["status"] == "unknown"]
            self.assertTrue(unknown)
            self.assertTrue(all(m["value"] is None for m in unknown))
            with self.assertRaisesRegex(ValueError, "IMPLEMENTATION_READY"):
                evaluate_agent_bundle(registry, "claim-001")
            self.assertEqual("EXECUTION_SUCCESS", finish_agent_harness(registry)["status"])
            (public / "implementation/entry.py").write_text("print('tampered')")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                run_built_replica(public, {"x": 13})
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                finish_agent_harness(registry)

    def test_builder_success_does_not_hide_actual_runtime_failure(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            registry = _bound_bundle(root, "raise RuntimeError('failed production dependency')")
            result = evaluate_agent_bundle(registry, "claim-001", semantic_judge=_fixture_judge)
            claim = result["claims"][0]
            self.assertEqual("RESULT_FAILED", claim["status"])
            self.assertEqual("not_reproduced_on_this_path", claim["final_result"]["reproduction_status"])
            vault = root / claim["final_result"]["vault_dir"]
            self.assertIn("failed production dependency", (vault / "results.jsonl").read_text())
            public = root / claim["final_result"]["public_run_dir"]
            self.assertNotIn("failed production dependency", (public / "replica-result.json").read_text())

    def test_exact_repeat_still_rejects_changed_required_output(self):
        with TemporaryDirectory() as tmp:
            research = _evaluation_research()
            research["claims"][0]["second_pass"]["replication_contract"][1]["evaluation"]["repeat_policy"] = "exact"
            result = evaluate_agent_bundle(_bound_bundle(Path(tmp) / "run", research=research), "claim-001", semantic_judge=_fixture_judge)
            self.assertEqual("partially_reproduced", result["claims"][0]["final_result"]["reproduction_status"])

    def test_semantic_criteria_check_both_repetitions(self):
        with TemporaryDirectory() as tmp:
            research = _evaluation_research()
            research["claims"][0]["second_pass"]["replication_contract"][1]["tests"][0]["semantic_criteria"] = ["A required fact remains correct."]
            seen = []
            def judge(request):
                seen.append(request)
                return {"pass": False, "reason": "Required behavior is wrong."}
            result = evaluate_agent_bundle(_bound_bundle(Path(tmp) / "run", research=research), "claim-001", semantic_judge=judge)
            self.assertEqual("RESULT_FAILED", result["claims"][0]["status"])
            quality = next(r for r in seen if r["stage"] == "quality")
            self.assertIn("repeated_output", quality)
            self.assertNotEqual(quality["replica_output"]["wording"], quality["repeated_output"]["wording"])

    def test_frozen_plan_tampering_is_rejected_before_execution(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            registry = _bound_bundle(root)
            state = json.loads(registry.read_text())
            plan = root / state["claims"][0]["bundle_evaluation"]["plan_path"]
            plan.write_text(plan.read_text() + " ")
            with self.assertRaisesRegex(ValueError, "plan hash mismatch"):
                evaluate_agent_bundle(registry, "claim-001")

    def test_missing_novelty_is_not_promoted_by_a_pass_label(self):
        with TemporaryDirectory() as tmp:
            research = _evaluation_research()
            del research["claims"][0]["second_pass"]["replication_contract"][1]["evaluation"]["additional_cases"][0]["novelty"]
            result = evaluate_agent_bundle(_bound_bundle(Path(tmp) / "run", research=research), "claim-001", semantic_judge=_fixture_judge)
            self.assertEqual("partially_reproduced", result["claims"][0]["final_result"]["reproduction_status"])

    def test_no_judge_cannot_claim_workflow_fidelity(self):
        with TemporaryDirectory() as tmp:
            result = evaluate_agent_bundle(_bound_bundle(Path(tmp) / "run"), "claim-001")
            self.assertEqual("partially_reproduced", result["claims"][0]["final_result"]["reproduction_status"])

    def test_command_timeout_and_invalid_json_are_real_failures(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(TimeoutError):
                run_json_command([sys.executable, "-c", "import time; time.sleep(10)"], {}, root, 0.05)
            with self.assertRaisesRegex(RuntimeError, "standard JSON"):
                run_json_command([sys.executable, "-c", "print('NaN')"], {}, root, 1)

    def test_supplement_cannot_change_existing_research_expectations(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            registry = _bound_bundle(root)
            supplement = Path(tmp) / "supplement.json"
            supplement.write_text(json.dumps({"case_checks": {"normal": {"input": {"x": 999}}}}))
            with self.assertRaisesRegex(ValueError, "not replace"):
                prepare_bundle_evaluation(registry, "claim-001", supplement)

    def test_file_outputs_survive_evaluation_and_a_new_published_run(self):
        with TemporaryDirectory() as tmp:
            research = _evaluation_research()
            config = research["claims"][0]["second_pass"]["replication_contract"][1]["evaluation"]
            config["output_artifacts"] = [{"path": ["document"], "media_type": "text/plain"}]
            for case in config["additional_cases"]:
                if "metamorphic" in case:
                    case["metamorphic"]["path"] = ["document"]
            source = """import json,sys
from pathlib import Path
v=json.load(sys.stdin)
Path('answer.txt').write_text(str(v['x'] * 2))
json.dump({'value':v['x'] * 2,'document':'answer.txt'},sys.stdout)
"""
            root = Path(tmp) / "run"
            registry = _bound_bundle(root, source, research)
            def inspect_review(request):
                if request["stage"] == "implementation_review":
                    self.assertEqual({"transport": "stdio_json"}, request["evaluation_runtime"])
                    self.assertEqual("oss_only", request["effective_dependency_level"])
                    self.assertTrue(request["execution_records"])
                    self.assertEqual(6, len(request["repeated_outputs"]))
                    captures = request["preserved_artifacts"]["normal"]
                    self.assertEqual(2, len(captures))
                    for repetition in captures:
                        artifact = Path(repetition[0]["path"])
                        self.assertTrue(artifact.is_absolute())
                        self.assertEqual("2", artifact.read_text())
                return _fixture_judge(request)
            result = evaluate_agent_bundle(registry, "claim-001", semantic_judge=inspect_review)
            public = root / result["claims"][0]["final_result"]["public_run_dir"]
            examples = json.loads((public / "public-examples.json").read_text())
            self.assertEqual("200", (public / examples[0]["output"]["document"]).read_text())
            output = run_built_replica(public, {"x": 63})
            generated = Path(output["document"])
            self.assertEqual("126", generated.read_text())
            generated.unlink()
            generated.parent.rmdir()
            self.assertEqual("RESULT_SUCCESS", result["claims"][0]["status"])

    def test_missing_public_input_asset_keeps_a_blocked_result(self):
        with TemporaryDirectory() as tmp:
            research = _evaluation_research()
            research["claims"][0]["second_pass"]["replication_contract"][1]["evaluation"]["assets"] = [{
                "path": "input.txt", "source": str(Path(tmp) / "missing.txt"), "sha256": "a" * 64,
                "media_type": "text/plain", "provenance": "Permitted test fixture", "usage_terms": "Synthetic fixture",
                "visibility": "public",
            }]
            result = evaluate_agent_bundle(_bound_bundle(Path(tmp) / "run", research=research), "claim-001")
            self.assertEqual("execution_blocked", result["claims"][0]["final_result"]["reproduction_status"])
            self.assertTrue((Path(tmp) / "run" / result["claims"][0]["final_result"]["public_run_dir"] / "replica-result.json").is_file())

    def test_installed_dependency_drift_is_observed_not_silently_certified(self):
        with TemporaryDirectory() as tmp:
            dependency = {"name": "pip", "version": "0.0.0", "source": "https://pip.pypa.io/", "license": "MIT"}
            registry = _bound_bundle(Path(tmp) / "run", dependencies=[dependency])
            result = evaluate_agent_bundle(registry, "claim-001", semantic_judge=_fixture_judge)
            public = registry.parent / result["claims"][0]["final_result"]["public_run_dir"]
            record = json.loads((public / "replica-result.json").read_text())
            self.assertEqual("different", record["dependencies"][0]["status"])
            self.assertEqual("partially_reproduced", record["reproduction_status"])

    def test_http_entrypoint_is_started_and_the_published_bundle_runs(self):
        source = '''import argparse,json
from pathlib import Path
from http.server import BaseHTTPRequestHandler,HTTPServer
factor=int(Path('factor.txt').read_text())
class Handler(BaseHTTPRequestHandler):
 def do_POST(self):
  v=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
  b=json.dumps({'value':v['x']*factor}).encode()
  self.send_response(200);self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def log_message(self,*args): pass
p=argparse.ArgumentParser();p.add_argument('--port',type=int);a=p.parse_args()
HTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
'''
        with TemporaryDirectory() as tmp:
            research = _evaluation_research()
            config = research["claims"][0]["second_pass"]["replication_contract"][1]["evaluation"]
            config["runtime"] = {
                "transport": "http_json", "endpoint": "/run", "port_argument": "--port",
            }
            factor = Path(tmp) / "factor.txt"
            factor.write_text("2")
            config["assets"] = [{"path": "factor.txt", "source": str(factor), "sha256": hashlib.sha256(b"2").hexdigest(),
                                  "media_type": "text/plain", "provenance": "test fixture", "usage_terms": "synthetic", "visibility": "public"}]
            registry = _bound_bundle(Path(tmp) / "run", source=source, research=research)
            contract = json.loads((registry.parent / "claims/claim-001/runtime-contract-001.json").read_text())
            self.assertEqual(config["public_examples"], contract["public_examples"])
            self.assertNotIn("additional_cases", contract)
            result = evaluate_agent_bundle(registry, "claim-001", semantic_judge=_fixture_judge)
            public = registry.parent / result["claims"][0]["final_result"]["public_run_dir"]
            self.assertEqual("RESULT_SUCCESS", result["claims"][0]["status"])
            self.assertEqual({"value": 76}, run_built_replica(public, {"x": 38}))

    def test_http_redirect_and_slow_stream_cannot_pass_as_bundle_execution(self):
        source = '''import argparse,time
from http.server import BaseHTTPRequestHandler,HTTPServer
class Handler(BaseHTTPRequestHandler):
 def do_POST(self):
  BODY
 def log_message(self,*args): pass
p=argparse.ArgumentParser();p.add_argument('--port',type=int);a=p.parse_args()
HTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
'''
        for body, category in (("self.send_response(302);self.send_header('Location','http://127.0.0.1:1/other');self.end_headers()", "implementation_defect"),
                               ("self.send_response(200);self.send_header('Content-Length','999');self.end_headers()\n  for i in range(100): self.wfile.write(b' ');self.wfile.flush();time.sleep(.03)", "budget_exhausted")):
            with self.subTest(category=category), TemporaryDirectory() as tmp:
                research = _evaluation_research()
                config = research["claims"][0]["second_pass"]["replication_contract"][1]["evaluation"]
                config["runtime"] = {"transport": "http_json", "endpoint": "/run", "port_argument": "--port"}
                config["timeout_seconds"] = .3
                registry = _bound_bundle(Path(tmp) / "run", source=source.replace("BODY", body), research=research)
                result = evaluate_agent_bundle(registry, "claim-001")
                public = registry.parent / result["claims"][0]["final_result"]["public_run_dir"]
                self.assertEqual(category, json.loads((public / "replica-result.json").read_text())["failure_category"])


if __name__ == "__main__":
    unittest.main()
