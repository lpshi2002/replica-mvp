import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from replica_mvp import finalize_first_pass
from replica_mvp.project import FIRST_PASS_SCOPES

EXCERPT = "Underwriters use Example Review, whose LLM agent reads submission documents and returns normalized fields."
QUOTE = EXCERPT


def _checkpoint(scope):
    source = f"https://example.com/{scope}"
    return {
        "schema_version": 2,
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
                "id": f"{scope}-claim-001",
                "claim": "Example automates review.",
                "sources": [
                    {
                        "url": source,
                        "type": "official",
                        "excerpt": EXCERPT,
                    }
                ],
                "customer_basis": {
                    "delivery": "public_product",
                    "subject": "Example Review",
                    "audience": "underwriters",
                    "source_index": 1,
                    "quote": QUOTE,
                },
                "ai_basis": {
                    "mechanism": "submission documents → normalized fields",
                    "signals": ["LLM agent"],
                    "work_signals": ["reads submission documents", "returns normalized fields"],
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
        "deferred": [],
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
        "schema_version": 2,
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
                    "customer_basis": {
                        "delivery": "public_product",
                        "subject": "Example Review",
                        "audience": "underwriters",
                        "source_index": 1,
                        "quote": QUOTE,
                    },
                    "ai_basis": {
                        "mechanism": "submission documents → normalized fields",
                        "signals": ["LLM agent"],
                        "work_signals": ["reads submission documents", "returns normalized fields"],
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
        "candidate_resolutions": [
            {
                "candidate_id": f"{scope}-claim-001",
                "decision": "kept_as_claim" if scope == "official_surfaces" else "merged_into_claim",
                "target_id": "claim-001",
                "rationale": "Same customer goal, input, and deliverable as claim-001.",
            }
            for scope in FIRST_PASS_SCOPES
        ],
        "deferred_resolutions": [],
        "summary": {
            "candidate_count": 0,
            "excluded_count": 0,
            "deferred_count": 0,
            "resolved_deferred_count": 0,
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

    def _rewrite_research(self, root, mutate):
        research_path = root / "research.json"
        research = json.loads(research_path.read_text(encoding="utf-8"))
        mutate(research)
        research_path.write_text(json.dumps(research, ensure_ascii=False), encoding="utf-8")

    def test_qualified_claims_finalize_pass_1(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)

            finalized = finalize_first_pass(root)

            self.assertEqual("pass_1_complete", finalized["workflow"]["status"])
            self.assertEqual(5, len(finalized["workflow"]["pass_1"]["coverage"]))
            self.assertEqual(1, finalized["summary"]["candidate_count"])
            self.assertEqual(5, finalized["summary"]["excluded_count"])
            self.assertEqual(0, finalized["summary"]["deferred_count"])
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

    def test_dropped_candidate_blocks_finalize(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)

            def drop(research):
                research["claims"] = []
                research["candidate_resolutions"] = []

            self._rewrite_research(root, drop)

            with self.assertRaisesRegex(ValueError, "candidate item '.*-claim-001' is unresolved"):
                finalize_first_pass(root)

    def test_candidates_can_be_excluded_with_rationale(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)

            def exclude_all(research):
                research["claims"] = []
                for resolution in research["candidate_resolutions"]:
                    resolution.update(decision="excluded", target_id=None, rationale="Only internal use was documented.")

            self._rewrite_research(root, exclude_all)

            finalized = finalize_first_pass(root)
            self.assertEqual(10, finalized["summary"]["excluded_count"])
            self.assertEqual("no_ai_claims", finalized["summary"]["next_step"])

    def test_excluded_candidate_needs_rationale(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)

            def exclude(research):
                research["candidate_resolutions"][1].update(decision="excluded", target_id=None, rationale="")

            self._rewrite_research(root, exclude)

            with self.assertRaisesRegex(ValueError, "rationale must be filled"):
                finalize_first_pass(root)

    def test_final_claim_must_trace_to_a_candidate(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)

            def orphan(research):
                for resolution in research["candidate_resolutions"]:
                    resolution.update(decision="excluded", target_id=None, rationale="Duplicate marketing copy.")

            self._rewrite_research(root, orphan)

            with self.assertRaisesRegex(ValueError, "not traced to any checkpoint candidate"):
                finalize_first_pass(root)

    def test_attached_deferred_evidence_does_not_originate_a_claim(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            path = root / FIRST_PASS_SCOPES["official_surfaces"]
            checkpoint = json.loads(path.read_text(encoding="utf-8"))
            checkpoint["deferred"].append(
                {
                    "id": "official_surfaces-deferred-001",
                    "claim": "One stage",
                    "url": "https://example.com/blog",
                    "excerpt": "The review workflow classifies attachments.",
                    "reason": "not_workflow",
                }
            )
            path.write_text(json.dumps(checkpoint, ensure_ascii=False), encoding="utf-8")

            def attach_only(research):
                for resolution in research["candidate_resolutions"]:
                    resolution.update(decision="excluded", target_id=None, rationale="Duplicate marketing copy.")
                research["deferred_resolutions"].append(
                    {
                        "deferred_id": "official_surfaces-deferred-001",
                        "decision": "attached_to_claim",
                        "target_id": "claim-001",
                        "rationale": "A stage of the review workflow.",
                    }
                )

            self._rewrite_research(root, attach_only)

            with self.assertRaisesRegex(ValueError, "not traced to any checkpoint candidate"):
                finalize_first_pass(root)

    def test_unperformed_assignment_blocks_finalize(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            path = root / FIRST_PASS_SCOPES["engineering_blog"]
            checkpoint = json.loads(path.read_text(encoding="utf-8"))
            checkpoint["assignment"]["assigned"].append("https://example.com/blog/2")
            path.write_text(json.dumps(checkpoint), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "neither completed nor skipped"):
                finalize_first_pass(root)

            checkpoint["progress"]["skipped"] = [{"item": "https://example.com/blog/2", "reason": ""}]
            path.write_text(json.dumps(checkpoint), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "skipped 1 needs item and reason"):
                finalize_first_pass(root)

            checkpoint["progress"]["skipped"] = [{"item": "https://example.com/blog/2", "reason": "HTTP 404"}]
            path.write_text(json.dumps(checkpoint), encoding="utf-8")
            finalize_first_pass(root)

    def test_finalize_refuses_research_past_pass_1(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            self._rewrite_research(root, lambda research: research["workflow"].update(status="pass_2_complete"))
            before = (root / "research.json").read_text(encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "before pass 2 starts"):
                finalize_first_pass(root)
            self.assertEqual(before, (root / "research.json").read_text(encoding="utf-8"))

    def test_finalize_is_repeatable_during_pass_1(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            finalize_first_pass(root)
            self.assertEqual("pass_1_complete", finalize_first_pass(root)["workflow"]["status"])

    def test_claim_without_ai_basis_is_rejected(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            self._rewrite_claim(root, lambda first: first.pop("ai_basis"))

            with self.assertRaisesRegex(ValueError, "ai_basis must be an object"):
                finalize_first_pass(root)

    def test_claim_without_customer_basis_is_rejected(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            self._rewrite_claim(root, lambda first: first.pop("customer_basis"))

            with self.assertRaisesRegex(ValueError, "customer_basis must be an object"):
                finalize_first_pass(root)

    def test_customer_basis_must_name_its_attributed_subject(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            self._rewrite_claim(
                root,
                lambda first: first["customer_basis"].__setitem__("subject", "Different Product"),
            )

            with self.assertRaisesRegex(ValueError, "must contain the attributed subject"):
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
                    "quote", "Our LLM agent reads submission documents and returns normalized fields for policies end to end."
                ),
            )

            with self.assertRaisesRegex(ValueError, "must appear in the excerpt"):
                finalize_first_pass(root)

    def test_promotional_ai_sentence_cannot_be_stitched_to_work_sentence(self):
        stitched = "Example Review is powered by an LLM agent. It reads submission documents and returns normalized fields."
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)

            def mutate(first):
                first["sources"][0]["excerpt"] = stitched
                first["customer_basis"]["quote"] = stitched
                first["ai_basis"].update(
                    {
                        "quote": stitched,
                        "signals": ["LLM agent"],
                        "work_signals": ["reads submission documents"],
                    }
                )

            self._rewrite_claim(root, mutate)
            with self.assertRaisesRegex(ValueError, "directly connect the AI and claimed work"):
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

    def test_internal_workflow_exclusion_reason_is_allowed(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            path = root / FIRST_PASS_SCOPES["official_surfaces"]
            checkpoint = json.loads(path.read_text(encoding="utf-8"))
            checkpoint["excluded"][0]["reason"] = "internal_workflow"
            path.write_text(json.dumps(checkpoint, ensure_ascii=False), encoding="utf-8")

            self.assertEqual(1, finalize_first_pass(root)["summary"]["candidate_count"])

    def test_deferred_item_blocks_finalize_until_controller_resolves_it(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            path = root / FIRST_PASS_SCOPES["official_surfaces"]
            checkpoint = json.loads(path.read_text(encoding="utf-8"))
            checkpoint["deferred"].append(
                {
                    "id": "official_surfaces-deferred-001",
                    "claim": "Potential customer workflow",
                    "url": "https://example.com/blog",
                    "excerpt": "An agent could review submissions.",
                    "reason": "no_customer_delivery",
                }
            )
            path.write_text(json.dumps(checkpoint, ensure_ascii=False), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "is unresolved"):
                finalize_first_pass(root)

    def test_controller_can_resolve_each_deferred_reason(self):
        for reason in ("no_company_attribution", "no_customer_delivery", "not_workflow"):
            with self.subTest(reason=reason), TemporaryDirectory() as tmp:
                root, _ = self._setup(tmp)
                path = root / FIRST_PASS_SCOPES["official_surfaces"]
                checkpoint = json.loads(path.read_text(encoding="utf-8"))
                deferred_id = f"official_surfaces-deferred-{reason}"
                checkpoint["deferred"].append(
                    {
                        "id": deferred_id,
                        "claim": "Potential workflow",
                        "url": "https://example.com/blog",
                        "excerpt": "Potential supporting text.",
                        "reason": reason,
                    }
                )
                path.write_text(json.dumps(checkpoint, ensure_ascii=False), encoding="utf-8")
                self._rewrite_research(
                    root,
                    lambda research: research["deferred_resolutions"].append(
                        {
                            "deferred_id": deferred_id,
                            "decision": "excluded",
                            "target_id": None,
                            "rationale": "All scopes were checked and no qualifying customer workflow was found.",
                        }
                    ),
                )

                finalized = finalize_first_pass(root)
                self.assertEqual(1, finalized["summary"]["deferred_count"])
                self.assertEqual(1, finalized["summary"]["resolved_deferred_count"])
                self.assertEqual(6, finalized["summary"]["excluded_count"])

    def test_controller_can_attach_deferred_evidence_to_parent_claim(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            path = root / FIRST_PASS_SCOPES["official_surfaces"]
            checkpoint = json.loads(path.read_text(encoding="utf-8"))
            checkpoint["deferred"].append(
                {
                    "id": "official_surfaces-deferred-001",
                    "claim": "One documented stage of the review workflow",
                    "url": "https://example.com/blog",
                    "excerpt": "The review workflow classifies attachments.",
                    "reason": "not_workflow",
                }
            )
            path.write_text(json.dumps(checkpoint, ensure_ascii=False), encoding="utf-8")
            self._rewrite_research(
                root,
                lambda research: research["deferred_resolutions"].append(
                    {
                        "deferred_id": "official_surfaces-deferred-001",
                        "decision": "attached_to_claim",
                        "target_id": "claim-001",
                        "rationale": "This is a stage of the existing end-to-end review claim.",
                    }
                ),
            )

            finalized = finalize_first_pass(root)
            self.assertEqual(1, finalized["summary"]["candidate_count"])
            self.assertEqual(5, finalized["summary"]["excluded_count"])

    def test_checkpoint_chain_hints_are_rejected(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            path = root / FIRST_PASS_SCOPES["official_surfaces"]
            checkpoint = json.loads(path.read_text(encoding="utf-8"))
            checkpoint["chain_hints"] = []
            path.write_text(json.dumps(checkpoint, ensure_ascii=False), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "chain_hints is retired"):
                finalize_first_pass(root)

    def test_research_chains_are_rejected(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            self._rewrite_research(root, lambda research: research.__setitem__("chains", []))

            with self.assertRaisesRegex(ValueError, "chains is retired"):
                finalize_first_pass(root)

    def test_whole_workflow_steps_remain_one_claim(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)

            finalized = finalize_first_pass(root)
            workflow = finalized["claims"][0]["first_pass"]["workflow"]
            self.assertEqual(1, finalized["summary"]["candidate_count"])
            self.assertEqual(2, len(workflow["steps"]))
            self.assertEqual(1, finalized["workflow"]["pass_2"]["handoff_count"])

    def test_replicable_verdict_is_rejected_in_pass_1(self):
        with TemporaryDirectory() as tmp:
            root, _ = self._setup(tmp)
            self._rewrite_claim(root, lambda first: first.__setitem__("replicable", True))

            with self.assertRaisesRegex(ValueError, "belongs to second_pass"):
                finalize_first_pass(root)


if __name__ == "__main__":
    unittest.main()
