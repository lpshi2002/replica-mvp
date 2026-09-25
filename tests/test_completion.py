import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from replica_mvp import assess_replica_completion


def _write_run(run_dir: Path, *, include_novel: bool) -> dict:
    kinds = ["normal", "boundary", "insufficient_information"]
    if include_novel:
        kinds.append("novel")
    cases = [
        {
            "id": kind,
            "kind": kind,
            "input": {"prompt": kind},
        }
        for kind in kinds
    ]
    tests_bytes = json.dumps(
        {"schema_version": "replica-tests/v1", "cases": cases}
    ).encode()
    (run_dir / "tests.json").write_bytes(tests_bytes)
    tests_sha256 = hashlib.sha256(tests_bytes).hexdigest()
    (run_dir / "test-suite-lock.json").write_text(
        json.dumps(
            {
                "schema_version": "replica-test-lock/v1",
                "status": "FROZEN",
                "sha256": tests_sha256,
                "case_count": len(cases),
            }
        ),
        encoding="utf-8",
    )
    outputs_bytes = "".join(
        json.dumps({"case_id": case["id"], "output": case["kind"]}) + "\n"
        for case in cases
    ).encode()
    (run_dir / "replica_outputs.jsonl").write_bytes(outputs_bytes)
    results_bytes = "".join(
        json.dumps({"case_id": case["id"], "pass": True}) + "\n"
        for case in cases
    ).encode()
    (run_dir / "results.jsonl").write_bytes(results_bytes)
    evaluation = {
        "schema_version": "replica-evaluation-summary/v1",
        "status": "PASSED",
        "passed": len(cases),
        "total": len(cases),
        "test_suite_sha256": tests_sha256,
        "outputs_sha256": hashlib.sha256(outputs_bytes).hexdigest(),
        "results_sha256": hashlib.sha256(results_bytes).hexdigest(),
        "judge_identity": "independent-test-judge/v1",
        "judge_mode": "independent",
    }
    (run_dir / "evaluation-summary.json").write_text(
        json.dumps(evaluation),
        encoding="utf-8",
    )
    (run_dir / "replica.json").write_text("{}\n", encoding="utf-8")
    generated_source = "def replicate(runtime_input):\n    return runtime_input\n"
    (run_dir / "generated-component.py").write_text(
        generated_source,
        encoding="utf-8",
    )
    component = {
        "schema_version": "replica-generated-component/v1",
        "language": "replica-python/v1",
        "input_contract": {},
        "output_contract": {},
        "source": generated_source,
    }
    component_sha256 = hashlib.sha256(
        json.dumps(
            component,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    request = {"fixture": "completion"}
    request_sha256 = hashlib.sha256(
        json.dumps(
            request,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    (run_dir / "generated-component.json").write_text(
        json.dumps(
            {
                "schema_version": "replica-generated-component-record/v1",
                "component_sha256": component_sha256,
                "request_sha256": request_sha256,
                "request": request,
                "component": component,
            }
        ),
        encoding="utf-8",
    )
    execution_plan = {
        "schema_version": "replica-execution-plan/v1",
        "steps": [
            {
                "operation": "execute_generated_component",
                "inputs": {
                    "component_sha256": component_sha256,
                    "request_sha256": request_sha256,
                },
            }
        ],
    }
    (run_dir / "execution-plan.json").write_text(
        json.dumps(execution_plan),
        encoding="utf-8",
    )
    (run_dir / "replica.json").write_text(
        json.dumps({"execution_plan": execution_plan}),
        encoding="utf-8",
    )
    implementation_dir = run_dir / "implementation"
    implementation_dir.mkdir()
    (implementation_dir / "replica.py").write_text(
        generated_source,
        encoding="utf-8",
    )
    (implementation_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "replica-implementation/v1",
                "entrypoint": "replica.py",
                "command": "replica-mvp run-replica RUN_DIR < INPUT.json",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "report.md").write_text("# Final report\n", encoding="utf-8")
    return evaluation


def _completion_contract(run_dir: Path, *, dependency_level="oss_only") -> dict:
    suite = json.loads((run_dir / "tests.json").read_text(encoding="utf-8"))
    return {
        "dependency_level": dependency_level,
        "dependencies": ["Python standard library"],
        "public_sources": [
            {
                "url": "https://example.com/product",
                "finding": "The public feature accepts a prompt and returns text.",
            }
        ],
        "input_assets": [
            {
                "id": "public-synthetic-input",
                "kind": "structured_json",
                "location": "tests.json",
                "visibility": "evaluation_vault",
                "sha256": hashlib.sha256(
                    (run_dir / "tests.json").read_bytes()
                ).hexdigest(),
                "case_ids": [case["id"] for case in suite["cases"]],
            }
        ],
        "implementation_scenario": "oss-generated-python",
    }


def _write_completion_report(run_dir: Path, contract: dict) -> None:
    suite = json.loads((run_dir / "tests.json").read_text(encoding="utf-8"))
    outputs = [
        json.loads(line)
        for line in (run_dir / "replica_outputs.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    results = [
        json.loads(line)
        for line in (run_dir / "results.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    payload = {
        "schema_version": "replica-completion-report/v1",
        "dependency_level": contract["dependency_level"],
        "dependencies": contract["dependencies"],
        "implementation_scenario": contract["implementation_scenario"],
        "public_sources": contract["public_sources"],
        "input_assets": contract["input_assets"],
        "cases": [
            {
                "case_id": case["id"],
                "kind": case["kind"],
                "input": case["input"],
                "output": output["output"],
                "pass": result["pass"],
            }
            for case, output, result in zip(
                suite["cases"], outputs, results, strict=True
            )
        ],
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    (run_dir / "completion-report.json").write_text(
        rendered + "\n",
        encoding="utf-8",
    )
    (run_dir / "report.md").write_text(
        f"# Final report\n\n## Replica completion evidence\n\n"
        f"```json\n{rendered}\n```\n",
        encoding="utf-8",
    )


class ReplicaCompletionTest(unittest.TestCase):
    def test_blocked_execution_is_reported_separately(self):
        with TemporaryDirectory() as tmp:
            assessment = assess_replica_completion(
                Path(tmp),
                {},
                {"status": "BLOCKED"},
                report_available=False,
            )

        self.assertEqual("execution_blocked", assessment["status"])

    def test_incomplete_demo_cannot_be_marked_reproduced(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_run(run_dir, include_novel=False)

            assessment = assess_replica_completion(
                run_dir,
                {},
                json.loads(
                    (run_dir / "evaluation-summary.json").read_text(
                        encoding="utf-8"
                    )
                ),
                report_available=False,
            )

        self.assertEqual("partially_reproduced", assessment["status"])
        failed = {
            check["id"] for check in assessment["checks"] if not check["pass"]
        }
        self.assertIn("public_evidence", failed)
        self.assertIn("dependency_record", failed)
        self.assertIn("novel_input", failed)
        self.assertIn("final_report", failed)

    def test_full_completion_contract_can_be_marked_reproduced(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            evaluation = _write_run(run_dir, include_novel=True)
            contract = _completion_contract(run_dir)
            _write_completion_report(run_dir, contract)

            assessment = assess_replica_completion(
                run_dir,
                {"completion_contract": contract},
                evaluation,
                report_available=True,
            )

        self.assertEqual("reproduced", assessment["status"])
        self.assertTrue(all(check["pass"] for check in assessment["checks"]))

    def test_failed_evaluation_is_not_reproduced_on_this_path(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_run(run_dir, include_novel=True)

            assessment = assess_replica_completion(
                run_dir,
                {"completion_contract": _completion_contract(run_dir)},
                {"status": "FAILED"},
                report_available=True,
            )

        self.assertEqual("not_reproduced_on_this_path", assessment["status"])

    def test_commercial_api_declaration_is_not_supported(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            evaluation = _write_run(run_dir, include_novel=True)
            contract = _completion_contract(
                run_dir,
                dependency_level="commercial_api",
            )
            _write_completion_report(run_dir, contract)

            assessment = assess_replica_completion(
                run_dir,
                {"completion_contract": contract},
                evaluation,
                report_available=True,
            )

        self.assertEqual("partially_reproduced", assessment["status"])
        dependency_execution = next(
            check
            for check in assessment["checks"]
            if check["id"] == "dependency_execution"
        )
        self.assertFalse(dependency_execution["pass"])

    def test_one_line_report_cannot_satisfy_completion_standard(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            evaluation = _write_run(run_dir, include_novel=True)

            assessment = assess_replica_completion(
                run_dir,
                {"completion_contract": _completion_contract(run_dir)},
                evaluation,
                report_available=True,
            )

        self.assertEqual("partially_reproduced", assessment["status"])
        final_report = next(
            check
            for check in assessment["checks"]
            if check["id"] == "final_report"
        )
        self.assertFalse(final_report["pass"])

    def test_report_output_must_match_the_executed_replica_output(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            evaluation = _write_run(run_dir, include_novel=True)
            contract = _completion_contract(run_dir)
            _write_completion_report(run_dir, contract)
            forged = json.loads(
                (run_dir / "completion-report.json").read_text(
                    encoding="utf-8"
                )
            )
            forged["cases"][0]["output"] = "forged output"
            rendered = json.dumps(
                forged,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            (run_dir / "completion-report.json").write_text(
                rendered + "\n",
                encoding="utf-8",
            )
            (run_dir / "report.md").write_text(
                f"# Final report\n\n## Replica completion evidence\n\n"
                f"```json\n{rendered}\n```\n",
                encoding="utf-8",
            )

            assessment = assess_replica_completion(
                run_dir,
                {"completion_contract": contract},
                evaluation,
                report_available=True,
            )

        self.assertEqual("partially_reproduced", assessment["status"])
        final_report = next(
            check
            for check in assessment["checks"]
            if check["id"] == "final_report"
        )
        self.assertFalse(final_report["pass"])

    def test_unexecuted_oss_dependency_cannot_satisfy_execution_check(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            evaluation = _write_run(run_dir, include_novel=True)
            contract = _completion_contract(run_dir)
            contract["dependencies"] = ["requests"]
            _write_completion_report(run_dir, contract)

            assessment = assess_replica_completion(
                run_dir,
                {"completion_contract": contract},
                evaluation,
                report_available=True,
            )

        self.assertEqual("partially_reproduced", assessment["status"])
        dependency_execution = next(
            check
            for check in assessment["checks"]
            if check["id"] == "dependency_execution"
        )
        self.assertFalse(dependency_execution["pass"])

    def test_manifest_entrypoint_cannot_escape_implementation_directory(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            evaluation = _write_run(run_dir, include_novel=True)
            contract = _completion_contract(run_dir)
            _write_completion_report(run_dir, contract)
            manifest_path = run_dir / "implementation" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["entrypoint"] = "../generated-component.py"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            assessment = assess_replica_completion(
                run_dir,
                {"completion_contract": contract},
                evaluation,
                report_available=True,
            )

        self.assertEqual("not_reproduced_on_this_path", assessment["status"])
        implementation = next(
            check
            for check in assessment["checks"]
            if check["id"] == "implementation"
        )
        self.assertFalse(implementation["pass"])

    def test_implementation_must_match_evaluated_generated_source(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            evaluation = _write_run(run_dir, include_novel=True)
            contract = _completion_contract(run_dir)
            _write_completion_report(run_dir, contract)
            (run_dir / "implementation" / "replica.py").write_text(
                "def replicate(runtime_input):\n    return 'different'\n",
                encoding="utf-8",
            )

            assessment = assess_replica_completion(
                run_dir,
                {"completion_contract": contract},
                evaluation,
                report_available=True,
            )

        self.assertEqual("not_reproduced_on_this_path", assessment["status"])

    def test_scenario_must_match_the_generated_component_language(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            evaluation = _write_run(run_dir, include_novel=True)
            contract = _completion_contract(run_dir)
            contract["implementation_scenario"] = "commercial-api"
            _write_completion_report(run_dir, contract)

            assessment = assess_replica_completion(
                run_dir,
                {"completion_contract": contract},
                evaluation,
                report_available=True,
            )

        self.assertEqual("partially_reproduced", assessment["status"])
        scenario = next(
            check
            for check in assessment["checks"]
            if check["id"] == "implementation_scenario"
        )
        self.assertFalse(scenario["pass"])

    def test_replaced_component_must_not_reuse_an_old_evaluation_plan(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            evaluation = _write_run(run_dir, include_novel=True)
            contract = _completion_contract(run_dir)
            _write_completion_report(run_dir, contract)
            record_path = run_dir / "generated-component.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            replacement = (
                "def replicate(runtime_input):\n    return 'replacement'\n"
            )
            record["component"]["source"] = replacement
            record["component_sha256"] = hashlib.sha256(
                json.dumps(
                    record["component"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode()
            ).hexdigest()
            record_path.write_text(json.dumps(record), encoding="utf-8")
            (run_dir / "generated-component.py").write_text(
                replacement,
                encoding="utf-8",
            )
            (run_dir / "implementation" / "replica.py").write_text(
                replacement,
                encoding="utf-8",
            )

            assessment = assess_replica_completion(
                run_dir,
                {"completion_contract": contract},
                evaluation,
                report_available=True,
            )

        self.assertEqual("not_reproduced_on_this_path", assessment["status"])

    def test_manifest_requires_the_supported_reexecution_command(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            evaluation = _write_run(run_dir, include_novel=True)
            contract = _completion_contract(run_dir)
            _write_completion_report(run_dir, contract)
            manifest_path = run_dir / "implementation" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["command"] = "not-a-command"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            assessment = assess_replica_completion(
                run_dir,
                {"completion_contract": contract},
                evaluation,
                report_available=True,
            )

        self.assertEqual("not_reproduced_on_this_path", assessment["status"])


class BundleCompletionTest(unittest.TestCase):
    def _assess(self, *, passed=6, status="PASSED", dependencies=(), coverage=None, has_outputs=True):
        from replica_mvp.completion import assess_bundle_execution
        plan = {"gaps": [], "prepared_before_implementation": True,
                "workflow_coverage": coverage or {"scope": "whole_workflow", "excluded_steps": [], "external_dependencies": []}}
        evaluation = {"status": status, "passed": passed, "total": 6, "source_unchanged": True,
                      "dependencies": list(dependencies), "failure_category": None if status == "PASSED" else "implementation_defect",
                      "candidate_sha256": "a" * 64, "plan_sha256": "b" * 64}
        return assess_bundle_execution(plan, evaluation, {"status": "PASSED"}, has_outputs=has_outputs,
                                       public_example_passed=True, public_assets_available=True)

    def test_complete_evidence_reproduces(self):
        self.assertEqual("reproduced", self._assess()["reproduction_status"])

    def test_outputs_without_a_passing_case_are_not_partial_reproduction(self):
        self.assertEqual("not_reproduced_on_this_path",
                         self._assess(passed=0, status="FAILED")["reproduction_status"])
        self.assertEqual("partially_reproduced", self._assess(passed=1, status="FAILED")["reproduction_status"])

    def test_unobserved_dependency_versions_prevent_full_reproduction(self):
        assessment = self._assess(dependencies=[{"name": "haystack-ai", "status": "unverified"}])
        self.assertEqual("partially_reproduced", assessment["reproduction_status"])
        self.assertIn("Declared dependency versions could not be observed: haystack-ai.", assessment["missing_conditions"])

    def test_excluded_workflow_steps_cap_the_result_at_partial(self):
        coverage = {"scope": "partial_workflow", "external_dependencies": [], "excluded_steps": [
            {"claim_id": "claim-003", "step_index": 1, "step": "present the first question", "reason": "caller supplies it"},
        ]}
        assessment = self._assess(coverage=coverage)
        self.assertEqual("partially_reproduced", assessment["reproduction_status"])
        self.assertIn("claim-003#1 present the first question", assessment["missing_conditions"][0])


if __name__ == "__main__":
    unittest.main()
