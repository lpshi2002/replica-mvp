import hashlib
import json
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from replica_mvp.web_demo import _instance_case, run_web_demo
from replica_mvp.web_inputs import InputVariationError, render_uploads, replacement_function, variation_sources
from tests.test_web_inputs import upload_plan, upload_tester
from tests.test_web_demo import _passing_judge


class UploadVariationTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def plan(self, name="sample.txt", content=b"Alice has 12 items"):
        path = upload_plan(self.root, name=name, content=content)
        plan = json.loads(path.read_text())
        case = plan["cases"][0]
        case["variation"] = {"instruction": "Change the person and count while preserving the task"}
        case["uploads"][0]["vary"] = True
        case["expectations"][0]["upload_relation"] = "literal"
        path.write_text(json.dumps(plan))
        return path, case

    @staticmethod
    def answer():
        return {"goal": "Ignore the actual task", "steps": [], "facts": ["Invented"],
                "replacements": [{"from": "Alice", "to": "Bob"}, {"from": "12", "to": "34"}]}

    def test_single_pass_rejects_duplicate_overlap_and_partial_values(self):
        swap = replacement_function([{"from": "Alice", "to": "Bob"}, {"from": "Bob", "to": "Carol"}])
        self.assertEqual("Bob and Carol", swap("Alice and Bob"))
        for replacements in ([{"from": "Alice", "to": "Bob"}, {"from": "Alice", "to": "Sue"}],
                             [{"from": "Alice", "to": "Bob"}, {"from": "Ali", "to": "Sue"}]):
            with self.assertRaisesRegex(InputVariationError, "overlapping"):
                replacement_function(replacements)
        for value in ("120", "x12", "12.5"):
            with self.assertRaisesRegex(InputVariationError, "partial"):
                replacement_function([{"from": "12", "to": "34"}])(value)

    def test_file_and_frozen_wording_use_the_same_substitutions(self):
        _, case = self.plan()
        instance = _instance_case(case, self.answer())
        self.assertEqual("Upload Bob's document", instance["goal"])
        self.assertEqual(case["steps"], instance["steps"])
        self.assertEqual(["Document is for Bob"], instance["facts"])
        self.assertEqual("Bob", instance["expectations"][0]["check"]["text"])
        self.assertEqual(b"Bob has 34 items", render_uploads(case, self.answer(), self.root)["sample.txt"])

    def test_csv_preserves_header_shape_and_numeric_types(self):
        _, case = self.plan("sample.csv", b"name,count\nAlice,12\n")
        self.assertEqual(b"name,count\r\nBob,34\r\n", render_uploads(case, self.answer(), self.root)["sample.csv"])
        answer = self.answer()
        answer["replacements"][1]["to"] = "many"
        with self.assertRaisesRegex(InputVariationError, "numeric"):
            render_uploads(case, answer, self.root)
        with self.assertRaisesRegex(InputVariationError, "headers"):
            render_uploads(case, {"replacements": [{"from": "name", "to": "person"}]}, self.root)

    def test_actual_browser_upload_and_comparison_use_the_varied_bytes(self):
        path, case = self.plan()
        observed = []
        def generator(prompt):
            observed.append(json.loads(prompt))
            return self.answer(), "generated-1"
        first = run_web_demo(path, self.root / "first", tester=upload_tester(), instance_generator=generator)
        self.assertEqual(1, first["outcome"]["passed"])
        self.assertEqual("Alice has 12 items", observed[0]["upload_inputs"][0]["content"])
        record = first["cases"][0]
        self.assertEqual("Bob has 34 items", record["input_files"][0]["content"])
        self.assertEqual(b"Bob has 34 items", (self.root / "first" / record["workspace"] / "result.txt").read_bytes())
        no_generator = Mock(side_effect=AssertionError("must not regenerate"))
        second = run_web_demo(path, self.root / "second", tester=upload_tester(), instance_generator=no_generator,
                              input_cases_from=self.root / "first", tester_mode="single")
        no_generator.assert_not_called()
        self.assertEqual(record["input_files"], second["cases"][0]["input_files"])

    def test_csv_upload_is_executed_through_the_user_interface(self):
        path, _ = self.plan("sample.csv", b"name,count\nAlice,12\n")
        result = run_web_demo(path, self.root / "out", tester=upload_tester("sample.csv"),
                              instance_generator=lambda _: (self.answer(), None))
        self.assertEqual(1, result["outcome"]["passed"])
        self.assertEqual("name,count\r\nBob,34\r\n", result["cases"][0]["input_files"][0]["content"])

    def test_derived_criterion_remains_unevaluated_and_judge_gets_real_input(self):
        path, _ = self.plan()
        plan = json.loads(path.read_text())
        original = deepcopy(plan["cases"][0]["expectations"][0])
        derived = {**original, "id": "total", "description": "The total is 24", "upload_relation": "derived",
                   "check": {"type": "file_contains", "path": "result.txt", "text": "24"}}
        semantic = {**original, "id": "visible"}
        semantic.pop("check")
        plan["cases"][0]["expectations"] += [derived, semantic]
        path.write_text(json.dumps(plan))
        prompts = []
        def judge(prompt):
            prompts.append(json.loads(prompt))
            return _passing_judge(prompt)
        result = run_web_demo(path, self.root / "out", tester=upload_tester(), judge=judge,
                              instance_generator=lambda _: (self.answer(), None))
        expectations = {e["id"]: e for e in result["cases"][0]["expectations"]}
        self.assertEqual("not_evaluated", expectations["total"]["status"])
        self.assertEqual("The total is 24", expectations["total"]["description"])
        self.assertEqual("Bob has 34 items", prompts[0]["input_files"][0]["content"])
        self.assertEqual(["visible"], [e["id"] for e in prompts[0]["expectations"]])

    def test_invalid_draw_is_not_run_or_redrawn_on_resume(self):
        path, _ = self.plan()
        bad = self.answer()
        bad["replacements"] = [{"from": "Nobody", "to": "Somebody"}]
        tester = Mock(side_effect=AssertionError("must not execute the original"))
        generator = Mock(return_value=(bad, None))
        first = run_web_demo(path, self.root / "first", tester=tester, instance_generator=generator)
        second = run_web_demo(path, self.root / "second", tester=tester, instance_generator=generator,
                              resume_from=self.root / "first")
        self.assertEqual(1, generator.call_count)
        tester.assert_not_called()
        self.assertEqual(0, first["outcome"]["passed"])
        self.assertEqual("blocked", second["cases"][0]["execution_status"])

    def test_interrupted_file_write_finishes_from_saved_parameters_without_redraw(self):
        path, _ = self.plan()
        first_dir = self.root / "first"
        generator = Mock(return_value=(self.answer(), "draw-1"))
        def crash(case, plan_dir, directory, info, **kwargs):
            checkpoint = json.loads((directory / "checkpoint.json").read_text())
            self.assertEqual("preparing", checkpoint["instances"][case["id"]]["input_state"])
            target = directory / f"cases/{case['id']}/inputs/sample.txt"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"partial")
            raise SystemExit("process ended during input write")
        with patch("replica_mvp.web_demo.seal_inputs", side_effect=crash), self.assertRaises(SystemExit):
            run_web_demo(path, first_dir, tester=upload_tester(), instance_generator=generator)
        second = run_web_demo(path, self.root / "second", resume_from=first_dir,
                              tester=upload_tester(), instance_generator=generator)
        self.assertEqual(1, generator.call_count)
        self.assertEqual("Bob has 34 items", second["cases"][0]["input_files"][0]["content"])
        self.assertEqual(b"partial", (first_dir / "cases/order/inputs/sample.txt").read_bytes())

    def test_provider_interruption_before_a_valid_draw_can_resume(self):
        path, _ = self.plan()
        generator = Mock(side_effect=[RuntimeError("provider interrupted"), (self.answer(), "draw-2")])
        first = run_web_demo(path, self.root / "first", tester=upload_tester(), instance_generator=generator)
        second = run_web_demo(path, self.root / "second", resume_from=self.root / "first",
                              tester=upload_tester(), instance_generator=generator)
        self.assertEqual(2, generator.call_count)
        self.assertEqual(first["cases"][0]["instance"]["seed"], second["cases"][0]["instance"]["seed"])
        self.assertEqual(2, second["cases"][0]["instance"]["generation_attempts"])

    def test_unchanged_and_fixed_attachment_conflicts_are_rejected(self):
        _, case = self.plan()
        with self.assertRaisesRegex(InputVariationError, "did not change"):
            render_uploads(case, {"replacements": [{"from": "Upload", "to": "Submit"}]}, self.root)
        (self.root / "fixed.txt").write_text("Policy for Alice")
        case["uploads"].append({"path": "fixed.txt", "sha256": hashlib.sha256(b"Policy for Alice").hexdigest()})
        with self.assertRaisesRegex(InputVariationError, "fixed upload"):
            render_uploads(case, self.answer(), self.root)

    def test_unsupported_variation_is_explicit_and_never_uses_the_original(self):
        path, _ = self.plan("sample.pdf", b"%PDF Alice 12")
        tester, generator = Mock(), Mock()
        result = run_web_demo(path, self.root / "out", tester=tester, instance_generator=generator)
        self.assertIn("UTF-8 TXT/CSV", result["cases"][0]["stop_reason"])
        tester.assert_not_called()
        generator.assert_not_called()

    def test_invalid_text_large_files_and_malformed_csv_are_rejected(self):
        for name, data in (("bad.txt", b"\xff"), ("huge.txt", b"x" * 20_001),
                           ("bad.csv", b"name,count\nAlice\n"), ("binary.txt", b"x\x00y")):
            (self.root / name).write_bytes(data)
            case = {"uploads": [{"path": name, "sha256": hashlib.sha256(data).hexdigest(), "vary": True}]}
            with self.assertRaises(InputVariationError):
                variation_sources(case, self.root)
