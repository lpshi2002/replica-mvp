import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from replica_mvp.web_demo import _evaluate_case


class VerdictReferencesTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.expectation = {"id": "result", "description": "The requested result is present",
                            "basis": {"type": "our_condition", "source": "fixture"}}
        self.case = {"id": "case", "goal": "Read result", "steps": ["Open result"], "expectations": [self.expectation]}

    def evaluate(self, refs=(), files=(), status="passed", observations=None, precondition_met=None, completed=True):
        (self.root / "result.txt").write_text("result")
        record = {"_trees": ({}, {"result.txt": hashlib.sha256(b"result").hexdigest()}, self.root),
                  "execution_status": "completed" if completed else "action_limit", "stop_reason": None,
                  "events": [{"event_id": "case-001"}], "observations": observations or [],
                  "file_changes": [{"path": "result.txt", "change": "added"}], "final_page": {"text": "result"}}
        verdict = {"id": "result", "status": status, "reason": "observed", "evidence_event_ids": list(refs),
                   "evidence_file_paths": list(files), "precondition_met": precondition_met}
        return _evaluate_case(self.case, record, lambda prompt: ({"verdicts": [verdict]}, None))[0]

    def test_invalid_pass_and_failure_are_unevaluated_with_original_preserved(self):
        for status in ("passed", "failed"):
            result = self.evaluate(["another-case-001"], ["inputs/answer.txt", "missing.txt"], status)
            self.assertEqual("not_evaluated", result["status"])
            self.assertEqual(status, result["raw_judgment"]["status"])
            self.assertEqual(["another-case-001"], result["rejected_references"]["evidence_event_ids"])

    def test_valid_and_invalid_references_are_separated(self):
        result = self.evaluate(["case-001", "foreign"])
        self.assertEqual(("passed", ["case-001"]), (result["status"], result["evidence_event_ids"]))
        self.assertEqual(["foreign"], result["rejected_references"]["evidence_event_ids"])

    def test_observations_without_actions_and_duplicate_ids_keep_order(self):
        observations = [{"event_id": "case-start", "page": {"text": "before"}},
                        {"event_id": "case-start", "page": {"text": "after"}}]
        result = self.evaluate(["case-start"], observations=observations)
        self.assertEqual("passed", result["status"])
        self.assertEqual([1, 2], [o["observation_index"] for o in result["evidence_observations"]])

    def test_actual_output_file_can_be_the_only_evidence(self):
        result = self.evaluate(files=["result.txt"])
        self.assertEqual("passed", result["status"])
        self.assertEqual(hashlib.sha256(b"result").hexdigest(), result["evidence_files"][0]["after_sha256"])

    def test_unreached_or_unknown_precondition_is_not_a_failure(self):
        self.expectation["precondition"] = "The topic reached 100%"
        for value in (False, None):
            result = self.evaluate(["case-001"], status="failed", precondition_met=value)
            self.assertEqual("not_evaluated", result["status"])
        self.assertEqual("failed", self.evaluate(["case-001"], status="failed", precondition_met=True)["status"])

    def test_deterministic_absence_and_unchanged_have_snapshot_evidence(self):
        for kind in ("file_absent", "files_unchanged"):
            self.expectation["check"] = {"type": kind, "path": "absent/*"}
            result = self.evaluate()
            self.assertEqual("passed", result["status"])
            self.assertEqual(["tree_before", "tree_after"], result["evidence"]["snapshots"])
            self.assertEqual("not_evaluated", self.evaluate(completed=False)["status"])
