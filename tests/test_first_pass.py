import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from replica_mvp import finalize_first_pass
from replica_mvp.project import FIRST_PASS_SCOPES


def _checkpoint(scope):
    source = f"https://example.com/{scope}"
    return {
        "schema_version": 1,
        "scope": scope,
        "status": "complete",
        "assignment": {
            "company": "Example",
            "official_url": "https://example.com",
            "assigned": [source],
        },
        "progress": {
            "completed": [source],
            "remaining": [],
            "discovered_names": ["Example Engine"],
        },
        "claims": [
            {
                "claim": "Example automates review.",
                "sources": [
                    {
                        "url": source,
                        "type": "official",
                        "excerpt": "Automates document review.",
                    }
                ],
            }
        ],
        "updated_at": "2026-07-25T00:00:00+00:00",
    }


def _research():
    return {
        "schema_version": 1,
        "company": {
            "name": "Example",
            "url": "https://example.com",
            "accessed_at": "2026-07-25",
        },
        "workflow": {
            "status": "pass_1_running",
            "pass_1": {"completed_at": None, "coverage": {}},
            "pass_2": {"selected_count": 0},
        },
        "rubric": {},
        "claims": [
            {
                "id": "claim-001",
                "slug": "automated-review",
                "first_pass": {
                    "claim": "Example automates review.",
                    "sources": [
                        {
                            "url": "https://example.com/product",
                            "type": "official_product",
                            "excerpt": "Automates document review.",
                        }
                    ],
                    "testable_claim": "Given a document, return review findings.",
                    "routing": "도메인워크플로독특",
                    "scores": {
                        "moat": {"value": 1, "reason": "Differentiated workflow."},
                        "business": {"value": 1, "reason": "Customer convenience."},
                        "separability": {"value": 2, "reason": "Bounded input and output."},
                    },
                    "total": 4,
                    "selected": True,
                    "disposition": "second_pass",
                },
                "second_pass": None,
            }
        ],
        "summary": {
            "candidate_count": 0,
            "selected_count": 0,
            "next_step": "run_pass_1",
        },
    }


class FinalizeFirstPassTest(unittest.TestCase):
    def _setup(self, tmp):
        root = Path(tmp) / "example"
        for scope, relative_path in FIRST_PASS_SCOPES.items():
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(_checkpoint(scope), ensure_ascii=False),
                encoding="utf-8",
            )
        research = _research()
        (root / "research.json").write_text(
            json.dumps(research, ensure_ascii=False),
            encoding="utf-8",
        )
        return root, research

    def test_complete_checkpoints_and_scores_finalize_pass_1(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)

            finalized = finalize_first_pass(root)

            self.assertEqual("pass_1_complete", finalized["workflow"]["status"])
            self.assertEqual(5, len(finalized["workflow"]["pass_1"]["coverage"]))
            self.assertEqual(1, finalized["summary"]["candidate_count"])
            self.assertEqual(1, finalized["summary"]["selected_count"])
            self.assertEqual("run_pass_2", finalized["summary"]["next_step"])

    def test_remaining_scope_rejects_without_changing_research(self):
        with TemporaryDirectory() as tmp:
            root, original = self._setup(tmp)
            path = root / FIRST_PASS_SCOPES["engineering_blog"]
            checkpoint = json.loads(path.read_text(encoding="utf-8"))
            checkpoint["progress"]["remaining"] = ["https://example.com/blog/2"]
            path.write_text(json.dumps(checkpoint), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "remaining must be empty"):
                finalize_first_pass(root)

            current = json.loads((root / "research.json").read_text(encoding="utf-8"))
            self.assertEqual(original, current)

    def test_selection_must_match_score(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            research_path = root / "research.json"
            research = json.loads(research_path.read_text(encoding="utf-8"))
            research["claims"][0]["first_pass"]["scores"]["moat"]["value"] = 0
            research["claims"][0]["first_pass"]["total"] = 3
            research_path.write_text(json.dumps(research), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "ranked_not_selected"):
                finalize_first_pass(root)

    def test_replicable_verdict_is_rejected_in_pass_1(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            research_path = root / "research.json"
            research = json.loads(research_path.read_text(encoding="utf-8"))
            research["claims"][0]["first_pass"]["replicable"] = True
            research_path.write_text(json.dumps(research), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "belongs to second_pass"):
                finalize_first_pass(root)


if __name__ == "__main__":
    unittest.main()
