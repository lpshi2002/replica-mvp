import hashlib
import json
import os
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from replica_mvp.web_demo import freeze_demo_plan, run_web_demo, validate_demo_plan
from replica_mvp.web_inputs import restore_inputs, seal_inputs, sealed_uploads
from tests.test_web_action_plans import _write_plan
from tests.test_web_demo import _scripted_tester


UPLOAD_APP = '''import argparse
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
class H(BaseHTTPRequestHandler):
 def log_message(self,*a): pass
 def do_GET(self):
  body=b'<form method="post" enctype="multipart/form-data"><label>Document<input type="file" name="doc"></label><button>Upload</button></form>'
  self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.end_headers();self.wfile.write(body)
 def do_POST(self):
  data=self.rfile.read(int(self.headers['Content-Length']))
  message=BytesParser(policy=default).parsebytes(('Content-Type: '+self.headers['Content-Type']+'\\r\\n\\r\\n').encode()+data)
  part=next(p for p in message.iter_parts() if p.get_filename())
  content=part.get_payload(decode=True)
  Path('result.txt').write_bytes(content)
  self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.end_headers();self.wfile.write(b'<pre>'+content+b'</pre>')
p=argparse.ArgumentParser();p.add_argument('--port',type=int);a=p.parse_args()
HTTPServer(('127.0.0.1',a.port),H).serve_forever()
'''


def upload_plan(root, *, content=b"Alice has 12 items", name="sample.txt"):
    expectation = {"id": "copied", "description": "The uploaded content Alice is saved",
                   "basis": {"type": "our_condition", "source": "test"},
                   "check": {"type": "file_contains", "path": "result.txt", "text": "Alice"}}
    path = _write_plan(root, "", [expectation])
    app = root / "app/app.py"
    app.write_text(UPLOAD_APP)
    manifest = json.loads((root / "app/manifest.json").read_text())
    manifest["files"][0]["sha256"] = hashlib.sha256(app.read_bytes()).hexdigest()
    (root / "app/manifest.json").write_text(json.dumps(manifest))
    (root / name).write_bytes(content)
    plan = json.loads(path.read_text())
    case = plan["cases"][0]
    case.update(goal="Upload Alice's document", steps=["Upload the supplied document"], facts=["Document is for Alice"],
                uploads=[{"path": name, "sha256": hashlib.sha256(content).hexdigest()}])
    path.write_text(json.dumps(plan))
    return path


def upload_tester(name="sample.txt"):
    return _scripted_tester([("upload", "Document", name), ("click", "Upload", None), ("done", None, None)])


class SealedInputsTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = upload_plan(self.root)
        self.plan = json.loads(self.path.read_text())
        self.case = self.plan["cases"][0]

    def test_freeze_copies_and_hashes_without_modifying_research(self):
        source = deepcopy(self.plan)
        for key in ("schema_version", "claim_id", "manifest"):
            source.pop(key)
        source["cases"][0]["uploads"][0].pop("sha256")
        original = deepcopy(source)
        frozen = freeze_demo_plan(source, "claim-001", self.root, self.root / "frozen")
        upload = json.loads(frozen.read_text())["cases"][0]["uploads"][0]
        self.assertEqual(hashlib.sha256((self.root / "sample.txt").read_bytes()).hexdigest(), upload["sha256"])
        self.assertEqual(original, source)

    def test_hashless_legacy_can_be_read_but_not_executed(self):
        self.case["uploads"][0].pop("sha256")
        validate_demo_plan(self.plan, self.root)
        with self.assertRaisesRegex(ValueError, "frozen sha256"):
            validate_demo_plan(self.plan, self.root, for_execution=True)

    def test_frozen_source_change_is_rejected_before_any_execution(self):
        (self.root / "sample.txt").write_text("Bob")
        browser = Mock()
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            run_web_demo(self.path, self.root / "out", browser_factory=browser)
        browser.assert_not_called()
        self.assertFalse((self.root / "out").exists())

    def test_saved_inputs_cannot_be_missing_changed_or_substituted(self):
        for mode in ("missing", "changed", "source", "other_case"):
            info = {}
            source = self.root / mode
            seal_inputs(self.case, self.root, source, info)
            saved = source / info["input_files"][0]["path"]
            if mode == "missing":
                saved.unlink()
            elif mode == "changed":
                saved.write_text("tampered")
            elif mode == "source":
                info["input_files"][0]["source_sha256"] = "0" * 64
            else:
                info["input_files"][0]["path"] = "cases/other/inputs/sample.txt"
            with self.assertRaises((ValueError, OSError)):
                restore_inputs([self.case], {self.case["id"]: info}, [], source)

    def test_missing_seal_of_an_executed_case_cannot_be_regenerated(self):
        with self.assertRaisesRegex(ValueError, "regeneration is forbidden"):
            restore_inputs([self.case], {}, [{"case_id": self.case["id"], "execution_status": "completed"}], self.root)

    def test_sealing_cannot_fall_back_or_modify_fixed_files(self):
        with self.assertRaisesRegex(ValueError, "fixed upload"):
            seal_inputs(self.case, self.root, self.root / "bad-fixed", {}, contents={"sample.txt": b"changed"})
        self.case["uploads"][0]["vary"] = True
        with self.assertRaisesRegex(ValueError, "fallback is forbidden"):
            seal_inputs(self.case, self.root, self.root / "bad-varied", {})

    def test_input_and_shell_changes_invalidate_evidence_reuse(self):
        from replica_mvp import web_checkpoint
        original = web_checkpoint.evaluator_version()
        digest = web_checkpoint.digest
        for name in ("web_inputs.py", "web_contract.py", "company_app.py"):
            with patch.object(web_checkpoint, "digest", side_effect=lambda p: "changed" if p.name == name else digest(p)):
                self.assertNotEqual(original, web_checkpoint.evaluator_version())

    def test_preapp_interruption_retains_the_sealed_input_for_resume(self):
        first_dir = self.root / "first"
        def interrupt(*args, **kwargs):
            checkpoint = json.loads((first_dir / "checkpoint.json").read_text())
            records = checkpoint["instances"][self.case["id"]]["input_files"]
            self.assertEqual(kwargs["input_files"], records)
            sealed_uploads(self.case, first_dir, records)
            raise RuntimeError("interrupted before app startup")
        with patch("replica_mvp.web_demo._run_case", side_effect=interrupt):
            first = run_web_demo(self.path, first_dir, tester=upload_tester())
        original = (first_dir / "checkpoint.json").read_bytes()
        second = run_web_demo(self.path, self.root / "second", resume_from=first_dir, tester=upload_tester())
        self.assertEqual(1, second["outcome"]["passed"])
        self.assertEqual(first["cases"][0]["instance"]["input_files"], second["cases"][0]["instance"]["input_files"])
        self.assertEqual(original, (first_dir / "checkpoint.json").read_bytes())

    def test_comparison_copies_inputs_but_runs_the_browser_again(self):
        first = run_web_demo(self.path, self.root / "first", tester=upload_tester())
        tester = Mock(side_effect=upload_tester())
        second = run_web_demo(self.path, self.root / "second", tester=tester, input_cases_from=self.root / "first",
                              tester_mode="single")
        self.assertEqual(3, tester.call_count)
        self.assertFalse(second["lineage"]["reused_evidence"])
        self.assertEqual(first["cases"][0]["input_files"], second["cases"][0]["input_files"])
        for directory in ("first", "second"):
            self.assertEqual(b"Alice has 12 items", (self.root / directory / "cases/order/workspace/implementation/result.txt").read_bytes())
