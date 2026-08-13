import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from replica_mvp import write_final_report
from replica_mvp.reporting import _write_report_file_exclusive


def _build_record():
    return {
        "schema_version": "replica-build-record/v1",
        "source_intake_sha256": "a" * 64,
        "replica_id": "acme-landing-page",
        "company": "Acme",
        "capability": "generate a public landing page",
        "evidence_level": "public",
        "readiness": "ready",
        "buildability_status": "BUILDABLE",
        "build_status": "SUCCEEDED",
        "blockers": [],
        "supported_scope": ["static responsive landing page"],
        "unsupported_scope": ["private Acme templates"],
        "limitations": ["evaluated with synthetic company content"],
        "artifacts": {
            "replica": "replica.json",
            "tests": "tests.json",
            "test_lock": "test-suite-lock.json",
            "outputs": "replica_outputs.jsonl",
            "results": "results.jsonl",
            "evaluation_summary": "evaluation-summary.json",
        },
    }


def _write_passed_evaluation(run_dir):
    suite = {
        "schema_version": "replica-tests/v1",
        "cases": [
            {
                "id": "case-1",
                "kind": "normal",
                "input": {"prompt": "normal"},
                "deterministic_assertions": [],
                "semantic_criteria": [],
            },
            {
                "id": "case-2",
                "kind": "boundary",
                "input": {"prompt": "boundary"},
                "deterministic_assertions": [],
                "semantic_criteria": [],
            },
            {
                "id": "case-3",
                "kind": "insufficient_information",
                "input": {"prompt": "insufficient"},
                "deterministic_assertions": [],
                "semantic_criteria": ["identify missing information"],
            },
        ],
    }
    tests_bytes = (json.dumps(suite, sort_keys=True) + "\n").encode()
    (run_dir / "tests.json").write_bytes(tests_bytes)
    test_digest = hashlib.sha256(tests_bytes).hexdigest()
    (run_dir / "test-suite-lock.json").write_text(
        json.dumps(
            {
                "schema_version": "replica-test-lock/v1",
                "status": "FROZEN",
                "sha256": test_digest,
                "case_count": 3,
            }
        ),
        encoding="utf-8",
    )
    outputs = [
        {"case_id": f"case-{index}", "output": {"page": index}}
        for index in range(1, 4)
    ]
    output_bytes = (
        "".join(json.dumps(output) + "\n" for output in outputs)
    ).encode()
    (run_dir / "replica_outputs.jsonl").write_bytes(output_bytes)
    results = [
        {
            "case_id": f"case-{index}",
            "kind": kind,
            "deterministic": {"status": "NOT_REQUIRED", "checks": []},
            "semantic": (
                {
                    "status": "PASSED",
                    "reason": "missing information identified",
                    "judge_identity": "independent-judge-v1",
                    "judge_mode": "independent",
                }
                if index == 3
                else {
                    "status": "NOT_REQUIRED",
                    "judge_identity": "independent-judge-v1",
                    "judge_mode": "independent",
                }
            ),
            "pass": True,
        }
        for index, kind in enumerate(
            ("normal", "boundary", "insufficient_information"),
            start=1,
        )
    ]
    result_bytes = (
        "".join(json.dumps(result) + "\n" for result in results)
    ).encode()
    (run_dir / "results.jsonl").write_bytes(result_bytes)
    summary = {
        "schema_version": "replica-evaluation-summary/v1",
        "status": "PASSED",
        "passed": 3,
        "total": 3,
        "test_suite_sha256": test_digest,
        "outputs_sha256": hashlib.sha256(output_bytes).hexdigest(),
        "results_sha256": hashlib.sha256(result_bytes).hexdigest(),
        "judge_identity": "independent-judge-v1",
        "judge_mode": "independent",
    }
    (run_dir / "evaluation-summary.json").write_text(
        json.dumps(summary),
        encoding="utf-8",
    )
    (run_dir / "replica.json").write_text("{}\n", encoding="utf-8")


def _read_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _rewrite_results(run_dir, results):
    result_bytes = (
        "".join(json.dumps(result) + "\n" for result in results)
    ).encode()
    (run_dir / "results.jsonl").write_bytes(result_bytes)
    summary_path = run_dir / "evaluation-summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["results_sha256"] = hashlib.sha256(result_bytes).hexdigest()
    summary["passed"] = sum(result["pass"] for result in results)
    summary["total"] = len(results)
    summary["status"] = (
        "PASSED" if summary["passed"] == summary["total"] else "FAILED"
    )
    summary_path.write_text(json.dumps(summary), encoding="utf-8")


class FinalReportTest(unittest.TestCase):
    def test_reports_a_successful_evaluated_replica(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_passed_evaluation(run_dir)

            report = write_final_report(run_dir, _build_record())

            self.assertEqual("BUILT_AND_PASSED", report["status"])
            self.assertEqual("Acme", report["target"]["company"])
            self.assertEqual(3, report["evaluation"]["passed"])
            self.assertEqual(
                {"level": "public", "readiness": "ready"},
                report["evidence"],
            )
            self.assertEqual(
                "PUBLIC_SCOPE_REIMPLEMENTATION_ONLY",
                report["equivalence"],
            )
            self.assertEqual(
                report,
                json.loads((run_dir / "report.json").read_text(encoding="utf-8")),
            )
            markdown = (run_dir / "report.md").read_text(encoding="utf-8")
            self.assertIn("# Acme Replica 결과", markdown)
            self.assertIn("BUILT_AND_PASSED", markdown)
            self.assertIn("public / ready", markdown)
            self.assertIn("private Acme templates", markdown)
            self.assertIn("static responsive landing page", markdown)
            self.assertIn("replica.json", markdown)

    def test_reports_a_non_buildable_decision_without_evaluation(self):
        for status in (
            "INVALID_INPUT",
            "NOT_BUILDABLE",
            "PARTIALLY_BUILDABLE",
        ):
            with self.subTest(status=status), TemporaryDirectory() as tmp:
                record = _build_record()
                record["buildability_status"] = status
                record["build_status"] = "NOT_STARTED"
                record["blockers"] = ["REPLICA_NOT_ALLOWED"]
                record["artifacts"] = {}

                report = write_final_report(Path(tmp), record)

                self.assertEqual(status, report["status"])
                self.assertIsNone(report["evaluation"])
                self.assertEqual(
                    ["REPLICA_NOT_ALLOWED"],
                    report["build"]["blockers"],
                )

    def test_reports_a_failed_build_without_evaluation(self):
        with TemporaryDirectory() as tmp:
            record = _build_record()
            record["build_status"] = "FAILED"
            record["blockers"] = ["OPERATION_FAILED"]
            record["artifacts"] = {}

            report = write_final_report(Path(tmp), record)

            self.assertEqual("BUILD_FAILED", report["status"])
            self.assertIsNone(report["evaluation"])
            self.assertEqual(
                ["OPERATION_FAILED"],
                report["build"]["blockers"],
            )

    def test_reports_failed_cases_from_an_unsuccessful_evaluation(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_passed_evaluation(run_dir)
            summary_path = run_dir / "evaluation-summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            results = _read_jsonl(run_dir / "results.jsonl")
            results[2]["semantic"] = {
                "status": "FAILED",
                "reason": "mobile layout overflowed",
                "judge_identity": "independent-judge-v1",
                "judge_mode": "independent",
            }
            results[2]["pass"] = False
            _rewrite_results(run_dir, results)

            report = write_final_report(run_dir, _build_record())

            self.assertEqual("BUILT_WITH_FAILURES", report["status"])
            self.assertEqual(
                [
                    {
                        "case_id": "case-3",
                        "reason": "mobile layout overflowed",
                    }
                ],
                report["evaluation"]["failed_cases"],
            )
            markdown = (run_dir / "report.md").read_text(encoding="utf-8")
            self.assertIn("mobile layout overflowed", markdown)

    def test_rejects_an_evaluation_summary_inconsistent_with_results(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_passed_evaluation(run_dir)
            results = _read_jsonl(run_dir / "results.jsonl")
            results[2]["pass"] = False
            result_bytes = (
                "".join(json.dumps(result) + "\n" for result in results)
            ).encode()
            (run_dir / "results.jsonl").write_bytes(result_bytes)

            with self.assertRaisesRegex(ValueError, "inconsistent"):
                write_final_report(run_dir, _build_record())

            self.assertFalse((run_dir / "report.json").exists())
            self.assertFalse((run_dir / "report.md").exists())

    def test_rejects_an_invalid_judge_mode_in_the_evaluation_summary(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_passed_evaluation(run_dir)
            summary_path = run_dir / "evaluation-summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["judge_mode"] = "claimed-independent"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "inconsistent"):
                write_final_report(run_dir, _build_record())

    def test_rejects_a_nested_result_that_contradicts_its_pass_value(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_passed_evaluation(run_dir)
            results = _read_jsonl(run_dir / "results.jsonl")
            results[0]["semantic"]["status"] = "FAILED"
            results[0]["semantic"]["reason"] = "failed despite top-level pass"
            _rewrite_results(run_dir, results)

            with self.assertRaisesRegex(ValueError, "inconsistent"):
                write_final_report(run_dir, _build_record())

    def test_rejects_result_judge_metadata_that_differs_from_summary(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_passed_evaluation(run_dir)
            results = _read_jsonl(run_dir / "results.jsonl")
            results[0]["semantic"]["judge_mode"] = "same_session"
            _rewrite_results(run_dir, results)

            with self.assertRaisesRegex(ValueError, "inconsistent"):
                write_final_report(run_dir, _build_record())

    def test_rejects_tests_or_outputs_from_another_evaluation(self):
        for artifact in ("tests.json", "replica_outputs.jsonl"):
            with self.subTest(artifact=artifact), TemporaryDirectory() as tmp:
                run_dir = Path(tmp)
                _write_passed_evaluation(run_dir)
                path = run_dir / artifact
                path.write_bytes(path.read_bytes() + b" ")

                with self.assertRaisesRegex(ValueError, "digest|frozen"):
                    write_final_report(run_dir, _build_record())

    def test_rejects_a_non_object_evaluation_summary(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_passed_evaluation(run_dir)
            (run_dir / "evaluation-summary.json").write_text(
                '[["schema_version", "replica-evaluation-summary/v1"]]',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "evaluation summary"):
                write_final_report(run_dir, _build_record())

    def test_rejects_an_invalid_build_record_before_reading_evaluation(self):
        with TemporaryDirectory() as tmp:
            record = _build_record()
            record["buildability_status"] = "MAYBE"

            with self.assertRaisesRegex(ValueError, "invalid build record"):
                write_final_report(Path(tmp), record)

    def test_rejects_a_successful_build_that_was_not_ready(self):
        for readiness in ("partial", "blocked"):
            with self.subTest(readiness=readiness), TemporaryDirectory() as tmp:
                run_dir = Path(tmp)
                _write_passed_evaluation(run_dir)
                record = _build_record()
                record["readiness"] = readiness

                with self.assertRaisesRegex(ValueError, "invalid build record"):
                    write_final_report(run_dir, record)

    def test_rejects_an_artifact_path_outside_the_run_directory(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_passed_evaluation(run_dir)
            record = _build_record()
            record["artifacts"]["replica"] = "../outside.json"

            with self.assertRaisesRegex(ValueError, "artifact path"):
                write_final_report(run_dir, record)

            self.assertFalse((run_dir / "report.json").exists())

    def test_refuses_to_overwrite_a_final_report(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_passed_evaluation(run_dir)
            first = write_final_report(run_dir, _build_record())
            changed = _build_record()
            changed["limitations"] = ["changed after finalization"]

            with self.assertRaisesRegex(ValueError, "already exists"):
                write_final_report(run_dir, changed)

            self.assertEqual(
                first,
                json.loads((run_dir / "report.json").read_text(encoding="utf-8")),
            )

    def test_removes_a_partial_report_if_the_second_write_fails(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_passed_evaluation(run_dir)

            def fail_markdown(path, content):
                if path.name == "report.md":
                    raise OSError("simulated write failure")
                with path.open("x", encoding="utf-8") as stream:
                    stream.write(content)

            with patch(
                "replica_mvp.reporting._write_report_file_exclusive",
                side_effect=fail_markdown,
            ):
                with self.assertRaisesRegex(OSError, "simulated"):
                    write_final_report(run_dir, _build_record())

            self.assertFalse((run_dir / "report.json").exists())
            self.assertFalse((run_dir / "report.md").exists())

    def test_exclusive_writer_removes_a_file_after_an_internal_write_failure(self):
        with TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.json"

            class FailingStream:
                def __init__(self, path):
                    self.stream = open(path, "x", encoding="utf-8")

                def __enter__(self):
                    return self

                def __exit__(self, *_):
                    self.stream.close()

                def write(self, content):
                    self.stream.write(content[:1])
                    self.stream.flush()
                    raise OSError("simulated disk failure")

            with patch.object(
                Path,
                "open",
                autospec=True,
                side_effect=lambda path, *_, **__: FailingStream(path),
            ):
                with self.assertRaisesRegex(OSError, "disk"):
                    _write_report_file_exclusive(report_path, "{}\n")

            self.assertFalse(report_path.exists())


if __name__ == "__main__":
    unittest.main()
