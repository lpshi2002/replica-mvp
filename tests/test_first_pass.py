import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from replica_mvp import finalize_first_pass
from replica_mvp.project import FIRST_PASS_SCOPES

EXCERPT = "Our LLM agent reads submission documents and returns normalized fields."
QUOTE = "Our LLM agent reads submission documents and returns normalized fields."


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
                        "excerpt": EXCERPT,
                    }
                ],
                "ai_basis": {
                    "mechanism": "submission documents → normalized fields",
                    "signals": ["LLM agent"],
                    "source_index": 1,
                    "quote": QUOTE,
                },
                "workflow": {
                    "input": "broker submission email with attachments",
                    "steps": [
                        {"step": "classify each attachment", "source_index": 1},
                        {"step": "extract fields into the target schema", "source_index": 1},
                    ],
                    "output": "normalized submission record",
                },
                "replication_leads": [
                    {
                        "kind": "input_sample",
                        "source_index": 1,
                        "finding": "The source contains a public sample submission.",
                    }
                ],
            }
        ],
        "excluded": [
            {
                "claim": "Cuts review time by 30x.",
                "url": source,
                "reason": "outcome_metric",
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
            "pass_2": {"handoff_count": 0},
        },
        "claim_filter": {},
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
                            "excerpt": EXCERPT,
                        }
                    ],
                    "ai_basis": {
                        "mechanism": "submission documents → normalized fields",
                        "signals": ["LLM agent"],
                        "source_index": 1,
                        "quote": QUOTE,
                    },
                    "workflow": {
                        "input": "broker submission email with attachments",
                        "steps": [
                            {"step": "classify each attachment", "source_index": 1},
                            {"step": "extract fields into the target schema", "source_index": 1},
                        ],
                        "output": "normalized submission record",
                    },
                    "replication_leads": [
                        {
                            "kind": "output_example",
                            "source_index": 1,
                            "finding": "The source shows normalized output fields.",
                        }
                    ],
                    "testable_claim": "Given a document, return review findings.",
                    "routing": "도메인워크플로독특",
                    "merged_from": ["Cuts review time by 30x."],
                },
                "second_pass": None,
            }
        ],
        "summary": {
            "candidate_count": 0,
            "excluded_count": 0,
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

    def _rewrite_claim(self, root, mutate):
        research_path = root / "research.json"
        research = json.loads(research_path.read_text(encoding="utf-8"))
        mutate(research["claims"][0]["first_pass"])
        research_path.write_text(json.dumps(research, ensure_ascii=False), encoding="utf-8")

    def test_qualified_claims_finalize_pass_1(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)

            finalized = finalize_first_pass(root)

            self.assertEqual("pass_1_complete", finalized["workflow"]["status"])
            self.assertEqual(5, len(finalized["workflow"]["pass_1"]["coverage"]))
            self.assertEqual(1, finalized["summary"]["candidate_count"])
            self.assertEqual(5, finalized["summary"]["excluded_count"])
            self.assertEqual(1, finalized["workflow"]["pass_2"]["handoff_count"])
            self.assertEqual("run_pass_2", finalized["summary"]["next_step"])
            self.assertNotIn("selected_count", finalized["summary"])

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

    def test_claim_without_ai_basis_is_rejected(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            self._rewrite_claim(root, lambda first: first.pop("ai_basis"))

            with self.assertRaisesRegex(ValueError, "ai_basis must be an object"):
                finalize_first_pass(root)

    def test_quote_missing_its_signal_is_rejected(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            self._rewrite_claim(
                root,
                lambda first: first["ai_basis"].__setitem__("signals", ["fine-tuned model"]),
            )

            with self.assertRaisesRegex(ValueError, "must contain the signal"):
                finalize_first_pass(root)

    def test_quote_absent_from_cited_source_is_rejected(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            self._rewrite_claim(
                root,
                lambda first: first["ai_basis"].__setitem__(
                    "quote", "Our LLM agent underwrites policies end to end."
                ),
            )

            with self.assertRaisesRegex(ValueError, "must appear in the excerpt"):
                finalize_first_pass(root)

    def test_source_index_out_of_range_is_rejected(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            self._rewrite_claim(root, lambda first: first["ai_basis"].__setitem__("source_index", 2))

            with self.assertRaisesRegex(ValueError, "1-based index into sources"):
                finalize_first_pass(root)

    def test_claim_without_workflow_is_rejected(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            self._rewrite_claim(root, lambda first: first.pop("workflow"))

            with self.assertRaisesRegex(ValueError, "workflow must be an object"):
                finalize_first_pass(root)

    def test_workflow_step_without_source_is_rejected(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            self._rewrite_claim(
                root,
                lambda first: first["workflow"]["steps"][1].pop("source_index"),
            )

            with self.assertRaisesRegex(ValueError, r"steps 2.source_index"):
                finalize_first_pass(root)

    def test_workflow_without_documented_steps_is_allowed(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            self._rewrite_claim(root, lambda first: first["workflow"].__setitem__("steps", []))

            self.assertEqual(1, finalize_first_pass(root)["summary"]["candidate_count"])

    def test_replication_leads_are_required_in_checkpoints_and_final_claims(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            path = root / FIRST_PASS_SCOPES["official_surfaces"]
            checkpoint = json.loads(path.read_text(encoding="utf-8"))
            checkpoint["claims"][0].pop("replication_leads")
            path.write_text(json.dumps(checkpoint, ensure_ascii=False), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "replication_leads must be a list"):
                finalize_first_pass(root)

        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            self._rewrite_claim(root, lambda first: first.pop("replication_leads"))

            with self.assertRaisesRegex(ValueError, "replication_leads must be a list"):
                finalize_first_pass(root)

    def test_replication_lead_source_index_out_of_range_is_rejected(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            self._rewrite_claim(
                root,
                lambda first: first["replication_leads"][0].__setitem__("source_index", 2),
            )

            with self.assertRaisesRegex(ValueError, "1-based index into sources"):
                finalize_first_pass(root)

    def test_claim_without_replication_leads_is_allowed_when_list_is_empty(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            self._rewrite_claim(root, lambda first: first.__setitem__("replication_leads", []))

            self.assertEqual(1, finalize_first_pass(root)["summary"]["candidate_count"])

    def test_retired_score_fields_are_rejected(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            self._rewrite_claim(root, lambda first: first.__setitem__("total", 4))

            with self.assertRaisesRegex(ValueError, "total is retired"):
                finalize_first_pass(root)

        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            path = root / FIRST_PASS_SCOPES["official_surfaces"]
            checkpoint = json.loads(path.read_text(encoding="utf-8"))
            checkpoint["claims"][0]["selected"] = True
            path.write_text(json.dumps(checkpoint, ensure_ascii=False), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "selected is retired"):
                finalize_first_pass(root)

    def test_unknown_exclusion_reason_is_rejected(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            path = root / FIRST_PASS_SCOPES["official_surfaces"]
            checkpoint = json.loads(path.read_text(encoding="utf-8"))
            checkpoint["excluded"][0]["reason"] = "not_interesting"
            path.write_text(json.dumps(checkpoint, ensure_ascii=False), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "reason must be one of"):
                finalize_first_pass(root)

    def test_replicable_verdict_is_rejected_in_pass_1(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            self._rewrite_claim(root, lambda first: first.__setitem__("replicable", True))

            with self.assertRaisesRegex(ValueError, "belongs to second_pass"):
                finalize_first_pass(root)


if __name__ == "__main__":
    unittest.main()
