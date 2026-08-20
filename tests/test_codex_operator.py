import hashlib
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from replica_mvp import (
    finalize_codex_operator,
    prepare_codex_operator,
    run_built_replica,
)


REPOSITORY_ROOT = Path(__file__).parents[1]
STATIC_SITE_EXAMPLE = (
    REPOSITORY_ROOT / "examples" / "second-pass-static-site.json"
)


def _static_site_operator(request):
    source = (
        "def escape(value):\n"
        "    return str(value).replace('&', '&amp;').replace('<', '&lt;')"
        ".replace('>', '&gt;').replace('\"', '&quot;')"
        ".replace(\"'\", '&#x27;')\n"
        "\n"
        "def replicate(runtime_input):\n"
        "    required = ['title', 'headline', 'description', 'cta_text', "
        "'cta_href']\n"
        "    missing = [key for key in required if key not in runtime_input]\n"
        "    if missing:\n"
        "        return 'INSUFFICIENT_INFORMATION: missing ' + "
        "', '.join(missing)\n"
        "    return '<!doctype html><html><head><title>' + "
        "escape(runtime_input['title']) + '</title></head><body><h1>' + "
        "escape(runtime_input['headline']) + '</h1><p>' + "
        "escape(runtime_input['description']) + '</p><a href=\"' + "
        "escape(runtime_input['cta_href']) + '\">' + "
        "escape(runtime_input['cta_text']) + '</a></body></html>'\n"
    )
    return {
        "schema_version": "replica-component-generation/v1",
        "generator_identity": "codex-skill/build-replica-operator/v1",
        "component": {
            "schema_version": "replica-generated-component/v1",
            "language": "replica-python/v1",
            "input_contract": request["input_contract"],
            "output_contract": request["output_contract"],
            "source": source,
        },
    }


def _write_json(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


class CodexOperatorWorkflowTest(unittest.TestCase):
    def test_completion_standard_contract_publishes_a_reproduced_result(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "second-pass.json"
            second_pass = json.loads(
                STATIC_SITE_EXAMPLE.read_text(encoding="utf-8")
            )
            second_pass["completion_contract"] = {
                "dependency_level": "oss_only",
                "dependencies": ["Python standard library"],
                "public_sources": [
                    {
                        "url": "https://example.com/product",
                        "finding": "A public feature generates a landing page.",
                    }
                ],
                "input_assets": [
                    {
                        "id": "frozen-json-inputs",
                        "kind": "synthetic_json",
                        "location": "tests.json",
                    }
                ],
                "implementation_scenario": "oss-generated-python",
            }
            second_pass["tests"]["cases"].append(
                {
                    "id": "novel",
                    "kind": "novel",
                    "input": {
                        "title": "Novel Company",
                        "headline": "Ship a novel workflow",
                        "description": "A separately frozen input.",
                        "cta_text": "Explore",
                        "cta_href": "/novel",
                    },
                    "deterministic_assertions": [
                        {"type": "contains", "value": "Ship a novel workflow"}
                    ],
                    "criterion_ids": ["criterion-content"],
                    "semantic_criteria": [],
                }
            )
            frozen_tests_bytes = (
                json.dumps(
                    second_pass["tests"],
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                )
                + "\n"
            ).encode()
            input_asset = second_pass["completion_contract"]["input_assets"][0]
            input_asset.update(
                {
                    "kind": "structured_json",
                    "visibility": "evaluation_vault",
                    "sha256": hashlib.sha256(frozen_tests_bytes).hexdigest(),
                    "case_ids": [
                        case["id"] for case in second_pass["tests"]["cases"]
                    ],
                }
            )
            _write_json(source, second_pass)
            workspace = root / "workspace"
            evaluator_vault = root / "evaluator-vault"

            prepared = prepare_codex_operator(source, workspace, evaluator_vault)
            request = json.loads(
                Path(prepared["request_path"]).read_text(encoding="utf-8")
            )
            self.assertIn(
                '"dependency_level":"oss_only"',
                request["implementation_instructions"],
            )
            _write_json(
                Path(prepared["operator_path"]),
                _static_site_operator(request),
            )
            result = finalize_codex_operator(
                Path(prepared["task_dir"]),
                workspace,
                evaluator_vault,
                include_report=True,
            )

            public_result = json.loads(
                (Path(result["run_dir"]) / "replica-result.json").read_text(
                    encoding="utf-8"
                )
            )
            completion = json.loads(
                (
                    Path(result["run_dir"]) / "completion-assessment.json"
                ).read_text(encoding="utf-8")
            )
            report_markdown = (
                Path(result["run_dir"]) / "report.md"
            ).read_text(encoding="utf-8")
            implementation_manifest = json.loads(
                (
                    Path(result["run_dir"])
                    / "implementation"
                    / "manifest.json"
                ).read_text(encoding="utf-8")
            )
            private_tests_path = next(
                (evaluator_vault / "runs").rglob("tests.json")
            )
            private_run_dir = private_tests_path.parent
            private_completion_report = json.loads(
                (private_run_dir / "completion-report.json").read_text(
                    encoding="utf-8"
                )
            )
            private_report_markdown = (
                private_run_dir / "report.md"
            ).read_text(encoding="utf-8")
            self.assertEqual(
                input_asset["sha256"],
                hashlib.sha256(private_tests_path.read_bytes()).hexdigest(),
            )
            self.assertFalse(
                (Path(result["run_dir"]) / "completion-report.json").exists()
            )

        self.assertEqual(
            "reproduced",
            public_result["reproduction_status"],
            completion,
        )
        self.assertEqual("reproduced", completion["status"])
        self.assertEqual(4, result["evaluation"]["passed"])
        public_input_asset = public_result["completion_contract"][
            "input_assets"
        ][0]
        self.assertNotIn("case_ids", public_input_asset)
        self.assertEqual(input_asset["sha256"], public_input_asset["sha256"])
        self.assertEqual(
            {"normal", "boundary", "insufficient_information", "novel"},
            {case["kind"] for case in private_completion_report["cases"]},
        )
        self.assertTrue(
            all(case["pass"] for case in private_completion_report["cases"])
        )
        self.assertIn(
            "## Replica completion evidence",
            private_report_markdown,
        )
        self.assertIn("재현 판정: reproduced", report_markdown)
        self.assertIn("의존성 수준: oss_only", report_markdown)
        self.assertIn("https://example.com/product", report_markdown)
        self.assertIn(
            "structured_json: evaluation_vault:tests.json",
            report_markdown,
        )
        self.assertIn("oss-generated-python", report_markdown)
        self.assertIn("novel_input: PASS", report_markdown)
        self.assertIn("customer_output: PASS", report_markdown)
        self.assertEqual(
            "replica-mvp run-replica RUN_DIR < INPUT.json",
            implementation_manifest["command"],
        )
        self.assertEqual("replica.py", implementation_manifest["entrypoint"])

    def test_codex_prepares_and_builds_an_operator_without_catalog_selection(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            evaluator_vault = Path(tmp) / "evaluator-vault"
            prepared = prepare_codex_operator(
                STATIC_SITE_EXAMPLE,
                workspace,
                evaluator_vault,
            )

            request_path = Path(prepared["request_path"])
            operator_path = Path(prepared["operator_path"])
            request = json.loads(request_path.read_text(encoding="utf-8"))

            self.assertEqual("AWAITING_CODEX_OPERATOR", prepared["status"])
            self.assertEqual(1, prepared["attempt"])
            self.assertFalse(operator_path.exists())
            self.assertNotIn("tests", request)
            self.assertNotIn("expected", json.dumps(request))
            self.assertFalse((workspace / "intakes").exists())
            self.assertTrue(
                any((evaluator_vault / "intakes").rglob("source.json"))
            )
            self.assertIn(
                '"operation":"render_static_site"',
                request["implementation_instructions"],
            )

            _write_json(operator_path, _static_site_operator(request))
            result = finalize_codex_operator(
                Path(prepared["task_dir"]),
                workspace,
                evaluator_vault,
                include_report=True,
            )

            run_dir = Path(result["run_dir"])
            public_result = json.loads(
                (run_dir / "replica-result.json").read_text(encoding="utf-8")
            )
            completion = json.loads(
                (run_dir / "completion-assessment.json").read_text(
                    encoding="utf-8"
                )
            )
            selection = json.loads(
                (run_dir / "operation-selection.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("BUILT_AND_PASSED", result["status"])
            self.assertEqual(
                "partially_reproduced",
                public_result["reproduction_status"],
            )
            self.assertEqual("partially_reproduced", completion["status"])
            self.assertEqual(3, result["evaluation"]["passed"])
            self.assertTrue(Path(result["report_path"]).is_file())
            self.assertTrue((run_dir / "report.json").is_file())
            self.assertNotIn(
                str(evaluator_vault.resolve()),
                json.dumps(result),
            )
            self.assertEqual(
                "codex-operator-builder/v1",
                selection["selector_identity"],
            )
            self.assertEqual(
                "generated_component",
                selection["selected"]["strategy"],
            )
            self.assertEqual(
                "replica-python/v1",
                json.loads(
                    (run_dir / "generated-component.json").read_text(
                        encoding="utf-8"
                    )
                )["component"]["language"],
            )
            self.assertIn(
                "&lt;Fast &amp; Safe&gt;",
                run_built_replica(
                    run_dir,
                    {
                        "title": "Demo",
                        "headline": "<Fast & Safe>",
                        "description": "Description",
                        "cta_text": "Start",
                        "cta_href": "/start",
                    },
                ),
            )
            hidden_names = {
                "second-pass.json",
                "tests.json",
                "test-suite-lock.json",
                "replica_outputs.jsonl",
                "results.jsonl",
            }
            self.assertFalse(
                hidden_names.intersection(
                    path.name for path in workspace.rglob("*")
                )
            )
            self.assertTrue(
                hidden_names.issubset(
                    path.name for path in evaluator_vault.rglob("*")
                )
            )

    def test_codex_repairs_from_sanitized_status_without_frozen_tests(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            evaluator_vault = Path(tmp) / "evaluator-vault"
            prepared = prepare_codex_operator(
                STATIC_SITE_EXAMPLE,
                workspace,
                evaluator_vault,
            )
            task_dir = Path(prepared["task_dir"])
            request_path = Path(prepared["request_path"])
            operator_path = Path(prepared["operator_path"])
            request = json.loads(request_path.read_text(encoding="utf-8"))
            invalid = _static_site_operator(request)
            invalid["component"]["source"] = "def replicate(\n"
            _write_json(operator_path, invalid)

            failed = finalize_codex_operator(
                task_dir,
                workspace,
                evaluator_vault,
            )

            self.assertEqual("VALIDATION_FAILED", failed["status"])
            self.assertTrue(failed["retryable"])
            self.assertEqual(1, failed["attempt"])
            self.assertNotIn("error", failed)
            repaired_request = json.loads(
                request_path.read_text(encoding="utf-8")
            )
            self.assertEqual(2, repaired_request["attempt_context"]["attempt"])
            self.assertEqual(
                "VALIDATION_FAILED",
                repaired_request["attempt_context"]["previous_attempt"][
                    "status"
                ],
            )
            self.assertNotIn("tests", repaired_request)
            self.assertNotIn("expected", json.dumps(repaired_request))

            _write_json(
                operator_path,
                _static_site_operator(repaired_request),
            )
            passed = finalize_codex_operator(
                task_dir,
                workspace,
                evaluator_vault,
            )

            self.assertEqual("BUILT_AND_PASSED", passed["status"])
            self.assertEqual(2, passed["attempt"])
            attempts = json.loads(
                (
                    Path(passed["run_dir"]) / "generation-attempts.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(
                ["VALIDATION_FAILED", "PASSED"],
                [attempt["status"] for attempt in attempts["attempts"]],
            )

    def test_codex_receives_only_counts_after_fixed_evaluation_failure(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            evaluator_vault = Path(tmp) / "evaluator-vault"
            prepared = prepare_codex_operator(
                STATIC_SITE_EXAMPLE,
                workspace,
                evaluator_vault,
            )
            task_dir = Path(prepared["task_dir"])
            request_path = Path(prepared["request_path"])
            operator_path = Path(prepared["operator_path"])
            request = json.loads(request_path.read_text(encoding="utf-8"))
            wrong = _static_site_operator(request)
            wrong["component"]["source"] = (
                "def replicate(runtime_input):\n"
                "    return 'contract-valid but behaviorally wrong'\n"
            )
            _write_json(operator_path, wrong)

            failed = finalize_codex_operator(
                task_dir,
                workspace,
                evaluator_vault,
            )

            self.assertEqual("EVALUATION_FAILED", failed["status"])
            self.assertTrue(failed["retryable"])
            self.assertEqual(
                {"status": "FAILED", "passed": 0, "total": 3},
                failed["evaluation"],
            )
            self.assertNotIn("run_dir", failed)
            self.assertNotIn("expected", json.dumps(failed))
            self.assertFalse(
                any((workspace / "runs").rglob("replica.json"))
            )
            repaired_request = json.loads(
                request_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                {
                    "language": "replica-python/v1",
                    "status": "EVALUATION_FAILED",
                    "passed": 0,
                    "total": 3,
                },
                repaired_request["attempt_context"]["previous_attempt"],
            )

    def test_evaluator_vault_must_be_physically_separate(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"

            with self.assertRaisesRegex(
                ValueError,
                "physically separate",
            ):
                prepare_codex_operator(
                    STATIC_SITE_EXAMPLE,
                    workspace,
                    workspace / "private-tests",
                )

    def test_source_must_be_outside_the_public_workspace(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            source = workspace / "arrived-second-pass.json"
            source.write_bytes(STATIC_SITE_EXAMPLE.read_bytes())

            with self.assertRaisesRegex(
                ValueError,
                "source must be outside",
            ):
                prepare_codex_operator(
                    source,
                    workspace,
                    Path(tmp) / "evaluator-vault",
                )

    def test_failed_operator_has_three_total_attempts(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            evaluator_vault = Path(tmp) / "evaluator-vault"
            prepared = prepare_codex_operator(
                STATIC_SITE_EXAMPLE,
                workspace,
                evaluator_vault,
            )
            results = []
            for _ in range(3):
                request = json.loads(
                    Path(prepared["request_path"]).read_text(encoding="utf-8")
                )
                wrong = _static_site_operator(request)
                wrong["component"]["source"] = (
                    "def replicate(runtime_input):\n"
                    "    return 'wrong'\n"
                )
                _write_json(Path(prepared["operator_path"]), wrong)
                results.append(
                    finalize_codex_operator(
                        Path(prepared["task_dir"]),
                        workspace,
                        evaluator_vault,
                    )
                )

            self.assertEqual([1, 2, 3], [result["attempt"] for result in results])
            self.assertEqual([True, True, False], [
                result["retryable"] for result in results
            ])
            with self.assertRaisesRegex(ValueError, "already failed"):
                finalize_codex_operator(
                    Path(prepared["task_dir"]),
                    workspace,
                    evaluator_vault,
                )

    def test_workspace_source_symlink_is_also_rejected(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            source = workspace / "arrived-second-pass.json"
            try:
                source.symlink_to(STATIC_SITE_EXAMPLE)
            except OSError as error:
                if os.environ.get("REPLICA_REQUIRE_SYMLINK_TEST") == "1":
                    self.fail(f"file symlink security test is required: {error}")
                self.skipTest(f"file symlinks unavailable: {error}")

            with self.assertRaisesRegex(ValueError, "source must be outside"):
                prepare_codex_operator(
                    source,
                    workspace,
                    Path(tmp) / "evaluator-vault",
                )


if __name__ == "__main__":
    unittest.main()
