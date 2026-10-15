"""The judge must receive the observed timeline and complete text outputs.

Model responses are injected; the integration test uses a local browser/app.
"""
import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from replica_mvp.web_demo import _judge_prompt, run_web_demo
from tests.test_web_action_plans import _form, _write_plan
from tests.test_web_demo import HAS_PLAYWRIGHT, _scripted_tester


def _observations(evidence):
    """Reconstruct the page at every observation using the judge's wire contract."""
    page, observations = {}, []
    for item in evidence:
        for key in item.get("removed_page_keys", []):
            del page[key]
        page.update(item["page_changes"])
        observations.append({"event_id": item["event_id"], "page": copy.deepcopy(page)})
    return observations


class JudgeEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.record = {"execution_status": "completed", "stop_reason": None,
                       "events": [], "observations": [], "final_page": None, "file_changes": []}

    def request(self):
        return json.loads(_judge_prompt({"goal": "결과 확인", "steps": ["입력", "결과 확인"]},
                                       [], self.record, self.root, []))

    def test_reappearing_and_disappearing_text_retains_every_observation(self):
        texts = ["처리 중\n처리 중", "완료", "처리 중\n처리 중", "", "오류", "오류\n완료", "완료\n오류"]
        self.record["observations"] = [
            {"event_id": f"event-{i}", "page": {"url": "http://app/", "text": text, "elements": []}}
            for i, text in enumerate(texts)
        ]
        before = copy.deepcopy(self.record)
        evidence = self.request()["screen_evidence"]
        self.assertEqual(before["observations"], _observations(evidence))
        self.assertEqual(before, self.record)

    def test_field_identity_empty_values_navigation_and_transient_evidence_survive(self):
        field = {"ref": 1, "label": "같은 이름", "value": "", "value_length": 0, "checked": False}
        page = {"url": "http://app/", "title": "폼", "text": "값",
                "elements": [field, {**field, "ref": 2, "value": None}]}
        changed = copy.deepcopy(page)
        changed["elements"][0].update(value="가", value_length=1, checked=True)
        changed["signals"] = [{"kind": "alert", "text": "다시 확인"}]
        changed["read_result"] = {"text": "긴 입력 끝", "offset": 4000, "more": False}
        pages = [page, changed, page, {**page, "elements": []},
                 {"url": "http://app/next", "text": "", "elements": []}, changed]
        # A pre-action and post-action observation can share the same event ID.
        self.record["observations"] = [{"event_id": "same-event", "page": p} for p in pages]
        evidence = self.request()["screen_evidence"]
        self.assertEqual(self.record["observations"], _observations(evidence))
        self.assertEqual(len(pages), len({e["observation_index"] for e in evidence}))
        self.assertIn("signals", evidence[2]["removed_page_keys"])
        self.assertIn("read_result", evidence[2]["removed_page_keys"])

    def test_unchanged_pages_keep_their_timing_without_resending_the_body(self):
        page = {"url": "http://app/", "text": "본문" * 2000, "elements": []}
        self.record["observations"] = [{"event_id": str(i), "page": page} for i in range(4)]
        evidence = self.request()["screen_evidence"]
        self.assertEqual(self.record["observations"], _observations(evidence))
        self.assertTrue(all(e["page_changes"] == {} for e in evidence[1:]))
        self.assertLess(len(json.dumps(evidence)), len(json.dumps(self.record["observations"])))

    def test_utf8_and_ascii_outputs_include_the_tail_beyond_the_old_limit(self):
        for text in ("가" * 2000 + "\n최종 판정: 실패 🧪", "x" * 6000 + "\nFAIL at the end"):
            with self.subTest(text=text[-25:]):
                path = self.root / "result.txt"
                path.write_bytes(text.encode("utf-8"))
                original = path.read_bytes()
                self.record["file_changes"] = [{"path": path.name, "change": "modified"}]
                evidence = self.request()["file_changes"][0]
                self.assertEqual("complete", evidence["content_status"])
                self.assertEqual(text, evidence["content"])
                self.assertEqual(original, path.read_bytes())

    def test_empty_file_is_distinct_from_removed_or_unreadable_files(self):
        (self.root / "empty.txt").write_bytes(b"")
        self.record["file_changes"] = [{"path": "empty.txt", "change": "added"},
                                       {"path": "removed.txt", "change": "removed"},
                                       {"path": "missing.txt", "change": "added"}]
        empty, removed, missing = self.request()["file_changes"]
        self.assertEqual(("complete", ""), (empty["content_status"], empty["content"]))
        self.assertEqual("removed", removed["content_status"])
        self.assertIsNone(removed["content"])
        self.assertEqual("unavailable", missing["content_status"])
        self.assertIsNone(missing["content"])
        self.assertIn("FileNotFoundError", missing["content_error"])

    def test_binary_or_invalid_utf8_is_explicitly_unavailable_not_empty(self):
        for data in (b"\xff\xfe\x00data", b"header\x00binary"):
            with self.subTest(data=data):
                (self.root / "output.bin").write_bytes(data)
                self.record["file_changes"] = [{"path": "output.bin", "change": "added"}]
                evidence = self.request()["file_changes"][0]
                self.assertEqual("unavailable", evidence["content_status"])
                self.assertIsNone(evidence["content"])
                self.assertTrue(evidence["content_error"])
                self.assertIn("unavailable", self.request()["instruction"])

    @unittest.skipUnless(HAS_PLAYWRIGHT, "Playwright optional dependency")
    def test_browser_evaluation_delivers_saved_unicode_tail_and_reconstructible_screens(self):
        text = "가" * 2000 + " 마지막 검증 문장 🧪"
        expectation = {"id": "full-output", "description": "입력한 전체 내용을 파일에 저장한다",
                       "basis": {"type": "our_condition", "source": "test"}}
        plan = _write_plan(self.root, _form(), expectations=[expectation])
        value = json.loads(plan.read_text())
        value["cases"][0]["facts"] = [text]
        plan.write_text(json.dumps(value, ensure_ascii=False))
        received = []

        def judge(prompt):
            request = json.loads(prompt)
            received.append(request)
            saved = next(c for c in request["file_changes"] if c["path"].startswith("outbox/"))
            self.assertEqual("complete", saved["content_status"])
            self.assertEqual(text, json.loads(saved["content"])["name"])
            return {"verdicts": [{"id": "full-output", "status": "passed", "reason": "전체 입력 일치",
                                  "evidence_event_ids": [request["events"][-1]["event_id"]]}]}, None

        result = run_web_demo(plan, self.root / "result", judge=judge, tester=_scripted_tester([
            ("fill", "이름", text), ("click", "제출", None), ("done", None, None),
        ]))
        self.assertEqual("passed", result["cases"][0]["expectations"][0]["status"])
        checkpoint = json.loads((self.root / "result/checkpoint.json").read_text())
        self.assertEqual(1, len(received))
        self.assertEqual(checkpoint["cases"][0]["observations"],
                         _observations(received[0]["screen_evidence"]))
