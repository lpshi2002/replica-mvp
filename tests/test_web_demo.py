import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
import unittest
import urllib.parse
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from replica_mvp.bundle_runtime import web_app_session
from replica_mvp.model_calls import install_meter, read_receipt, run_model_cli, summarize_receipts
from replica_mvp.web_demo import run_web_demo, validate_demo_plan


HAS_PLAYWRIGHT = importlib.util.find_spec("playwright") is not None

# A small approval workflow: register a request, the app asks the model CLI for a summary,
# then a reviewer approves (writes outbox/) or rejects (no outbox file). With --base-path it
# serves every page and form under that path, as a company-app feature does.
APP = r'''
import argparse, html, json, os, subprocess, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, required=True)
parser.add_argument("--base-path", default="")
ARGS = parser.parse_args()
BASE = ARGS.base_path
DATA = "data/requests.json"
def load():
    return json.load(open(DATA)) if os.path.exists(DATA) else []
def save(items):
    os.makedirs("data", exist_ok=True)
    json.dump(items, open(DATA, "w"), ensure_ascii=False)
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def do_GET(self):
        rows = "".join(
            f"<li>{html.escape(r['text'])} [{r['state']}] {html.escape(r['summary'])}"
            + (f"<form method=post action={BASE}/review><input type=hidden name=id value={r['id']}>"
               f"<button name=decision value=approve>승인 {r['id']}</button>"
               f"<button name=decision value=reject>거절 {r['id']}</button></form>" if r["state"] == "pending" else "")
            + "</li>" for r in load())
        body = ("<html><head><title>승인 요청</title></head><body><h1>승인 요청</h1>"
                f"<form method=post action={BASE}/requests><label for=t>요청 내용</label>"
                "<textarea id=t name=text></textarea><button>등록</button></form>"
                f"<ul>{rows}</ul></body></html>").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)
    def do_POST(self):
        form = urllib.parse.parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
        items = load()
        if self.path == BASE + "/requests":
            text = form["text"][0]
            out = subprocess.run(["claude", "-p", "--output-format", "json"], input=text.encode(),
                                 capture_output=True, timeout=20)
            summary = json.loads(out.stdout)["structured_output"]["summary"]
            items.append({"id": f"r{len(items) + 1}", "text": text, "state": "pending", "summary": summary})
        else:
            item = next(i for i in items if i["id"] == form["id"][0])
            item["state"] = "approved" if form["decision"][0] == "approve" else "rejected"
            if item["state"] == "approved":
                os.makedirs("outbox", exist_ok=True)
                json.dump(item, open(f"outbox/{item['id']}.json", "w"), ensure_ascii=False)
        save(items)
        self.send_response(303)
        self.send_header("Location", BASE + "/")
        self.end_headers()
ThreadingHTTPServer(("127.0.0.1", ARGS.port), Handler).serve_forever()
'''

# Stands in for the real model CLI: echoes a usage envelope, or sleeps when asked to.
FAKE_CLI = r'''
import json, os, sys, time
prompt = sys.stdin.read()
if "sleep" in sys.argv:
    open(sys.argv[-1], "w").write(str(os.getpid()))
    time.sleep(60)
if "fail" in sys.argv:
    sys.stderr.write("boom")
    sys.exit(3)
schema = json.loads(sys.argv[sys.argv.index("--json-schema") + 1]) if "--json-schema" in sys.argv else {}
required = schema.get("required", [])
result = {"summary": "요약: " + prompt[:20]}
if "verdicts" in required:
    result = {"verdicts": []}
print(json.dumps({"type": "result", "is_error": False, "structured_output": result,
                  "usage": {"input_tokens": 5, "output_tokens": 7, "cache_read_input_tokens": 100},
                  "total_cost_usd": 0.01, "modelUsage": {"fake-model": {"costBasis": "list"}}}))
'''


def _write_cli(directory: Path, name: str = "claude") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(f"#!{sys.executable}\n{FAKE_CLI}")
    path.chmod(0o755)
    return path


def _write_app(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "app.py").write_text(APP)
    manifest = {
        "schema_version": "replica-implementation-bundle/v1", "claim_id": "claim-001", "scenario_id": "s-01",
        "implementation_type": "hybrid", "dependency_level": "commercial_api",
        "entrypoint": "app.py", "command": [sys.executable, "app.py"], "dependencies": [],
        "environment_variables": [],
        "files": [{"path": "app.py", "sha256": hashlib.sha256(APP.encode()).hexdigest()}],
        "runtime": {"transport": "web_app", "port_argument": "--port", "ready_path": "/"},
    }
    path = directory / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path


def _plan(root: Path, cases=None) -> Path:
    _write_app(root / "app")
    plan = {
        "schema_version": "replica-web-demo-plan/v1", "claim_id": "claim-001", "title": "승인 워크플로",
        "manifest": "app/manifest.json", "case_design": "retrospective", "case_author": "test",
        "budget": {"time_limit_seconds": 120, "max_actions_per_case": 8, "model_call_timeout_seconds": 30},
        "cases": cases or [{
            "id": "approve", "goal": "요청을 등록하고 승인한다",
            "steps": ["요청 내용에 '노트북 구매'를 입력하고 등록한다", "등록된 요청을 승인한다"],
            "facts": ["요청 내용은 '노트북 구매'"], "targeted_barrier": None,
            "barrier_note": "공개 장벽 주장 미확인", "covers_steps": [1, 2],
            "variation": None, "variation_note": "fixture",
            "expectations": [
                {"id": "outbox", "description": "승인하면 outbox에 기록된다",
                 "basis": {"type": "our_condition", "source": "test"},
                 "check": {"type": "file_contains", "path": "outbox/*.json", "text": "노트북 구매"}},
                {"id": "summary", "description": "등록한 요청의 요약이 화면에 보인다",
                 "basis": {"type": "public_rule", "source": "test"}},
            ],
        }],
    }
    path = root / "plan.json"
    path.write_text(json.dumps(plan, ensure_ascii=False))
    return path


def _scripted_tester(script):
    """Pick refs by label the way a careful user would; no model involved."""
    remaining = list(script)

    def tester(prompt):
        page = json.loads(prompt)["page"]
        action, label, value = remaining.pop(0)
        ref = None
        if label is not None:
            # The last match: a company app's navigation bar comes before the feature's own controls.
            ref = [e["ref"] for e in page["elements"] if label in e["label"]][-1]
        return {"action": action, "ref": ref, "value": value, "reason": f"step {action}"}, None
    return tester


def _passing_judge(prompt):
    request = json.loads(prompt)
    return {"verdicts": [{"id": e["id"], "status": "passed", "reason": "보임",
                          "evidence_event_ids": [request["events"][-1]["event_id"]]}
                         for e in request["expectations"]]}, None


class DemoPlanTest(unittest.TestCase):
    def test_plan_requires_basis_and_barrier_reason(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            plan = json.loads(_plan(root).read_text())
            validate_demo_plan(plan, root)
            missing_basis = json.loads(json.dumps(plan))
            del missing_basis["cases"][0]["expectations"][0]["basis"]
            with self.assertRaisesRegex(ValueError, "basis"):
                validate_demo_plan(missing_basis, root)
            no_barrier = json.loads(json.dumps(plan))
            del no_barrier["cases"][0]["barrier_note"]
            with self.assertRaisesRegex(ValueError, "barrier"):
                validate_demo_plan(no_barrier, root)

    def test_plan_requires_web_runtime(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            plan = json.loads(_plan(root).read_text())
            manifest = json.loads((root / "app" / "manifest.json").read_text())
            manifest["runtime"] = {"transport": "stdio_json"}
            (root / "app" / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "web_app"):
                validate_demo_plan(plan, root)


class MeterTest(unittest.TestCase):
    def test_wrapper_passes_bytes_and_exit_status_through(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _write_cli(root / "real")
            with patch.dict(os.environ, {"PATH": f"{root / 'real'}{os.pathsep}{os.environ['PATH']}"}):
                installed = install_meter(root / "bin", root / "receipts", "replica_runtime")
            self.assertEqual(installed["claude"], str((root / "real" / "claude").resolve()))
            for extra in ([], ["fail"]):
                direct = subprocess.run([str(root / "real" / "claude"), "-p", *extra], input=b"hello",
                                        capture_output=True)
                wrapped = subprocess.run([str(root / "bin" / "claude"), "-p", *extra], input=b"hello",
                                         capture_output=True)
                self.assertEqual((wrapped.stdout, wrapped.stderr, wrapped.returncode),
                                 (direct.stdout, direct.stderr, direct.returncode))
            calls = summarize_receipts(root / "receipts")["calls"]
            self.assertEqual([c["status"] for c in calls], ["completed", "failed"])
            self.assertEqual(calls[0]["usage"]["cache_read_input_tokens"], 100)
            self.assertEqual(calls[0]["models"], ["fake-model"])

    def test_killing_wrapper_also_ends_real_cli(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _write_cli(root / "real")
            with patch.dict(os.environ, {"PATH": f"{root / 'real'}{os.pathsep}{os.environ['PATH']}"}):
                install_meter(root / "bin", root / "receipts", "replica_runtime")
            pid_file = root / "child.pid"
            with self.assertRaises(subprocess.TimeoutExpired):
                # The same kill a caller's subprocess timeout performs on the process it started.
                subprocess.run([str(root / "bin" / "claude"), "sleep", str(pid_file)], input=b"x",
                               capture_output=True, timeout=1.5)
            receipt_dir = next((root / "receipts").iterdir())
            for _ in range(50):
                if (receipt_dir / "orphan.json").exists():
                    break
                time.sleep(0.1)
            child = int(pid_file.read_text())
            time.sleep(0.2)
            with self.assertRaises(ProcessLookupError):
                os.kill(child, 0)
            receipt = read_receipt(receipt_dir)
            self.assertEqual(receipt["status"], "incomplete")
            self.assertTrue(receipt["wrapper_terminated"])

    def test_runner_call_records_receipt_and_timeout(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _write_cli(root / "real")
            schema = {"type": "object", "required": ["summary"], "properties": {"summary": {"type": "string"}}}
            with patch.dict(os.environ, {"PATH": f"{root / 'real'}{os.pathsep}{os.environ['PATH']}"}):
                result, call_id = run_model_cli("claude", "질문", schema, receipts=root / "receipts",
                                                phase="tester", timeout=10)
            self.assertEqual(result["summary"], "요약: 질문")
            receipt = read_receipt(root / "receipts" / call_id)
            self.assertEqual((receipt["phase"], receipt["status"], receipt["cost_usd"]), ("tester", "completed", 0.01))
            phases = summarize_receipts(root / "receipts")["phases"]
            self.assertEqual(phases["tester"]["usage"], {"input_tokens": 5, "output_tokens": 7,
                                                         "cache_read_input_tokens": 100})


class WebAppSessionTest(unittest.TestCase):
    def test_app_serves_and_keeps_saved_state_across_restarts(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _write_cli(root / "real")
            manifest = _write_app(root / "app")
            with patch.dict(os.environ, {"PATH": f"{root / 'real'}{os.pathsep}{os.environ['PATH']}"}):
                with web_app_session(manifest, 30, workspace=root / "state") as (base_url, app_root):
                    data = urllib.parse.urlencode({"text": "의자"}).encode()
                    urllib.request.build_opener(urllib.request.ProxyHandler({})).open(base_url + "/requests", data)
                with web_app_session(manifest, 30, workspace=root / "state") as (base_url, app_root):
                    page = urllib.request.build_opener(urllib.request.ProxyHandler({})).open(base_url + "/").read()
            self.assertIn("의자", page.decode())
            self.assertTrue((app_root / "data" / "requests.json").is_file())


@unittest.skipUnless(HAS_PLAYWRIGHT, "web demo needs the optional playwright dependency")
class WebDemoTest(unittest.TestCase):
    def _run(self, root, tester, judge=_passing_judge, cases=None):
        _write_cli(root / "real")
        with patch.dict(os.environ, {"PATH": f"{root / 'real'}{os.pathsep}{os.environ['PATH']}"}):
            return run_web_demo(_plan(root, cases), root / "out", tester=tester, judge=judge)

    def test_ai_browser_case_saves_actions_files_and_costs(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            result = self._run(root, _scripted_tester([
                ("fill", "요청 내용", "노트북 구매"), ("click", "등록", None), ("click", "승인", None), ("done", None, None),
            ]))
            case = result["cases"][0]
            self.assertEqual(case["execution_status"], "completed")
            self.assertEqual({e["id"]: e["status"] for e in case["expectations"]},
                             {"outbox": "passed", "summary": "passed"})
            self.assertIn({"path": "outbox/r1.json", "change": "added"}, case["file_changes"])
            events = [json.loads(line) for line in (root / "out" / "events.jsonl").read_text().splitlines()]
            self.assertEqual([e["action"] for e in events], ["fill", "click", "click", "done"])
            self.assertTrue(all((root / "out" / e["screenshot"]).is_file() for e in events))
            runtime = result["costs"]["phases"]["replica_runtime"]
            self.assertEqual((runtime["calls"], runtime["usage"]["output_tokens"]), (1, 7))
            # The app's model call happened while the tester clicked 등록.
            self.assertEqual([r["event_id"] for r in result["receipts"] if r["phase"] == "replica_runtime"],
                             ["approve-002"])
            self.assertTrue((root / "out" / "report.md").read_text().startswith("# AI 사례 시연"))
            with self.assertRaisesRegex(ValueError, "never overwritten"):
                self._run(root, _scripted_tester([("done", None, None)]))

    def test_unfinished_case_does_not_pass_absence_checks(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cases = [{
                "id": "reject", "goal": "요청을 거절한다", "steps": ["요청을 거절한다"], "targeted_barrier": None,
                "barrier_note": "없음", "covers_steps": [2], "variation": None, "variation_note": "fixture",
                "expectations": [{"id": "no-outbox", "description": "거절하면 outbox가 없다",
                                  "basis": {"type": "our_condition", "source": "test"},
                                  "check": {"type": "file_absent", "path": "outbox/*"}}],
            }]
            result = self._run(root, _scripted_tester([("give_up", None, None)]), cases=cases)
            case = result["cases"][0]
            self.assertEqual(case["execution_status"], "gave_up")
            self.assertEqual(case["expectations"][0]["status"], "not_evaluated")

    def test_unfinished_case_does_not_fail_missing_results(self):
        with TemporaryDirectory() as directory:
            result = self._run(Path(directory), _scripted_tester([
                ("fill", "요청 내용", "노트북 구매"), ("click", "등록", None), ("give_up", None, None),
            ]))
            case = result["cases"][0]
            self.assertEqual("gave_up", case["execution_status"])
            outbox = next(e for e in case["expectations"] if e["id"] == "outbox")
            self.assertEqual("not_evaluated", outbox["status"])
            self.assertIn("before this result could be checked", outbox["reason"])

    def test_judge_failure_is_not_evaluated_not_failed(self):
        def broken_judge(prompt):
            raise RuntimeError("judge unavailable")
        with TemporaryDirectory() as directory:
            result = self._run(Path(directory), _scripted_tester([
                ("fill", "요청 내용", "노트북 구매"), ("click", "등록", None), ("click", "승인", None), ("done", None, None),
            ]), judge=broken_judge)
            statuses = {e["id"]: e["status"] for e in result["cases"][0]["expectations"]}
            self.assertEqual(statuses, {"outbox": "passed", "summary": "not_evaluated"})
            self.assertEqual(result["outcome"]["failed"], 0)


class BrowserUnavailableTest(unittest.TestCase):
    def test_missing_browser_blocks_cases_without_failing_them(self):
        def no_browser():
            raise RuntimeError("no playwright")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_web_demo(_plan(root), root / "out", tester=_scripted_tester([]), judge=_passing_judge,
                                  browser_factory=no_browser)
            case = result["cases"][0]
            self.assertEqual(case["execution_status"], "blocked")
            self.assertEqual({e["status"] for e in case["expectations"]}, {"not_evaluated"})
            self.assertTrue((root / "out" / "demo-result.json").is_file())


if __name__ == "__main__":
    unittest.main()
