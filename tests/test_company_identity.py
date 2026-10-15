import hashlib
import json
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from replica_mvp.company_app import company_app_session, company_features
from tests.test_company_app import _mounted_app


class CompanyIdentityTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.manifest = _mounted_app(self.root / "feature")
        (self.root / "plan.json").write_text(json.dumps({"title": "Feature"}))
        self.claim = {"claim_id": "claim-001", "status": "IMPLEMENTATION_READY",
                      "implementation_result": {"candidate_path": "feature/manifest.json",
                          "candidate_sha256": hashlib.sha256(self.manifest.read_bytes()).hexdigest()},
                      "web_demo": {"plan_path": "plan.json"}}

    def selected(self, claims=None):
        return company_features({"claims": claims or [self.claim]}, self.root, self.root / "state")

    def test_valid_partial_or_unevaluated_features_remain_usable(self):
        for status in ("IMPLEMENTATION_READY", "RESULT_FAILED", "EVALUATION_INTERRUPTED"):
            self.claim["status"] = status
            features, excluded = self.selected()
            self.assertEqual(1, len(features))
            self.assertEqual([], excluded)

    def test_changing_both_files_and_manifest_cannot_bypass_with_fresh_state(self):
        app = self.manifest.parent / "app.py"
        app.write_text(app.read_text() + "\n# changed\n")
        manifest = json.loads(self.manifest.read_text())
        manifest["files"][0]["sha256"] = hashlib.sha256(app.read_bytes()).hexdigest()
        self.manifest.write_text(json.dumps(manifest))
        features, excluded = self.selected()
        self.assertEqual([], features)
        self.assertIn("hash mismatch", excluded[0]["reason"])
        self.assertFalse((self.root / "state").exists())

    def test_source_file_change_is_caught_before_any_server_starts(self):
        (self.manifest.parent / "app.py").write_text("changed")
        features, excluded = self.selected()
        self.assertEqual([], features)
        self.assertIn("bundle file hash mismatch", excluded[0]["reason"])

    def test_invalid_feature_does_not_hide_a_valid_one(self):
        invalid = deepcopy(self.claim)
        invalid["claim_id"] = "claim-002"
        invalid["implementation_result"]["candidate_sha256"] = "wrong"
        features, excluded = self.selected([invalid, self.claim])
        self.assertEqual(["claim-001"], [f["id"] for f in features])
        self.assertEqual(["claim-002"], [f["claim_id"] for f in excluded])

    def test_selection_and_startup_are_bound_to_the_same_manifest(self):
        features, _ = self.selected()
        self.manifest.write_text("{}")
        with self.assertRaisesRegex(ValueError, "changed before startup"):
            with company_app_session("company", features, 1):
                self.fail("altered manifest was served")
