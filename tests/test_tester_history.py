"""Tester prompt savings must not discard inputs or alter evaluation evidence."""
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from replica_mvp.web_demo import _judge_prompt, _tester_prompt, run_web_demo
from tests.test_web_demo import HAS_PLAYWRIGHT, _passing_judge, _plan, _scripted_tester, _write_cli


class TesterHistoryTest(unittest.TestCase):
    def setUp(self):
        self.long_value = "입력한 값과 줄바꿈을 보존한다.\n" * 300 + "마지막 표식 🧪"
        self.reason = "The field is visible; enter the supplied facts before the next step. " * 12
        self.case = {"goal": "입력 결과 확인", "steps": ["입력 후 읽기"], "facts": [self.long_value]}
        self.element = {"tag": "textarea", "type": None, "label": "원문 입력 🧪"}
        self.page = {
            "url": "http://localhost/example", "text": "화면 내용\n" * 1000,
            "elements": [{**self.element, "ref": "e1", "value": self.long_value[:200],
                          "value_truncated": True, "checked": False}],
            "read_result": {"text": self.long_value[200:4200], "offset": 200, "more": True},
        }

    def event(self, index=1, **overrides):
        return {"index": index, "action": "fill", "element": self.element,
                "value": self.long_value, "reason": self.reason, "error": None, **overrides}

    def prompt(self, history):
        return _tester_prompt(self.case, ["uploads/音声.wav"], self.page, history, 7)

    def test_compaction_preserves_long_inputs_current_observation_and_recent_order(self):
        history = [self.event(index) for index in range(1, 22)]
        original = json.dumps([history, self.case, self.page], ensure_ascii=False)
        prompt = self.prompt(history)
        request = json.loads(prompt)
        recent = request["previous_actions"]
        self.assertEqual(list(range(7, 22)), [e["index"] for e in recent])
        for entry in recent:
            self.assertEqual(self.long_value, entry["value"])
            self.assertEqual(self.element, entry["element"])
            self.assertEqual("fill", entry["action"])
            self.assertNotIn("error", entry)
            self.assertTrue(entry["reason"].endswith("…[truncated]"))
            self.assertTrue(self.reason.startswith(entry["reason"].removesuffix("…[truncated]")))
            self.assertLess(len(entry["reason"]), len(self.reason))
        self.assertEqual(self.case, request["case"])
        self.assertEqual(self.page, request["page"])
        self.assertEqual(["uploads/音声.wav"], request["upload_files"])
        self.assertEqual(7, request["remaining_actions"])
        self.assertEqual(original, json.dumps([history, self.case, self.page], ensure_ascii=False))
        before = {**request, "previous_actions": history[-15:]}
        self.assertLess(len(prompt.encode()), len(json.dumps(before, ensure_ascii=False).encode()))

    def test_failure_and_terminal_reasons_are_retained_in_full(self):
        error = "Locator failed: " + "詳細 " * 300
        history = [self.event(1, error=error), self.event(2, action="give_up"),
                   self.event(3, action="done")]
        recent = json.loads(self.prompt(history))["previous_actions"]
        self.assertEqual([self.reason] * 3, [e["reason"] for e in recent])
        self.assertEqual(error, recent[0]["error"])

    def test_empty_input_is_preserved_and_short_reasons_are_unchanged(self):
        history = [self.event(1, value="", reason="Clear this field."),
                   self.event(2, action="wait", element=None, value="0", reason="Wait."),
                   self.event(3, action="click", value=None, reason="x" * 160),
                   self.event(4, reason="x" * 161)]
        recent = json.loads(self.prompt(history))["previous_actions"]
        self.assertEqual("", recent[0]["value"])
        self.assertEqual("0", recent[1]["value"])
        self.assertNotIn("element", recent[1])
        self.assertNotIn("value", recent[2])
        self.assertEqual([e["reason"] for e in history[:3]], [e["reason"] for e in recent[:3]])
        self.assertLess(len(recent[3]["reason"]), len(history[3]["reason"]))
        self.assertEqual([], json.loads(self.prompt([]))["previous_actions"])

    def test_building_tester_prompt_does_not_change_record_or_judge_input(self):
        event = self.event(event_id="input-001", url_after=self.page["url"])
        record = {"events": [event], "observations": [{"event_id": "input-001", "page": self.page}],
                  "execution_status": "completed", "stop_reason": None,
                  "file_changes": [], "final_page": self.page}
        expectations = [{"id": "kept", "description": "원문이 보존된다"}]
        with TemporaryDirectory() as directory:
            original = json.dumps(record, ensure_ascii=False).encode()
            judge_before = _judge_prompt(self.case, expectations, record, Path(directory), []).encode()
            self.prompt(record["events"])
            self.assertEqual(original, json.dumps(record, ensure_ascii=False).encode())
            self.assertEqual(judge_before,
                             _judge_prompt(self.case, expectations, record, Path(directory), []).encode())
            judge = json.loads(judge_before)
            self.assertEqual(self.reason, judge["events"][0]["reason"])
            self.assertEqual(self.long_value, judge["events"][0]["value"])

    @unittest.skipUnless(HAS_PLAYWRIGHT, "Playwright optional dependency")
    def test_browser_logs_and_judge_retain_full_reasons_while_tester_gets_compact_history(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _write_cli(root / "real")
            plan = _plan(root)
            script = _scripted_tester([
                ("fill", "요청 내용", self.long_value), ("click", "등록", None),
                ("click", "승인", None), ("done", None, None),
            ])
            prompts, judged = [], []

            def tester(prompt):
                prompts.append(json.loads(prompt))
                action, receipt = script(prompt)
                action["reason"] = self.reason
                return action, receipt

            def judge(prompt):
                judged.append(json.loads(prompt))
                return _passing_judge(prompt)

            with patch.dict(os.environ, {"PATH": f"{root / 'real'}{os.pathsep}{os.environ['PATH']}"}):
                run_web_demo(plan, root / "result", tester=tester, judge=judge)
            events = [json.loads(line) for line in (root / "result/events.jsonl").read_text().splitlines()]
            self.assertEqual(4, len(events))
            self.assertEqual(self.long_value, events[0]["value"])
            self.assertEqual([self.reason] * 4, [e["reason"] for e in events])
            self.assertTrue(all((root / "result" / e["screenshot"]).is_file() for e in events))
            self.assertEqual(self.long_value, prompts[1]["previous_actions"][0]["value"])
            self.assertLess(len(prompts[1]["previous_actions"][0]["reason"]), len(self.reason))
            self.assertEqual(1, len(judged))
            self.assertEqual("completed", judged[0]["execution_status"])
            self.assertEqual([self.reason] * 4, [e["reason"] for e in judged[0]["events"]])
            self.assertEqual(self.long_value, judged[0]["events"][0]["value"])
