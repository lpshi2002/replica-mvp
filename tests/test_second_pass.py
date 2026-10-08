import json
import unittest
from pathlib import Path

from replica_mvp import parse_second_pass


REPOSITORY_ROOT = Path(__file__).parents[1]
LEGACY_EXAMPLE = REPOSITORY_ROOT / "examples" / "second-pass-lead-qualification.json"


def _legacy_claim():
    return json.loads(LEGACY_EXAMPLE.read_text(encoding="utf-8"))


SOURCE = {
    "url": "https://example.com/docs",
    "type": "official_docs",
    "excerpt": "Example answers questions from supplied documents with citations.",
}


def _case(name, kind, value):
    return {
        "id": name,
        "kind": kind,
        "input": {"x": value},
        "deterministic_assertions": [{"type": "equals", "path": ["value"], "value": value * 2}],
        "semantic_criteria": [],
        "criterion_ids": ["criterion-001"],
    }


def _evaluation():
    novel = _case("unseen", "novel", 18)
    novel["novelty"] = {
        "difference": "A new supplied numeric range with independent input data.",
        "development_inputs": [{"x": 7, "unrelated": ["sample"]}],
    }
    # This is a plumbing test fixture, not evidence of generalization for a company claim.
    invariant = _case("invariant", "metamorphic", 1)
    invariant["input"]["unrelated"] = ["different", "ordering"]
    invariant["metamorphic"] = {
        "case_id": "normal", "relation": "equal", "path": ["value"], "reason": "Ignore unrelated metadata.",
    }
    changed = _case("changed", "metamorphic", 8)
    changed["metamorphic"] = {
        "case_id": "normal", "relation": "different", "path": ["value"],
        "reason": "Changed facts must change the result.",
    }
    return {
        "runtime": {"transport": "stdio_json"},
        "timeout_seconds": 2,
        "repeat_policy": "contract",
        "additional_cases": [novel, invariant, changed],
        "public_examples": [{"input": {"x": 100}, "description": "A separate public demonstration."}],
    }


def _research():
    """A complete pass-2 research record whose selected scenario is ready to evaluate."""
    scenario = {
        "id": "s-commercial",
        "self_sufficiency": "commercial_api",
        "boundaries": "Text only.",
        "input": "A UTF-8 document and question.",
        "output": "A cited JSON answer.",
        "evidence_level": "public",
        "acceptance_criteria": ["Double the supplied value; arbitrary wording may vary."],
        "sources": [SOURCE],
        "step_coverage": [
            {"step_index": 1, "disposition": "implemented"},
            {"step_index": 2, "disposition": "implemented"},
        ],
        "tests": [
            _case("normal", "normal", 1),
            _case("boundary", "boundary", -2),
            _case("insufficient", "insufficient_information", 0),
        ],
    }
    oss = json.loads(json.dumps(scenario))
    oss.update({"id": "s-oss", "self_sufficiency": "oss_only", "evaluation": _evaluation()})
    findings = {
        bucket: {"state": "unknown", "note": "Looked; nothing public.", "sources": []}
        for bucket in (
            "evidence", "datasets_apis", "oss_papers_patents", "eval_assets", "access_license", "impl_path",
        )
    }
    findings["impl_path"] = {"state": "filled", "note": "Use a local retriever.", "sources": [SOURCE]}
    findings["datasets_apis"] = {"state": "filled", "note": "Use public text.", "sources": [SOURCE]}
    second_pass = {
        "claim_id": "claim-001",
        "status": "confirmed",
        "workflow": {
            "input": "document",
            "steps": [],
            "output": "answer",
            "boundaries": {"state": "stated", "value": "Text only.", "sources": [SOURCE]},
        },
        "findings": findings,
        "readiness": {"status": "ready"},
        "handoff": {"action": "build", "selected_scenario_id": "s-oss", "selection_reason": "Local retrieval was selected by second-pass research."},
        "replication_contract": [scenario, oss],
    }
    first_pass = {
        "claim": "Answers from supplied documents.",
        "workflow": {
            "input": "document",
            "steps": [
                {"step": "retrieve passages", "source_index": 1},
                {"step": "answer with citations", "source_index": 1},
            ],
            "output": "answer",
        },
    }
    return {
        "schema_version": 2,
        "company": {"name": "Example", "url": "https://example.com"},
        "workflow": {
            "status": "pass_2_complete",
            "pass_1": {"completed_at": "2026-09-24T00:00:00+00:00"},
        },
        "claims": [
            {
                "id": "claim-001",
                "first_pass": first_pass,
                "second_pass": second_pass,
            },
            {
                "id": "claim-002",
                "first_pass": {"claim": "Not ready.", "workflow": first_pass["workflow"]},
                "second_pass": {
                    **second_pass,
                    "claim_id": "claim-002",
                    "readiness": {"status": "partial"},
                },
            },
        ],
        "summary": {"ready_count": 1, "partial_count": 1, "blocked_count": 0},
    }


class SecondPassParserTest(unittest.TestCase):
    def test_company_research_preserves_the_full_ready_claim_for_sol(self):
        research = _research()

        parsed = parse_second_pass(research)

        self.assertEqual(1, parsed["claim_count"])
        claim = parsed["claims"][0]
        payload = claim["payload"]
        self.assertEqual("claim-001", claim["claim_id"])
        self.assertEqual("replica-agent-claim/v2", payload["schema_version"])
        self.assertEqual("s-oss", payload["selected_scenario_id"])
        self.assertEqual(
            research["claims"][0]["second_pass"],
            payload["second_pass"],
        )
        self.assertEqual(
            "Use a local retriever.",
            payload["second_pass"]["findings"]["impl_path"]["note"],
        )
        self.assertEqual(
            [{"id": "criterion-001", "description": "Double the supplied value; arbitrary wording may vary."}],
            payload["acceptance_criteria"],
        )

    def test_model_runtime_does_not_replace_the_self_sufficient_scenario(self):
        parsed = parse_second_pass(_research(), model_runtime="claude")

        payload = parsed["claims"][0]["payload"]
        self.assertEqual("s-oss", payload["selected_scenario_id"])
        self.assertEqual(
            {"provider": "claude", "transport": "local_cli"},
            payload["model_runtime"],
        )

    def test_unknown_model_runtime_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "model runtime"):
            parse_second_pass(_research(), model_runtime="other")

    def test_researched_order_and_explicit_priority_do_not_prefer_cheaper_dependencies(self):
        research = _research()
        handoff = research["claims"][0]["second_pass"]["handoff"]
        del handoff["selected_scenario_id"]
        payload = parse_second_pass(research)["claims"][0]["payload"]
        self.assertEqual("s-commercial", payload["selected_scenario_id"])
        self.assertEqual("research_order", payload["scenario_selection"]["basis"])
        handoff["scenario_priority"] = ["s-commercial", "s-oss"]
        self.assertEqual("s-commercial", parse_second_pass(research)["claims"][0]["payload"]["selected_scenario_id"])
        handoff["selected_scenario_id"] = "s-oss"
        with self.assertRaisesRegex(ValueError, "conflicting"):
            parse_second_pass(research)

    def _selected(self, research):
        return research["claims"][0]["second_pass"]["replication_contract"][1]

    def test_every_researched_step_needs_a_scenario_disposition(self):
        research = _research()
        self._selected(research)["step_coverage"].pop()
        with self.assertRaisesRegex(ValueError, r"RESEARCH_INCOMPLETE: claim-001: workflow steps without step_coverage: claim-001#2"):
            parse_second_pass(research)

    def test_unconfirmed_step_blocks_implementation(self):
        research = _research()
        self._selected(research)["step_coverage"][0]["disposition"] = "unconfirmed"
        with self.assertRaisesRegex(ValueError, "step claim-001#1 is unconfirmed: retrieve passages"):
            parse_second_pass(research)

    def test_excluded_step_makes_the_contract_a_partial_workflow(self):
        research = _research()
        self._selected(research)["step_coverage"][0] = {"step_index": 1, "disposition": "excluded"}
        with self.assertRaisesRegex(ValueError, "excluded step claim-001#1 needs a reason"):
            parse_second_pass(research)
        self._selected(research)["step_coverage"][0]["reason"] = "Retrieval is supplied by the caller."
        # Leaving a step out needs the routes that were checked and what building it would take.
        with self.assertRaisesRegex(ValueError, "excluded step claim-001#1 needs alternatives"):
            parse_second_pass(research)
        self._selected(research)["step_coverage"][0]["alternatives"] = [
            {"candidate": "rank_bm25 over the policy corpus", "reason": "No public policy corpus was found."}]
        with self.assertRaisesRegex(ValueError, "needs `needs`"):
            parse_second_pass(research)
        self._selected(research)["step_coverage"][0]["needs"] = "A licensed policy corpus."
        coverage = parse_second_pass(research)["claims"][0]["payload"]["workflow_coverage"]
        self.assertEqual("partial_workflow", coverage["scope"])
        self.assertEqual("retrieve passages", coverage["excluded_steps"][0]["step"])
        self.assertEqual("A licensed policy corpus.", coverage["excluded_steps"][0]["needs"])

    def test_excluded_part_of_an_implemented_step_makes_the_contract_partial(self):
        research = _research()
        self._selected(research)["step_coverage"][0]["excluded_parts"] = [
            {"part": "audio and video sources", "reason": "No transcription route was chosen."}]
        with self.assertRaisesRegex(ValueError, "excluded part of step claim-001#1 needs alternatives"):
            parse_second_pass(research)
        self._selected(research)["step_coverage"][0]["excluded_parts"][0].update(
            alternatives=[{"candidate": "openai-whisper", "reason": "Not checked against the time budget."}],
            needs="A local speech-to-text model and audio fixtures.")
        coverage = parse_second_pass(research)["claims"][0]["payload"]["workflow_coverage"]
        self.assertEqual("partial_workflow", coverage["scope"])
        self.assertEqual(("audio and video sources", 1),
                         (coverage["excluded_parts"][0]["part"], coverage["excluded_parts"][0]["step_index"]))

    def test_step_component_records_where_it_comes_from(self):
        research = _research()
        entry = self._selected(research)["step_coverage"][0]
        entry["component"] = {"description": "keyword retrieval", "origin": "guess"}
        with self.assertRaisesRegex(ValueError, "component needs a description and an origin"):
            parse_second_pass(research)
        entry["component"] = {"description": "keyword retrieval", "origin": "company_stated"}
        with self.assertRaisesRegex(ValueError, "stated by the company needs sources"):
            parse_second_pass(research)
        entry["component"]["origin"] = "inferred"
        parse_second_pass(research)

    def test_web_claim_does_not_need_json_tests(self):
        research = _research()
        selected = self._selected(research)
        del selected["tests"]
        with self.assertRaisesRegex(ValueError, "tests must be a list"):
            parse_second_pass(research)
        selected["demo_plan"] = {"title": "demo"}
        self.assertEqual(1, len(parse_second_pass(research)["claims"]))

    def test_research_must_complete_both_passes_before_implementation(self):
        research = _research()
        research["workflow"]["status"] = "pass_1_complete"
        with self.assertRaisesRegex(ValueError, "RESEARCH_INCOMPLETE: research must pass finalize-pass-1"):
            parse_second_pass(research)

    def test_summary_counts_must_match_claim_readiness(self):
        research = _research()
        research["summary"]["ready_count"] = 2
        with self.assertRaisesRegex(ValueError, "ready_count is 2 but claims record 1"):
            parse_second_pass(research)

    def test_required_scenario_tests_and_explicit_kinds(self):
        research = _research()
        self._selected(research)["tests"].pop()
        with self.assertRaisesRegex(ValueError, "lacks insufficient_information tests"):
            parse_second_pass(research)
        research = _research()
        del self._selected(research)["tests"][2]["kind"]
        with self.assertRaisesRegex(ValueError, "needs an input and a kind"):
            parse_second_pass(research)

    def test_sources_without_excerpts_are_not_evidence(self):
        research = _research()
        research["claims"][0]["second_pass"]["findings"]["impl_path"]["sources"] = [
            {"url": "https://example.com", "type": "official", "excerpt": ""}
        ]
        with self.assertRaisesRegex(ValueError, "finding impl_path must be closed"):
            parse_second_pass(research)

    def test_open_findings_and_unchecked_boundaries_block_ready(self):
        research = _research()
        del research["claims"][0]["second_pass"]["findings"]["eval_assets"]
        with self.assertRaisesRegex(ValueError, "finding eval_assets"):
            parse_second_pass(research)
        research = _research()
        research["claims"][0]["second_pass"]["workflow"]["boundaries"]["state"] = "unchecked"
        with self.assertRaisesRegex(ValueError, "boundaries.state"):
            parse_second_pass(research)

    def test_changed_fragment_verdict_needs_a_recorded_revision(self):
        import tempfile

        research = _research()
        second_pass = research["claims"][0]["second_pass"]
        second_pass["run"] = {"fragment": "second_pass/claim-001.json"}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "second_pass").mkdir()
            original = {
                "claim_id": "claim-001",
                "readiness": {"status": "partial"},
                "handoff": {"action": "evidence_request"},
            }
            (root / "second_pass" / "claim-001.json").write_text(json.dumps(original))
            claim_002 = research["claims"][1]["second_pass"]
            claim_002["run"] = {"fragment": "second_pass/claim-002.json"}
            (root / "second_pass" / "claim-002.json").write_text(json.dumps(claim_002))
            with self.assertRaisesRegex(ValueError, "without a revision that records the original verdict"):
                parse_second_pass(research, fragment_root=root)
            revision = {
                "previous": {"readiness": "partial", "handoff": "evidence_request"},
                "reason": "The compiler schema was published.",
                "revised_at": "2026-09-24T00:00:00+00:00",
                "sources": [{"url": "https://example.com/schema", "excerpt": ""}],
            }
            second_pass["revisions"] = [revision]
            with self.assertRaisesRegex(ValueError, "revisions entry needs"):
                parse_second_pass(research, fragment_root=root)
            revision["sources"][0]["excerpt"] = "The action schema is documented here."
            self.assertEqual(1, parse_second_pass(research, fragment_root=root)["claim_count"])

    def test_claim_without_a_pass_2_verdict_blocks_implementation(self):
        research = _research()
        research["claims"][1]["second_pass"] = None
        research["summary"]["partial_count"] = 0
        with self.assertRaisesRegex(ValueError, "RESEARCH_INCOMPLETE: claim-002: every pass-1 claim needs a pass-2"):
            parse_second_pass(research)

    def test_missing_fragment_cannot_verify_the_verdict(self):
        import tempfile

        research = _research()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "claim-001: the pass-2 fragment .* is missing"):
                parse_second_pass(research, fragment_root=root)
            (root / "second_pass").mkdir()
            for claim in research["claims"]:
                name = f"second_pass/{claim['id']}.json"
                claim["second_pass"]["run"] = {"fragment": name}
                (root / name).write_text(json.dumps(claim["second_pass"]))
            self.assertEqual(1, parse_second_pass(research, fragment_root=root)["claim_count"])
            research["claims"][0]["second_pass"]["run"]["fragment"] = "../outside.json"
            (root.parent / "outside.json").write_text("{}")
            try:
                with self.assertRaisesRegex(ValueError, "is missing"):
                    parse_second_pass(research, fragment_root=root)
            finally:
                (root.parent / "outside.json").unlink()

    def test_fragment_of_another_claim_cannot_verify_the_verdict(self):
        import tempfile

        research = _research()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "second_pass").mkdir()
            for claim in research["claims"]:
                claim["second_pass"]["run"] = {"fragment": f"second_pass/{claim['id']}.json"}
                (root / "second_pass" / f"{claim['id']}.json").write_text(json.dumps(claim["second_pass"]))
            research["claims"][0]["second_pass"]["run"]["fragment"] = "second_pass/claim-002.json"
            with self.assertRaisesRegex(ValueError, "claim-001: .* records claim_id 'claim-002'"):
                parse_second_pass(research, fragment_root=root)

    def test_step_added_in_pass_2_must_be_mapped_before_whole_workflow(self):
        research = _research()
        workflow = research["claims"][0]["second_pass"]["workflow"]
        workflow["steps"] = [
            {"step": "retrieve passages", "first_pass_step": 1},
            {"step": "answer with citations", "first_pass_step": 2},
            {"step": "store answers for later lookup"},
        ]
        with self.assertRaisesRegex(ValueError, "pass-2 step 3 is not a pass-1 step"):
            parse_second_pass(research)
        workflow["steps"][2]["sources"] = [SOURCE]
        with self.assertRaisesRegex(ValueError, "workflow steps without step_coverage: claim-001#3"):
            parse_second_pass(research)
        self._selected(research)["step_coverage"].append(
            {"step_index": 3, "disposition": "excluded", "reason": "Storage is left to the caller.",
             "alternatives": [{"candidate": "SQLite", "reason": "The public scenario hands storage to the caller."}],
             "needs": "A storage layer the caller can query."}
        )
        coverage = parse_second_pass(research)["claims"][0]["payload"]["workflow_coverage"]
        self.assertEqual("partial_workflow", coverage["scope"])
        self.assertEqual("store answers for later lookup", coverage["excluded_steps"][0]["step"])
        self.assertEqual("second_pass", coverage["workflows"][0]["basis"])
        self.assertEqual([{"step_index": 3, "step": "store answers for later lookup"}],
                         coverage["workflows"][0]["added_steps"])

    def test_pass_2_cannot_drop_a_pass_1_step_silently(self):
        research = _research()
        workflow = research["claims"][0]["second_pass"]["workflow"]
        # Identical text keeps a pass-1 step without naming its index.
        workflow["steps"] = [{"step": "answer with citations"}]
        self._selected(research)["step_coverage"].pop()
        with self.assertRaisesRegex(ValueError, "drops pass-1 steps without workflow.removed_steps: claim-001#1"):
            parse_second_pass(research)
        workflow["removed_steps"] = [{"first_pass_step": 1, "reason": "Retrieval is part of answering.", "sources": [SOURCE]}]
        coverage = parse_second_pass(research)["claims"][0]["payload"]["workflow_coverage"]
        self.assertEqual("whole_workflow", coverage["scope"])
        self.assertEqual("retrieve passages", coverage["workflows"][0]["removed_steps"][0]["step"])

    def test_empty_workflow_is_not_whole_workflow_scope(self):
        research = _research()
        research["claims"][0]["first_pass"]["workflow"]["steps"] = []
        self._selected(research)["step_coverage"] = []
        with self.assertRaisesRegex(ValueError, "confirmed workflow has no steps"):
            parse_second_pass(research)

    def test_every_researched_claim_is_listed_with_its_execution_reason(self):
        parsed = parse_second_pass(_research())
        self.assertEqual(1, parsed["claim_count"])
        self.assertEqual(
            [("claim-001", True, None),
             ("claim-002", False, "pass-2 research confirmed, readiness partial, handoff build")],
            [(c["claim_id"], c["selected_for_execution"], c["not_executed_reason"]) for c in parsed["company_claims"]],
        )
        research = _research()
        research["claims"][0]["second_pass"]["readiness"] = {"status": "blocked", "reasons": "No public input."}
        research["summary"].update(ready_count=0, blocked_count=1)
        parsed = parse_second_pass(research)
        self.assertEqual(0, parsed["claim_count"])
        self.assertEqual("No public input.", parsed["company_claims"][0]["readiness_reasons"])

    def test_merged_claim_steps_move_to_the_parent_contract(self):
        research = _research()
        child = research["claims"][1]
        child["second_pass"] = {
            "claim_id": "claim-002",
            "status": "merged",
            "readiness": {"status": "partial"},
            "handoff": {"action": "merge"},
            "replication_contract": None,
        }
        research["summary"].update(partial_count=1)
        with self.assertRaisesRegex(ValueError, "merged claim needs merged_into"):
            parse_second_pass(research)
        child["second_pass"]["merged_into"] = "claim-001"
        with self.assertRaisesRegex(ValueError, "claim-002#1, claim-002#2"):
            parse_second_pass(research)
        self._selected(research)["step_coverage"] += [
            {"claim_id": "claim-002", "step_index": 1, "disposition": "implemented"},
            {"claim_id": "claim-002", "step_index": 2, "disposition": "implemented"},
        ]
        payload = parse_second_pass(research)["claims"][0]["payload"]
        self.assertEqual(["claim-002"], [item["claim_id"] for item in payload["absorbed_claims"]])

    def test_legacy_single_claim_normalizes_to_canonical_collection(self):
        claim = _legacy_claim()

        parsed = parse_second_pass(claim)

        self.assertEqual("replica-claim-collection/v1", parsed["schema_version"])
        self.assertEqual(1, parsed["claim_count"])
        self.assertEqual(
            [
                {
                    "claim_id": claim["replica_id"],
                    "payload": claim,
                }
            ],
            parsed["claims"],
        )

    def test_multiple_claims_normalize_without_mixing_payloads(self):
        first = _legacy_claim()
        second = _legacy_claim()
        second["replica_id"] = "growth-labs-seat-guidance"
        second["capability"] = "recommend a seat band from supplied team size"
        second["canonical_claim"] = "Recommend a seat band without enrichment."
        source = {
            "schema_version": "replica-second-pass-claim-collection/v1",
            "claims": [first, second],
        }

        parsed = parse_second_pass(source)

        self.assertEqual(2, parsed["claim_count"])
        self.assertEqual(
            ["growth-labs-lead-qualification", "growth-labs-seat-guidance"],
            [claim["claim_id"] for claim in parsed["claims"]],
        )
        self.assertEqual(
            [first["canonical_claim"], second["canonical_claim"]],
            [claim["payload"]["canonical_claim"] for claim in parsed["claims"]],
        )

    def test_invalid_claim_is_rejected(self):
        claim = _legacy_claim()
        del claim["canonical_claim"]

        with self.assertRaisesRegex(
            ValueError,
            "invalid second-pass result contract",
        ):
            parse_second_pass(
                {
                    "schema_version": "replica-second-pass-claim-collection/v1",
                    "claims": [claim],
                }
            )

    def test_legacy_claim_without_implementation_remains_supported(self):
        claim = _legacy_claim()
        del claim["implementation"]

        parsed = parse_second_pass(claim)

        self.assertEqual(claim, parsed["claims"][0]["payload"])

    def test_unsupported_claim_type_and_unsafe_identity_are_rejected(self):
        unsafe_claim = _legacy_claim()
        unsafe_claim["replica_id"] = "../claim-001"
        invalid_claims = ("not-an-object", unsafe_claim)

        for claim in invalid_claims:
            with self.subTest(claim=claim):
                with self.assertRaisesRegex(
                    ValueError,
                    "invalid second-pass result contract",
                ):
                    parse_second_pass(
                        {
                            "schema_version": (
                                "replica-second-pass-claim-collection/v1"
                            ),
                            "claims": [claim],
                        }
                    )

    def test_duplicate_claim_identity_is_rejected(self):
        claim = _legacy_claim()

        with self.assertRaisesRegex(
            ValueError,
            "duplicate claim identity: growth-labs-lead-qualification",
        ):
            parse_second_pass(
                {
                    "schema_version": "replica-second-pass-claim-collection/v1",
                    "claims": [claim, claim],
                }
            )

    def test_n_input_claims_produce_n_stable_claim_identities(self):
        claims = []
        for index in range(1, 8):
            claim = _legacy_claim()
            claim["replica_id"] = f"growth-labs-claim-{index:03d}"
            claims.append(claim)
        source = {
            "schema_version": "replica-second-pass-claim-collection/v1",
            "claims": claims,
        }

        first_parse = parse_second_pass(source)
        second_parse = parse_second_pass(source)

        expected_ids = [claim["replica_id"] for claim in claims]
        self.assertEqual(len(claims), first_parse["claim_count"])
        self.assertEqual(
            expected_ids,
            [claim["claim_id"] for claim in first_parse["claims"]],
        )
        self.assertEqual(first_parse, second_parse)

    def test_invalid_claim_collection_is_rejected_fail_closed(self):
        invalid_values = (
            [],
            {"schema_version": "replica-second-pass-claim-collection/v1"},
            {
                "schema_version": "replica-second-pass-claim-collection/v1",
                "claims": [],
            },
            {
                "schema_version": "replica-second-pass-claim-collection/v1",
                "claims": [_legacy_claim()],
                "unexpected": True,
            },
            {
                "schema_version": "replica-second-pass-claim-collection/v1",
                "claims": "not-a-list",
            },
        )

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    ValueError,
                    "invalid second-pass claim collection",
                ):
                    parse_second_pass(value)

    def test_claim_payloads_are_isolated_and_source_input_is_not_mutated(self):
        shared_scope = ["shared source value"]
        first = _legacy_claim()
        second = _legacy_claim()
        second["replica_id"] = "growth-labs-seat-guidance"
        first["supported_scope"] = shared_scope
        second["supported_scope"] = shared_scope
        source = {
            "schema_version": "replica-second-pass-claim-collection/v1",
            "claims": [first, second],
        }

        parsed = parse_second_pass(source)
        parsed["claims"][0]["payload"]["supported_scope"].append(
            "first claim only"
        )

        self.assertEqual(["shared source value"], first["supported_scope"])
        self.assertEqual(["shared source value"], second["supported_scope"])
        self.assertEqual(
            ["shared source value"],
            parsed["claims"][1]["payload"]["supported_scope"],
        )


if __name__ == "__main__":
    unittest.main()
