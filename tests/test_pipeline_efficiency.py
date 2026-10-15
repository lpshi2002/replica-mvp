"""Regression coverage for repeated cost, interrupted evaluation and observation limits.

Uses local fixture apps and fake CLIs only; no paid model requests.
"""
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from replica_mvp.model_calls import (ModelUsageLimitError, install_meter, run_model_cli,
                                     summarize_receipts, trip_limit_gate, usage_limit_message)
from replica_mvp.web_demo import (_OBSERVE_SCRIPT, _perform, _wait_on_screen,
                                  _screen_evidence, run_web_demo, web_reproduction_status)
from replica_mvp.web_evaluation import (cumulative_web_costs, register_development_run, submission_count)
from replica_mvp.bundle_evaluation import evaluate_agent_bundle
from replica_mvp.single_agent import _development_seconds
from tests.test_web_demo import HAS_PLAYWRIGHT, _plan, _write_cli, _scripted_tester, _passing_judge
from tests.test_web_evaluation import APPROVE, _bind_web_app

# A standalone app (no company shell) opens directly on its own page, so no menu click.
STANDALONE_APPROVE = APPROVE[1:]
from tests import test_web_evaluation as web_fixtures


class LimitGateTest(unittest.TestCase):
    def test_cli_limit_in_stdout_stops_subsequent_real_calls(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            real = _write_cli(root / "real")
            counter = root / "invocations"
            real.write_text(f"#!{sys.executable}\nfrom pathlib import Path\nimport json\n"
                            f"p=Path({str(counter)!r}); p.write_text(p.read_text()+'x' if p.exists() else 'x')\n"
                            "print(json.dumps({'is_error':True,'result':\"You've hit your usage limit\"}))\n")
            gate = root / "gate.json"
            with patch.dict(os.environ, {"PATH": f"{real.parent}{os.pathsep}{os.environ['PATH']}"}):
                for phase in ("tester", "judge"):
                    with self.assertRaises(ModelUsageLimitError):
                        run_model_cli("claude", "test", {}, receipts=root / "receipts", phase=phase,
                                      timeout=5, gate=gate)
            self.assertEqual("x", counter.read_text())
            costs = summarize_receipts(root / "receipts")["phases"]
            self.assertEqual(1, costs["tester"]["usage_limited"])
            self.assertEqual((0, 1), (costs["judge"]["calls"], costs["judge"]["skipped"]))

    def test_runtime_wrapper_recognizes_zero_exit_limit_and_blocks_next_call(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            real = _write_cli(root / "real")
            real.write_text(f"#!{sys.executable}\nimport json\n"
                            "print(json.dumps({'type':'turn.failed','error':{'message':'usage limit reached'}}))\n")
            with patch.dict(os.environ, {"PATH": f"{real.parent}{os.pathsep}{os.environ['PATH']}"}):
                install_meter(root / "bin", root / "receipts", "replica_runtime", gate=root / "gate.json")
            first = subprocess.run([str(root / "bin/claude")], capture_output=True)
            self.assertEqual(0, first.returncode)  # Preserve the underlying CLI's transport contract.
            self.assertTrue((root / "gate.json").exists())
            second = subprocess.run([str(root / "bin/claude")], capture_output=True)
            self.assertNotEqual(0, second.returncode)
            phases = summarize_receipts(root / "receipts")["phases"]
            self.assertEqual((1, 1), (phases["replica_runtime"]["calls"], phases["replica_runtime"]["skipped"]))

    def test_limit_words_in_successful_model_content_are_not_a_limit(self):
        out = json.dumps({"is_error": False, "result": "Our app shows 'usage limit' in its help page."}).encode()
        self.assertIsNone(usage_limit_message(out))


@unittest.skipUnless(HAS_PLAYWRIGHT, "Playwright optional dependency")
class BrowserEfficiencyTest(unittest.TestCase):
    def test_long_input_checked_state_intermediate_evidence_and_local_wait(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as driver:
            browser = driver.chromium.launch()
            try:
                page = browser.new_page()
                page.set_content('<label for="t">내용</label><textarea id="t"></textarea>'
                                 '<label><input type="checkbox" checked>인용</label><p id="s">처리 중</p>')
                text = "긴 입력" * 120
                page.locator("textarea").fill(text)
                before = page.evaluate(_OBSERVE_SCRIPT)
                field, check = before["elements"]
                self.assertEqual((200, len(text), True), (len(field["value"]), field["value_length"], field["value_truncated"]))
                self.assertTrue(check["checked"])
                _perform(page, {"action": "check", "ref": check["ref"]}, {})
                self.assertTrue(page.locator('input').is_checked())
                read = _perform(page, {"action": "read", "ref": field["ref"], "value": "200"}, {})
                self.assertEqual(text[200:], read["text"])
                page.evaluate("setTimeout(() => document.querySelector('#s').textContent = '완료', 700)")
                waited = _wait_on_screen(page, {"action": "wait_for", "value": json.dumps(
                    {"text": "완료", "state": "present", "seconds": 3})}, time.monotonic() + 4, None)
                self.assertEqual("condition_met", waited["reason"])
                self.assertGreater(waited["polls"], 1)
                after = page.evaluate(_OBSERVE_SCRIPT)
                evidence = _screen_evidence({"observations": [{"event_id": "1", "page": before},
                                                               {"event_id": "2", "page": after}]})
                self.assertIn("처리 중", evidence[0]["page_changes"]["text"])
                self.assertIn("완료", evidence[1]["page_changes"]["text"])
                waited = _wait_on_screen(page, {"action": "wait", "value": "120"}, time.monotonic() + .05, None)
                self.assertLess(waited["seconds"], 1)
            finally:
                browser.close()

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        _write_cli(self.root / "real")
        env = patch.dict(os.environ, {"PATH": f"{self.root / 'real'}{os.pathsep}{os.environ['PATH']}"})
        env.start()
        self.addCleanup(env.stop)

    def two_case_plan(self, varied=False):
        path = _plan(self.root)
        plan = json.loads(path.read_text())
        if varied:
            plan["cases"][0]["variation"] = {"instruction": "다른 사무용품 이름으로 바꾼다"}
        plan["cases"].append({**plan["cases"][0], "id": "second"})
        path.write_text(json.dumps(plan))
        return path

    def test_resume_reuses_finished_case_and_already_drawn_values(self):
        path = self.two_case_plan(varied=True)
        chair = [(a, l, "의자 구매" if v else v) for a, l, v in STANDALONE_APPROVE]
        script = _scripted_tester(chair)
        count = 0
        def interrupted(prompt):
            nonlocal count
            count += 1
            if count > len(chair):
                trip_limit_gate(self.root / "first/usage-limit.json", {"message": "usage limit"})
                raise ModelUsageLimitError("usage limit")
            return script(prompt)
        generator = Mock(side_effect=web_fixtures.WebHarnessTest._chair)
        first = run_web_demo(path, self.root / "first", tester=interrupted,
                             judge=_passing_judge, instance_generator=generator)
        self.assertEqual(1, first["outcome"]["cases_completed"])
        self.assertTrue(first["interruption"])
        self.assertEqual(2, generator.call_count)
        before = (self.root / "first/checkpoint.json").read_bytes()
        generator.reset_mock()
        blocked = run_web_demo(path, self.root / "paused", resume_from=self.root / "first",
                               tester=_scripted_tester([]), judge=_passing_judge, instance_generator=generator)
        self.assertTrue(blocked["interruption"])
        self.assertEqual(1, blocked["outcome"]["cases_completed"])
        second = run_web_demo(path, self.root / "second", resume_from=self.root / "paused", clear_limit=True,
                              tester=_scripted_tester(chair), judge=_passing_judge, instance_generator=generator)
        self.assertEqual(2, second["outcome"]["cases_completed"])
        self.assertIsNone(second["interruption"])
        self.assertTrue(second["lineage"]["reused_evidence"])
        self.assertEqual(0, generator.call_count)
        self.assertEqual(first["cases"][1]["instance"], second["cases"][1]["instance"])
        self.assertEqual(before, (self.root / "first/checkpoint.json").read_bytes())

    def test_partial_selection_and_changed_evaluator_require_fresh_observations(self):
        path = self.two_case_plan()
        first = run_web_demo(path, self.root / "first", case_ids=["approve"],
                             tester=_scripted_tester(STANDALONE_APPROVE), judge=_passing_judge)
        self.assertFalse(first["complete_plan"])
        self.assertEqual("not_evaluated", web_reproduction_status(first))
        tester = Mock(wraps=_scripted_tester(STANDALONE_APPROVE))
        with patch("replica_mvp.web_demo.evaluator_version", return_value="new-observer"):
            second = run_web_demo(path, self.root / "second", case_ids=["approve"],
                                  resume_from=self.root / "first", tester=tester, judge=_passing_judge)
        self.assertFalse(second["lineage"]["reused_evidence"])
        self.assertEqual(len(STANDALONE_APPROVE), tester.call_count)
        evidence = self.root / "first/cases/approve/screens/000-start.png"
        evidence.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "resume evidence changed"):
            run_web_demo(path, self.root / "third", resume_from=self.root / "first")
        self.assertFalse((self.root / "third").exists())

    def test_role_models_are_routed_independently(self):
        path = _plan(self.root)
        tester = _scripted_tester(STANDALONE_APPROVE)
        def call(provider, prompt, schema, **kwargs):
            if kwargs["phase"] == "tester":
                return tester(prompt)
            return _passing_judge(prompt)
        with patch("replica_mvp.web_demo.run_model_cli", side_effect=call) as model:
            run_web_demo(path, self.root / "out", phase_models={"tester": "small", "judge": "large"})
        routed = {(c.kwargs["phase"], c.kwargs["model"]) for c in model.call_args_list}
        self.assertEqual({("tester", "small"), ("judge", "large")}, routed)

    def test_costs_include_registered_development_and_deduplicate_receipts(self):
        path = _plan(self.root)
        demo = self.root / "development"
        run_web_demo(path, demo, tester=_scripted_tester(STANDALONE_APPROVE), judge=_passing_judge)
        registry = _bind_web_app(self.root / "harness")
        registered = register_development_run(registry, "claim-001", demo)
        self.assertEqual(registered, register_development_run(registry, "claim-001", demo))
        claim = json.loads(registry.read_text())["claims"][0]
        # Importing the same receipt under two different provenance entries must not double it.
        claim["bundle_submissions"] = [{"public_run_dir": registered["path"], "result_sha256": registered["result_sha256"]}]
        costs = cumulative_web_costs(registry.parent, claim)
        self.assertEqual(1, costs["unique_calls"])
        self.assertEqual(.01, costs["phases"]["replica_runtime"]["cli_list_estimate_usd"])

    def test_old_evaluator_recovery_after_three_attempts_preserves_the_bundle(self):
        registry = _bind_web_app(self.root / "harness")
        def failing_judge(prompt):
            result, receipt = _passing_judge(prompt)
            for verdict in result["verdicts"]:
                verdict["status"] = "failed"
            return result, receipt
        value = evaluate_agent_bundle(registry, "claim-001", tester=_scripted_tester(APPROVE),
                                      judge=failing_judge, reviewer=web_fixtures._passing_review)
        claim = value["claims"][0]
        original = claim["bundle_submissions"][0]
        # Legacy runs counted every evaluation attempt against the three-submission cap.
        claim["bundle_submissions"] = [{**original, "attempt": n} for n in (1, 2, 3)]
        registry.write_text(json.dumps(value))
        previous = registry.parent / original["public_run_dir"] / "demo-result.json"
        before = previous.read_bytes()
        manifest = registry.parent / claim["implementation_result"]["candidate_path"]
        bundle_before = manifest.read_bytes()
        with patch("replica_mvp.web_evaluation.evaluator_version", return_value="corrected"), \
                patch("replica_mvp.web_demo.evaluator_version", return_value="corrected"):
            value = evaluate_agent_bundle(registry, "claim-001", recovery_reason="observer corrected",
                                          tester=_scripted_tester(APPROVE), judge=_passing_judge,
                                          reviewer=web_fixtures._passing_review)
        claim = value["claims"][0]
        self.assertEqual("RESULT_SUCCESS", claim["status"])
        self.assertEqual((4, 3), (len(claim["bundle_submissions"]), claim["bundle_submissions"][-1]["recovery_of"]))
        result = json.loads((registry.parent / claim["final_result"]["public_run_dir"] / "demo-result.json").read_text())
        self.assertFalse(result["lineage"]["reused_evidence"])
        self.assertEqual(before, previous.read_bytes())
        self.assertEqual(bundle_before, manifest.read_bytes())
        with self.assertRaisesRegex(ValueError, "not a successful result"):
            evaluate_agent_bundle(registry, "claim-001", recovery_reason="do not rerun a success")


class BudgetAccountingTest(unittest.TestCase):
    def test_evaluation_pause_does_not_consume_development_budget(self):
        claim = {"status": "RESULT_FAILED", "started_at": "2000-01-01T00:00:00+00:00",
                 "finished_at": "2000-01-01T00:01:00+00:00"}
        self.assertEqual(60, _development_seconds(claim))
        claim.update(status="IMPLEMENTING", development_elapsed_seconds=60,
                     development_active_since="2026-10-10T00:00:00+00:00")
        with patch("replica_mvp.single_agent.utc_now", return_value="2026-10-10T00:00:10+00:00"):
            self.assertEqual(70, _development_seconds(claim))

    def test_recovery_is_not_a_new_candidate_submission(self):
        claim = {"bundle_submissions": [
            {"candidate_sha256": "a", "status": "INTERRUPTED"},
            {"candidate_sha256": "a", "status": "COMPLETED", "recovery_of": 1},
            {"candidate_sha256": "a", "status": "COMPLETED", "recovery_of": 2},
            {"candidate_sha256": "b", "status": "COMPLETED"}]}
        self.assertEqual(2, submission_count(Path("/unused"), claim))
