import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from replica_mvp import evaluate_frozen_suite, freeze_test_suite


def _suite():
    return {
        "schema_version": "replica-tests/v1",
        "cases": [
            {
                "id": "normal",
                "kind": "normal",
                "input": "revenue grew 20%",
                "deterministic_assertions": [
                    {"type": "contains", "value": "20%"},
                ],
                "semantic_criteria": ["explain the observed growth"],
                "reference": {"observed_growth": "20%"},
            },
            {
                "id": "boundary",
                "kind": "boundary",
                "input": "revenue grew 0%",
                "deterministic_assertions": [
                    {"type": "contains", "value": "0%"},
                ],
                "semantic_criteria": [],
            },
            {
                "id": "insufficient",
                "kind": "insufficient_information",
                "input": "revenue changed",
                "deterministic_assertions": [],
                "semantic_criteria": ["identify missing evidence"],
            },
        ],
    }


class FrozenEvaluationTest(unittest.TestCase):
    def test_freezes_the_exact_test_suite_with_a_digest(self):
        suite = _suite()

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source-tests.json"
            source_bytes = (
                json.dumps(suite, ensure_ascii=False, indent=2) + "\n"
            ).encode()
            source.write_bytes(source_bytes)
            run_dir = root / "run"

            frozen = freeze_test_suite(source, run_dir)

            digest = hashlib.sha256(source_bytes).hexdigest()
            self.assertEqual("FROZEN", frozen["status"])
            self.assertEqual(digest, frozen["sha256"])
            self.assertEqual(3, frozen["case_count"])
            self.assertEqual(source_bytes, (run_dir / "tests.json").read_bytes())
            self.assertEqual(
                frozen,
                json.loads(
                    (run_dir / "test-suite-lock.json").read_text(encoding="utf-8")
                ),
            )

    def test_generates_every_output_before_judging(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source-tests.json"
            source.write_text(json.dumps(_suite()), encoding="utf-8")
            run_dir = root / "run"
            frozen = freeze_test_suite(source, run_dir)
            events = []

            def run_replica(case_input):
                events.append(("replica", case_input))
                return f"analysis: {case_input}"

            def judge(payload):
                outputs = (run_dir / "replica_outputs.jsonl").read_text(
                    encoding="utf-8"
                )
                self.assertEqual(3, len(outputs.splitlines()))
                if payload["case_id"] == "normal":
                    self.assertEqual(
                        {"observed_growth": "20%"},
                        payload["reference"],
                    )
                events.append(("judge", payload["case_id"]))
                return {"pass": True, "reason": "criterion is satisfied"}

            summary = evaluate_frozen_suite(
                run_dir,
                expected_test_sha256=frozen["sha256"],
                run_replica=run_replica,
                semantic_judge=judge,
                judge_identity="independent-judge-v1",
                judge_mode="independent",
            )

            self.assertEqual(
                [
                    "replica",
                    "replica",
                    "replica",
                    "replica",
                    "replica",
                    "replica",
                    "judge",
                    "judge",
                ],
                [event[0] for event in events],
            )
            self.assertEqual("PASSED", summary["status"])
            self.assertEqual(3, summary["passed"])
            self.assertEqual(
                hashlib.sha256(
                    (run_dir / "replica_outputs.jsonl").read_bytes()
                ).hexdigest(),
                summary["outputs_sha256"],
            )
            self.assertEqual(
                hashlib.sha256((run_dir / "results.jsonl").read_bytes()).hexdigest(),
                summary["results_sha256"],
            )
            results = [
                json.loads(line)
                for line in (run_dir / "results.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual("independent", results[0]["semantic"]["judge_mode"])
            self.assertEqual(
                "NOT_REQUIRED",
                results[1]["semantic"]["status"],
            )

    def test_refuses_to_reuse_a_run_with_evaluation_artifacts(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source-tests.json"
            source.write_text(json.dumps(_suite()), encoding="utf-8")
            run_dir = root / "run"
            frozen = freeze_test_suite(source, run_dir)
            evaluate_frozen_suite(
                run_dir,
                expected_test_sha256=frozen["sha256"],
                run_replica=lambda value: f"analysis: {value}",
                semantic_judge=lambda _: {
                    "pass": True,
                    "reason": "criterion is satisfied",
                },
                judge_identity="independent-judge-v1",
                judge_mode="independent",
            )

            with self.assertRaisesRegex(ValueError, "already exist"):
                evaluate_frozen_suite(
                    run_dir,
                    expected_test_sha256=frozen["sha256"],
                    run_replica=lambda _: self.fail("Replica must not rerun"),
                    semantic_judge=lambda _: self.fail("Judge must not rerun"),
                    judge_identity="independent-judge-v1",
                    judge_mode="independent",
                )

            summary = json.loads(
                (run_dir / "evaluation-summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual("PASSED", summary["status"])

    def test_rejects_a_nonstandard_json_replica_output(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source-tests.json"
            source.write_text(json.dumps(_suite()), encoding="utf-8")
            run_dir = root / "run"
            frozen = freeze_test_suite(source, run_dir)

            with self.assertRaisesRegex(ValueError, "standard JSON"):
                evaluate_frozen_suite(
                    run_dir,
                    expected_test_sha256=frozen["sha256"],
                    run_replica=lambda _: float("nan"),
                    semantic_judge=lambda _: {
                        "pass": True,
                        "reason": "not reached",
                    },
                    judge_identity="independent-judge-v1",
                    judge_mode="independent",
                )

            self.assertFalse((run_dir / "replica_outputs.jsonl").exists())

    def test_rejects_a_replica_that_changes_its_answer_for_the_same_input(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source-tests.json"
            source.write_text(json.dumps(_suite()), encoding="utf-8")
            run_dir = root / "run"
            frozen = freeze_test_suite(source, run_dir)
            calls = 0

            def changing_replica(case_input):
                nonlocal calls
                calls += 1
                return {"input": case_input, "call": calls}

            with self.assertRaisesRegex(RuntimeError, "not deterministic"):
                evaluate_frozen_suite(
                    run_dir,
                    expected_test_sha256=frozen["sha256"],
                    run_replica=changing_replica,
                    semantic_judge=lambda _: self.fail("Judge must not run"),
                    judge_identity="independent-judge-v1",
                    judge_mode="independent",
                )

            self.assertFalse((run_dir / "replica_outputs.jsonl").exists())
            self.assertFalse((run_dir / "results.jsonl").exists())

    def test_equals_requires_the_same_json_type_and_value(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            suite = _suite()
            suite["cases"][0]["deterministic_assertions"] = [
                {"type": "equals", "value": True},
            ]
            suite["cases"][0]["semantic_criteria"] = []
            source = root / "source-tests.json"
            source.write_text(json.dumps(suite), encoding="utf-8")
            run_dir = root / "run"
            frozen = freeze_test_suite(source, run_dir)

            summary = evaluate_frozen_suite(
                run_dir,
                expected_test_sha256=frozen["sha256"],
                run_replica=lambda value: (
                    1 if value == "revenue grew 20%" else f"analysis: {value}"
                ),
                semantic_judge=lambda _: {
                    "pass": True,
                    "reason": "criterion is satisfied",
                },
                judge_identity="independent-judge-v1",
                judge_mode="independent",
            )

            self.assertEqual("FAILED", summary["status"])
            first_result = json.loads(
                (run_dir / "results.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()[0]
            )
            self.assertEqual(
                "FAILED",
                first_result["deterministic"]["status"],
            )

    def test_refuses_to_replace_an_already_frozen_suite(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first.json"
            first_bytes = json.dumps(_suite()).encode()
            first.write_bytes(first_bytes)
            run_dir = root / "run"
            freeze_test_suite(first, run_dir)

            changed_suite = _suite()
            changed_suite["cases"][0]["input"] = "changed after implementation"
            changed = root / "changed.json"
            changed.write_text(json.dumps(changed_suite), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "already frozen"):
                freeze_test_suite(changed, run_dir)

            self.assertEqual(first_bytes, (run_dir / "tests.json").read_bytes())

    def test_rejects_a_malformed_existing_lock(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source-tests.json"
            source.write_text(json.dumps(_suite()), encoding="utf-8")
            run_dir = root / "run"
            frozen = freeze_test_suite(source, run_dir)
            (run_dir / "test-suite-lock.json").write_text(
                json.dumps({"sha256": frozen["sha256"]}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "already frozen"):
                freeze_test_suite(source, run_dir)

    def test_rejects_a_frozen_suite_changed_before_evaluation(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source-tests.json"
            source.write_text(json.dumps(_suite()), encoding="utf-8")
            run_dir = root / "run"
            frozen = freeze_test_suite(source, run_dir)
            (run_dir / "tests.json").write_text("{}", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "trusted digest"):
                evaluate_frozen_suite(
                    run_dir,
                    expected_test_sha256=frozen["sha256"],
                    run_replica=lambda _: self.fail("Replica must not run"),
                    semantic_judge=lambda _: self.fail("Judge must not run"),
                    judge_identity="independent-judge-v1",
                    judge_mode="independent",
                )

    def test_rejects_tests_and_lock_changed_together(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source-tests.json"
            source.write_text(json.dumps(_suite()), encoding="utf-8")
            run_dir = root / "run"
            frozen = freeze_test_suite(source, run_dir)

            changed_suite = _suite()
            changed_suite["cases"][0]["input"] = "changed with lock"
            changed_bytes = json.dumps(changed_suite).encode()
            (run_dir / "tests.json").write_bytes(changed_bytes)
            lock_path = run_dir / "test-suite-lock.json"
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            lock["sha256"] = hashlib.sha256(changed_bytes).hexdigest()
            lock_path.write_text(json.dumps(lock), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "trusted digest"):
                evaluate_frozen_suite(
                    run_dir,
                    expected_test_sha256=frozen["sha256"],
                    run_replica=lambda _: self.fail("Replica must not run"),
                    semantic_judge=lambda _: self.fail("Judge must not run"),
                    judge_identity="independent-judge-v1",
                    judge_mode="independent",
                )

    def test_requires_normal_boundary_and_insufficient_information_cases(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "incomplete.json"
            incomplete = _suite()
            incomplete["cases"] = incomplete["cases"][:1]
            source.write_text(json.dumps(incomplete), encoding="utf-8")
            run_dir = root / "run"

            with self.assertRaisesRegex(ValueError, "required test kinds"):
                freeze_test_suite(source, run_dir)

            self.assertFalse(run_dir.exists())

    def test_rejects_duplicate_inputs_with_different_case_ids(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "duplicate-inputs.json"
            suite = _suite()
            suite["cases"][1]["input"] = suite["cases"][0]["input"]
            source.write_text(json.dumps(suite), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "inputs must be unique"):
                freeze_test_suite(source, root / "run")

            self.assertFalse((root / "run").exists())

    def test_rejects_an_unsupported_deterministic_assertion(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "unsupported.json"
            suite = _suite()
            suite["cases"][0]["deterministic_assertions"][0]["type"] = "shell"
            source.write_text(json.dumps(suite), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unsupported assertion"):
                freeze_test_suite(source, root / "run")

    def test_rejects_an_unknown_judge_mode_before_running(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source-tests.json"
            source.write_text(json.dumps(_suite()), encoding="utf-8")
            run_dir = root / "run"
            frozen = freeze_test_suite(source, run_dir)

            with self.assertRaisesRegex(ValueError, "judge_mode"):
                evaluate_frozen_suite(
                    run_dir,
                    expected_test_sha256=frozen["sha256"],
                    run_replica=lambda _: self.fail("Replica must not run"),
                    semantic_judge=lambda _: self.fail("Judge must not run"),
                    judge_identity="unknown",
                    judge_mode="maybe-independent",
                )

    def test_rejects_an_invalid_semantic_judge_result(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source-tests.json"
            source.write_text(json.dumps(_suite()), encoding="utf-8")
            run_dir = root / "run"
            frozen = freeze_test_suite(source, run_dir)

            with self.assertRaisesRegex(RuntimeError, "semantic judge"):
                evaluate_frozen_suite(
                    run_dir,
                    expected_test_sha256=frozen["sha256"],
                    run_replica=lambda value: f"analysis: {value}",
                    semantic_judge=lambda _: {"pass": "yes"},
                    judge_identity="independent-judge-v1",
                    judge_mode="independent",
                )

            self.assertTrue((run_dir / "replica_outputs.jsonl").exists())
            self.assertFalse((run_dir / "results.jsonl").exists())

    def test_rejects_nonstandard_json_constants_before_freezing(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "nonstandard.json"
            suite = _suite()
            suite["cases"][0]["input"] = float("nan")
            source.write_text(json.dumps(suite), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "invalid test suite JSON"):
                freeze_test_suite(source, root / "run")


if __name__ == "__main__":
    unittest.main()
