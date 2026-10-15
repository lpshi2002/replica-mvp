"""A cost comparison must reuse inputs, not successful judgments or browser state."""
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from replica_mvp.web_demo import run_web_demo
from tests.test_web_demo import HAS_PLAYWRIGHT, _plan, _write_cli, _scripted_tester, _passing_judge
from tests import test_web_evaluation as web_fixtures


@unittest.skipUnless(HAS_PLAYWRIGHT, "Playwright optional dependency")
class ComparisonInputsTest(unittest.TestCase):
    def test_paired_run_reuses_drawn_values_but_executes_every_action_and_judgment(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_cli(root / "real")
            path = _plan(root)
            plan = json.loads(path.read_text())
            plan["cases"][0]["variation"] = {"instruction": "다른 사무용품 이름으로 바꾼다"}
            path.write_text(json.dumps(plan))
            script = [("fill", "요청 내용", "의자 구매"), ("click", "등록", None),
                      ("click", "승인", None), ("done", None, None)]
            with patch.dict(os.environ, {"PATH": f"{root / 'real'}{os.pathsep}{os.environ['PATH']}"}):
                first = run_web_demo(path, root / "first", tester=_scripted_tester(script),
                                     judge=_passing_judge, instance_generator=web_fixtures.WebHarnessTest._chair,
                                     tester_mode="single", cache_ttl="1h")
                tester, judge = Mock(side_effect=_scripted_tester(script)), Mock(side_effect=_passing_judge)
                generator = Mock(side_effect=AssertionError("comparison must not redraw inputs"))
                second = run_web_demo(path, root / "second", tester=tester, judge=judge,
                                      instance_generator=generator, input_cases_from=root / "first",
                                      tester_mode="plan", cache_ttl="5m")
            self.assertEqual(4, tester.call_count)
            self.assertEqual(1, judge.call_count)
            generator.assert_not_called()
            self.assertEqual(first["cases"][0]["instance"], second["cases"][0]["instance"])
            self.assertFalse(second["lineage"]["reused_evidence"])
            self.assertEqual("inputs_only", second["lineage"]["mode"])
            self.assertEqual("5m", second["model_configuration"]["cache_ttl"])
            self.assertEqual(4, second["cases"][0]["event_count"])
            for event in map(json.loads, (root / "second/events.jsonl").read_text().splitlines()):
                self.assertTrue((root / "second" / event["screenshot"]).is_file())

    def test_incomplete_input_source_rejected_before_new_model_or_browser(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = _plan(root)
            plan = json.loads(path.read_text()); plan["cases"][0]["variation"] = {"instruction": "vary"}
            path.write_text(json.dumps(plan))
            from replica_mvp.web_checkpoint import digest, write_checkpoint
            old = root / "old"; old.mkdir()
            write_checkpoint(old, {"plan_sha256": digest(path), "candidate_manifest_sha256": digest(root / "app/manifest.json"),
                                   "instances": {}, "cases": []})
            tester = Mock(side_effect=AssertionError("must not call"))
            with self.assertRaisesRegex(ValueError, "lacks drawn inputs"):
                run_web_demo(path, root / "out", tester=tester, input_cases_from=old)
            tester.assert_not_called()
