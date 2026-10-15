import hashlib
import importlib.util
import json
import sys
import time
import unittest
from unittest import mock
from pathlib import Path
from tempfile import TemporaryDirectory

from replica_mvp.web_actions import read_plan
from replica_mvp import web_demo
from replica_mvp.web_demo import run_web_demo


HAS_PLAYWRIGHT = importlib.util.find_spec("playwright") is not None

# One form page per test. POST /submit stores the form in outbox/ and redirects to a result page.
APP = r'''
import argparse, json, os, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, required=True)
ARGS = parser.parse_args()
PAGE = %r
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def reply(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())
    def do_GET(self):
        self.reply("<html><body><h1>접수 완료</h1></body></html>" if self.path == "/done" else PAGE)
    def do_POST(self):
        form = urllib.parse.parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode(),
                                     keep_blank_values=True)
        os.makedirs("outbox", exist_ok=True)
        number = len(os.listdir("outbox")) + 1
        json.dump({k: v[0] for k, v in form.items()}, open(f"outbox/submission-{number}.json", "w"),
                  ensure_ascii=False)
        self.send_response(303)
        self.send_header("Location", "/done")
        self.end_headers()
ThreadingHTTPServer(("127.0.0.1", ARGS.port), Handler).serve_forever()
'''

FORM = """<html><head><title>주문</title></head><body><h1>주문</h1>
<form method=post action=/submit>
<label for=name>이름</label><input id=name name=name>
<label for=qty>수량</label><input id=qty name=qty %(qty)s>
<label for=color>색상</label><select id=color name=color><option value=red>빨강</option><option value=blue>파랑</option></select>
<label for=agree>동의</label><input id=agree type=checkbox name=agree value=yes>
<button>제출</button>
</form>%(extra)s</body></html>"""

SUBMITTED = {"id": "outbox", "description": "제출하면 outbox에 기록된다",
             "basis": {"type": "our_condition", "source": "test"},
             "check": {"type": "file_contains", "path": "outbox/*.json", "text": "홍길동"}}


def _form(qty="", extra=""):
    return FORM % {"qty": qty, "extra": extra}


def _write_plan(root: Path, page: str, expectations=None) -> Path:
    app = APP % page
    (root / "app").mkdir(parents=True)
    (root / "app" / "app.py").write_text(app)
    manifest = {
        "schema_version": "replica-implementation-bundle/v1", "claim_id": "claim-001", "scenario_id": "s-01",
        "implementation_type": "deterministic", "dependency_level": "none",
        "entrypoint": "app.py", "command": [sys.executable, "app.py"], "dependencies": [],
        "environment_variables": [],
        "files": [{"path": "app.py", "sha256": hashlib.sha256(app.encode()).hexdigest()}],
        "runtime": {"transport": "web_app", "port_argument": "--port", "ready_path": "/"},
    }
    (root / "app" / "manifest.json").write_text(json.dumps(manifest))
    plan = {
        "schema_version": "replica-web-demo-plan/v1", "claim_id": "claim-001", "title": "주문",
        "manifest": "app/manifest.json", "case_design": "retrospective", "case_author": "test",
        "budget": {"time_limit_seconds": 120, "max_actions_per_case": 8, "model_call_timeout_seconds": 30},
        "cases": [{
            "id": "order", "goal": "주문서를 제출한다", "steps": ["주문서를 채우고 제출한다"],
            "facts": ["이름은 홍길동"], "targeted_barrier": None, "barrier_note": "fixture",
            "covers_steps": [1], "variation": None, "variation_note": "fixture",
            "expectations": expectations or [SUBMITTED],
        }],
    }
    path = root / "plan.json"
    path.write_text(json.dumps(plan, ensure_ascii=False))
    return path


class PlanTester:
    """Answer each tester call with the next scripted plan; refs are found by label on the observed page."""

    def __init__(self, script, hooks=None):
        self.script, self.hooks, self.prompts = list(script), hooks or {}, []

    def __call__(self, prompt):
        request = json.loads(prompt)
        self.prompts.append(request)
        hook = self.hooks.get(len(self.prompts))
        if hook:
            hook()
        step = self.script.pop(0)
        if callable(step):
            return step(request), None
        actions = []
        for action, label, value in step:
            ref = label if not isinstance(label, str) else (
                [e["ref"] for e in request["page"]["elements"] if label in e["label"]][-1])
            actions.append({"action": action, "ref": ref, "value": value, "reason": f"{action} {label}"})
        if len(self.prompts) and "remaining_model_calls" not in request:
            return actions[0], None  # Single mode takes one action per call.
        return {"actions": actions}, None


def _no_judge(prompt):
    raise AssertionError("these cases use deterministic checks only")


def _checkpoint_case(root: Path) -> dict:
    return json.loads((root / "out" / "checkpoint.json").read_text())["cases"][0]


def _events(root: Path) -> list[dict]:
    return [json.loads(line) for line in (root / "out" / "events.jsonl").read_text().splitlines()]


DONE = [("done", None, None)]


@unittest.skipUnless(HAS_PLAYWRIGHT, "web demo needs the optional playwright dependency")
class ActionPlanTest(unittest.TestCase):
    def _run(self, root, page, tester, expectations=None, **options):
        return run_web_demo(_write_plan(root, page, expectations), root / "out", tester=tester, judge=_no_judge,
                            **options)

    def test_one_plan_fills_a_form_with_evidence_for_every_action(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            tester = PlanTester([
                [("fill", "이름", "홍길동"), ("fill", "수량", "3"), ("select", "색상", "파랑"),
                 ("check", "동의", None), ("click", "제출", None)],
                DONE,
            ])
            result = self._run(root, _form(), tester)
            case = result["cases"][0]
            self.assertEqual(case["execution_status"], "completed")
            self.assertEqual(case["budgets"], {"max_model_calls": 8, "max_actions": 8, "model_calls": 2, "actions": 6})
            self.assertEqual(case["expectations"][0]["status"], "passed")
            saved = json.loads(next((root / "out" / "cases" / "order" / "workspace").rglob("submission-1.json"))
                               .read_text())
            self.assertEqual(saved, {"name": "홍길동", "qty": "3", "color": "blue", "agree": "yes"})
            events = _events(root)
            self.assertEqual([e["action"] for e in events], ["fill", "fill", "select", "check", "click", "done"])
            self.assertEqual([e.get("plan_index") for e in events[:5]], [1, 2, 3, 4, 5])
            self.assertEqual({e["plan_id"] for e in events[:5]}, {"order-plan-001"})
            self.assertTrue(all((root / "out" / e["screenshot"]).is_file() for e in events))
            self.assertEqual([e["effect"]["status"] for e in events[:4]], ["ok"] * 4)
            self.assertNotIn("plan_stop", events[3])
            # Every intermediate step was observed again without renumbering refs.
            observed = [o["event_id"] for o in _checkpoint_case(root)["observations"]]
            self.assertEqual(observed[:5], ["order-001", "order-002", "order-003", "order-004", "order-005"])
            self.assertEqual(case["plan_stats"]["multi_action_plans"], 1)
            self.assertEqual(case["plan_stats"]["cancelled_actions"], 0)
            self.assertNotIn("events", case)
            self.assertEqual(result["model_configuration"]["tester_mode"], "plan")
            self.assertEqual(tester.prompts[1]["remaining_model_calls"], 7)
            self.assertIsNone(tester.prompts[1]["last_plan"])

    def test_a_replaced_or_duplicated_node_stops_before_the_action(self):
        replace = ("<label for=note>비고</label><input id=note name=note>"
                   "<button type=button onclick=\"setTimeout(() => { const n = document.getElementById('note');"
                   " n.outerHTML = n.outerHTML; }, 1500)\">교체준비</button>"
                   "<button type=button onclick=\"setTimeout(() => { const n = document.getElementById('note');"
                   " n.after(n.cloneNode(true)); }, 1500)\">복제준비</button>")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            # The page changes while the tester is thinking, after the refs were registered.
            pause = lambda: time.sleep(3)
            tester = PlanTester([
                [("click", "교체준비", None)], [("fill", "비고", "메모")],
                [("click", "복제준비", None)], [("fill", "비고", "메모")],
                DONE,
            ], hooks={2: pause, 4: pause})
            result = self._run(root, _form(extra=replace), tester)
            plans = result["cases"][0]["plans"]
            self.assertEqual([(p["status"], p["performed"], (p["stop"] or {}).get("reason")) for p in plans[:4]],
                             [("completed", 1, None), ("stopped", 0, "node_replaced"),
                              ("completed", 1, None), ("stopped", 0, "target_ambiguous")])
            self.assertEqual(tester.prompts[2]["last_plan"]["performed"], [])
            self.assertEqual(tester.prompts[2]["last_plan"]["not_performed"][0]["action"], "fill")
            self.assertNotIn("fill", [e["action"] for e in _events(root)])

    def test_values_the_app_did_not_keep_stop_the_plan(self):
        extra = ("<label for=code>코드</label><input id=code maxlength=5>"
                 "<label for=letters>문자</label><input id=letters oninput=\"this.value = this.value.replace(/[0-9]/g, '')\">"
                 "<label for=free>자유글</label><textarea id=free></textarea>"
                 "<label for=short>제한글</label><textarea id=short maxlength=3000></textarea>"
                 "<label for=more>추가 정보</label><input id=more type=checkbox"
                 " onchange=\"document.getElementById('detail').hidden = !this.checked\">"
                 "<div id=detail hidden><label for=extra>상세</label><input id=extra></div>")
        long = "가" * 5000
        with TemporaryDirectory() as directory:
            root = Path(directory)
            tester = PlanTester([
                [("fill", "코드", "abcdefgh"), ("fill", "이름", "홍길동")],
                [("fill", "문자", "abc123"), ("fill", "이름", "홍길동")],
                [("fill", "자유글", long), ("fill", "제한글", long)],
                [("check", "추가 정보", None), ("fill", "이름", "홍길동")],
                DONE,
            ])
            result = self._run(root, _form(extra=extra), tester)
            case = result["cases"][0]
            self.assertEqual([(p["size"], p["performed"], (p["stop"] or {}).get("reason")) for p in case["plans"][:4]],
                             [(2, 1, "postcondition_mismatch"), (2, 1, "postcondition_mismatch"),
                              (2, 2, None), (2, 1, "new_field")])
            effects = [e.get("effect") for e in _events(root)]
            self.assertEqual(effects[0], {"status": "mismatch", "expected_length": 8, "actual_length": 5,
                                          "actual": "abcde"})
            self.assertEqual(effects[1]["actual"], "abc")
            self.assertEqual(effects[2], {"status": "ok", "expected_length": 5000, "actual_length": 5000})
            self.assertEqual((effects[3]["status"], effects[3]["actual_length"]), ("mismatch", 3000))
            self.assertEqual(case["plans"][3]["stop"]["detail"][0]["label"], "상세")
            self.assertEqual(case["plan_stats"]["stop_reasons"], {"postcondition_mismatch": 2, "new_field": 1})
            self.assertEqual(case["plan_stats"]["cancelled_actions"], 3)
            # The tester sees which planned actions never ran.
            self.assertEqual(tester.prompts[1]["last_plan"]["not_performed"][0]["value"], "홍길동")

    def test_navigation_ends_the_plan_after_the_completed_prefix(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            tester = PlanTester([
                [("fill", "이름", "홍길동"), ("click", "제출", None),
                 ("wait_for", None, json.dumps({"text": "접수 완료", "state": "present", "seconds": 5}))],
                DONE,
            ])
            result = self._run(root, _form(), tester)
            case = result["cases"][0]
            self.assertEqual(case["execution_status"], "completed")
            last_plan = tester.prompts[1]["last_plan"]
            self.assertEqual(last_plan["stop"]["reason"], "url_changed")
            self.assertEqual(last_plan["performed"], ["order-001", "order-002"])
            self.assertEqual([a["action"] for a in last_plan["not_performed"]], ["wait_for"])
            # The performed click is in the history, so the tester knows not to submit again.
            self.assertEqual([a["action"] for a in tester.prompts[1]["previous_actions"]], ["fill", "click"])
            outbox = list((root / "out" / "cases" / "order" / "workspace").rglob("submission-*.json"))
            self.assertEqual(len(outbox), 1)

    def test_invalid_plans_spend_calls_but_run_nothing(self):
        def raw(*actions):
            return lambda request: {"actions": [dict(zip(("action", "ref", "value", "reason"), a + ("x",)))
                                                for a in actions]}
        with TemporaryDirectory() as directory:
            root = Path(directory)
            tester = PlanTester([
                raw(*[("fill", 1, "a")] * 9),
                raw(("fill", 1, "a"), ("done", None, None)),
                raw(("click", 1, None), ("click", 2, None)),
                raw(("fill", 999, "a")),
                raw(("hover", 1, None)),
                raw(("click", 1, None), ("fill", 2, "a")),
                raw(("fill", 1, "a"), ("fill", 1, "b")),
                raw(("fill", 1, 3)),
            ])
            result = self._run(root, _form(), tester)
            case = result["cases"][0]
            problems = [p["problem"] for p in case["plans"]]
            for problem, expected in zip(problems, ["9 actions but only 8", "only action", "at most one click",
                                                    "ref 999", "unknown action", "must end the plan",
                                                    "more than once", "string value"]):
                self.assertIn(expected, problem)
            self.assertEqual(case["budgets"]["model_calls"], 8)
            self.assertEqual(case["budgets"]["actions"], 0)
            self.assertEqual(case["execution_status"], "model_call_limit")
            self.assertIn("model_call_limit", case["stop_reason"])
            self.assertEqual(case["plan_stats"]["rejected"], 8)
            self.assertEqual(_events(root), [])
            self.assertEqual(case["expectations"][0]["status"], "not_evaluated")
            self.assertEqual(tester.prompts[1]["last_plan"], {"status": "rejected", "problem": problems[0]})

    def test_wait_for_reports_a_timeout(self):
        extra = "<button type=button>시작</button>"
        with TemporaryDirectory() as directory:
            root = Path(directory)
            tester = PlanTester([
                [("click", "시작", None), ("wait_for", None, json.dumps({"text": "시작", "state": "absent", "seconds": 1}))],
                DONE,
            ])
            self._run(root, _form(extra=extra), tester)
            wait = _events(root)[1]["wait"]
            self.assertEqual(wait["reason"], "timeout")
            self.assertGreaterEqual(wait["seconds"], 1)

    def test_unwritable_evidence_blocks_the_case(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            screens = root / "out" / "cases" / "order" / "screens"
            tester = PlanTester([[("fill", "이름", "홍길동"), ("fill", "수량", "3")]],
                                hooks={1: lambda: screens.chmod(0o500)})
            try:
                result = self._run(root, _form(), tester)
            finally:
                screens.chmod(0o700)
            case = result["cases"][0]
            self.assertEqual((case["execution_status"], case["environment_error"]), ("blocked", "evidence_write"))
            self.assertEqual(case["budgets"]["actions"], 1)
            self.assertEqual(case["plans"][0]["stop"]["reason"], "evidence_write")
            self.assertEqual(case["expectations"][0]["status"], "not_evaluated")
            self.assertIsNone(_events(root)[0]["screenshot"])

    def test_a_rejected_value_is_still_a_failed_result(self):
        expectations = [{"id": "qty", "description": "수량 3이 저장된다",
                         "basis": {"type": "our_condition", "source": "test"},
                         "check": {"type": "file_contains", "path": "outbox/*.json", "text": '"qty": "3"'}}]
        with TemporaryDirectory() as directory:
            root = Path(directory)
            tester = PlanTester([
                [("fill", "이름", "홍길동"), ("fill", "수량", "3"), ("click", "제출", None)],
                [("click", "제출", None)],
                DONE,
            ])
            result = self._run(root, _form(qty="oninput=\"this.value = this.value.replace(/[0-9]/g, '')\""),
                               tester, expectations)
            case = result["cases"][0]
            self.assertEqual(case["plans"][0]["stop"]["reason"], "postcondition_mismatch")
            self.assertEqual(case["execution_status"], "completed")
            self.assertEqual(case["expectations"][0]["status"], "failed")
            self.assertEqual(result["outcome"]["passed"], 0)

    def test_dialogs_and_transient_alerts_are_recorded(self):
        extra = ("<button type=button onclick=\"alert('주의')\">경고</button>"
                 "<label for=memo>메모</label><input id=memo oninput=\"const a = document.createElement('div');"
                 " a.setAttribute('role', 'alert'); a.textContent = '형식 확인'; document.body.append(a);"
                 " setTimeout(() => a.remove(), 50)\">")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            tester = PlanTester([
                [("click", "경고", None)],
                [("fill", "메모", "x"), ("fill", "이름", "홍길동")],
                DONE,
            ])
            result = self._run(root, _form(extra=extra), tester)
            events = _events(root)
            self.assertIn({"kind": "dialog", "type": "alert", "text": "주의"}, events[0]["signals"])
            stop = result["cases"][0]["plans"][1]["stop"]
            self.assertEqual(stop["reason"], "signal")
            self.assertIn({"kind": "alert", "text": "형식 확인"}, stop["detail"])
            self.assertFalse(any(e["text"] == "형식 확인" for e in tester.prompts[2]["page"].get("signals", [])))

    def test_single_mode_keeps_one_action_per_call(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            tester = PlanTester([[("fill", "이름", "홍길동")], [("click", "제출", None)], DONE])
            result = self._run(root, _form(), tester, tester_mode="single")
            case = result["cases"][0]
            self.assertEqual(result["model_configuration"]["tester_mode"], "single")
            self.assertEqual(case["execution_status"], "completed")
            self.assertNotIn("plans", case)
            self.assertNotIn("remaining_model_calls", tester.prompts[0])
            self.assertNotIn("plan_id", _events(root)[0])
            with self.assertRaisesRegex(ValueError, "tester_mode"):
                run_web_demo(root / "plan.json", root / "again", tester=tester, judge=_no_judge, tester_mode="batch")

    def test_changes_while_thinking_cancel_before_the_first_action(self):
        extra = ('<div id=status>준비</div><button type=button onclick="setTimeout(() => '
                 '{document.getElementById(\'status\').textContent = \'다시 확인\';}, 1500)">변경</button>')
        with TemporaryDirectory() as directory:
            root = Path(directory)
            tester = PlanTester([[("click", "변경", None)], [("fill", "이름", "홍길동")], DONE],
                                hooks={2: lambda: time.sleep(3)})
            result = self._run(root, _form(extra=extra), tester)
            self.assertEqual(result["cases"][0]["plans"][1]["performed"], 0)
            self.assertEqual(result["cases"][0]["plans"][1]["stop"]["reason"], "text_changed")
            self.assertNotIn("fill", [e["action"] for e in _events(root)])

    def test_dependent_field_changes_stop_before_submitting(self):
        for change in ("document.getElementById('name').disabled = true",
                       "document.getElementById('name').value = 'changed'",
                       "document.getElementById('name').setAttribute('aria-invalid','true')",
                       "document.getElementById('color').options[1].disabled = true"):
            with self.subTest(change=change), TemporaryDirectory() as directory:
                root = Path(directory)
                tester = PlanTester([[("fill", "수량", "3"), ("click", "제출", None)], DONE])
                result = self._run(root, _form(qty=f'oninput="{change}"'), tester)
                self.assertEqual(result["cases"][0]["plans"][0]["stop"]["reason"], "field_changed")
                self.assertNotIn("click", [e["action"] for e in _events(root)])

    def test_fill_then_enter_submits_once(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            tester = PlanTester([[("fill", "이름", "홍길동"), ("press", "이름", "Enter")], DONE])
            result = self._run(root, _form(), tester)
            self.assertEqual(result["outcome"]["passed"], 1)
            self.assertEqual(result["cases"][0]["budgets"]["model_calls"], 2)
            self.assertEqual(len(list((root / "out" / "cases").rglob("submission-*.json"))), 1)

    def test_console_error_cancels_plan_and_is_seen_by_judge(self):
        extra = '<label for=memo>메모</label><input id=memo oninput="console.error(\'입력 오류\')">'
        with TemporaryDirectory() as directory:
            root = Path(directory)
            tester = PlanTester([[("fill", "메모", "x"), ("fill", "이름", "홍길동")], DONE])
            prompts = []
            def judge(prompt):
                prompts.append(json.loads(prompt))
                return {"verdicts": [{"id": "error", "status": "failed", "reason": "오류가 관측됨",
                                      "evidence_event_ids": ["order-001"]}]}, None
            expectation = {"id": "error", "description": "오류 없이 입력된다",
                           "basis": {"type": "our_condition", "source": "test"}}
            result = run_web_demo(_write_plan(root, _form(extra=extra), [expectation]), root / "out",
                                  tester=tester, judge=judge)
            self.assertEqual(result["cases"][0]["plans"][0]["stop"]["reason"], "signal")
            self.assertIn({"kind": "console_error", "text": "입력 오류"}, prompts[0]["events"][0]["signals"])
            self.assertIn("only confirms that the UI accepted", prompts[0]["instruction"])
            self.assertEqual(result["outcome"]["failed"], 1)

    def test_unobserved_wait_condition_cannot_run(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            tester = PlanTester([[("wait_for", None, json.dumps({"text": "imaginary", "state": "present"}))], DONE])
            result = self._run(root, _form(), tester)
            self.assertEqual(result["cases"][0]["plans"][0]["stop"]["reason"], "unobserved_wait")
            self.assertNotIn("wait_for", [e["action"] for e in _events(root)])

    def test_popup_stops_before_trailing_wait(self):
        extra = '<button type=button onclick="window.open(\'/done\')">새 창</button>'
        with TemporaryDirectory() as directory:
            root = Path(directory)
            tester = PlanTester([[("click", "새 창", None), ("wait", None, "1")], DONE])
            result = self._run(root, _form(extra=extra), tester)
            self.assertEqual(result["cases"][0]["plans"][0]["stop"]["reason"], "signal")
            self.assertIn("popup", [s["kind"] for s in _events(root)[0]["signals"]])
            self.assertNotIn("wait", [e["action"] for e in _events(root)])

    def test_failed_observation_is_an_environment_stop(self):
        for failure_call in (1, 2):
            with self.subTest(failure_call=failure_call), TemporaryDirectory() as directory:
                root = Path(directory)
                tester = PlanTester([[("fill", "이름", "홍길동")]])
                actual_peek, calls = web_demo.peek, []
                def sometimes_unavailable(page):
                    calls.append(None)
                    return None if len(calls) == failure_call else actual_peek(page)
                with mock.patch.object(web_demo, "peek", side_effect=sometimes_unavailable):
                    result = self._run(root, _form(), tester)
                case = result["cases"][0]
                self.assertEqual((case["execution_status"], case["environment_error"]), ("blocked", "browser_failure"))
                self.assertEqual(case["budgets"]["actions"], 0)
                self.assertEqual(case["budgets"]["model_calls"], failure_call - 1)


class ReadPlanTest(unittest.TestCase):
    ELEMENTS = [{"ref": 1}, {"ref": 2}]

    def test_single_action_answer_is_a_one_action_plan(self):
        actions, problem = read_plan({"action": "click", "ref": 1, "value": None, "reason": "r"}, self.ELEMENTS, 8, {})
        self.assertIsNone(problem)
        self.assertEqual(len(actions), 1)

    def test_click_may_be_followed_only_by_one_wait(self):
        ok = [{"action": "fill", "ref": 1, "value": "a"}, {"action": "click", "ref": 2},
              {"action": "wait", "value": "1"}]
        self.assertIsNone(read_plan({"actions": ok}, self.ELEMENTS, 8, {})[1])
        late = ok + [{"action": "wait", "value": "1"}]
        self.assertIsNotNone(read_plan({"actions": late}, self.ELEMENTS, 8, {})[1])
        self.assertIn("non-empty", read_plan({"actions": []}, self.ELEMENTS, 8, {})[1])
        self.assertIn("ref True", read_plan({"actions": [{"action": "click", "ref": True}]}, self.ELEMENTS, 8, {})[1])

    def test_malformed_model_fields_are_rejected_without_crashing(self):
        for action in ({"action": []}, {"action": "click", "ref": []},
                       {"action": "click", "ref": {}}, {"action": "upload", "ref": 1, "value": []}):
            with self.subTest(action=action):
                self.assertIsNotNone(read_plan({"actions": [action]}, self.ELEMENTS, 8, {})[1])


if __name__ == "__main__":
    unittest.main()
