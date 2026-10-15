import json
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from replica_mvp.agent_harness import _demo_scope, finish_agent_harness
from replica_mvp.bundle_evaluation import evaluate_agent_bundle
from replica_mvp.web_contract import verification_scope
from replica_mvp.web_demo import web_reproduction_status
from tests.test_web_evaluation import _bind_web_app, _web_research, APPROVE, _passing_review
from tests.test_web_demo import _passing_judge, _scripted_tester, _write_cli


class VerificationScopeTest(unittest.TestCase):
    def setUp(self):
        self.scope = {"steps": [{"step_index": 1, "step": "answer", "disposition": "implemented",
                                 "verification_parts": [{"id": "microphone", "description": "Live capture",
                                    "reason": "This trial only uploads a clip", "development_evidence": [
                                        {"source": "dev.json", "method": "code check", "result": "present"}]}]}],
                      "excluded_steps": [], "out_of_scope": ["A separate billing product"]}
        self.cases = [{"case_id": "typed", "expectations": [{"id": "answer", "status": "passed", "covers_steps": [1]}]}]

    def verdict(self, scope):
        return web_reproduction_status({"outcome": {"passed": 1, "failed": 0, "not_evaluated": 0,
                     "cases_completed": 1, "cases_total": 1}, "cases": [{"execution_status": "completed"}],
                     "scope": scope, "code_review": {"status": "passed"}})

    def test_a_passing_step_does_not_verify_its_untested_input_mode(self):
        scope = verification_scope(self.scope, self.cases)
        self.assertEqual([], scope["uncovered_steps"])
        self.assertEqual("microphone", scope["unverified_parts"][0]["id"])
        self.assertEqual("partially_reproduced", self.verdict(scope))
        self.assertEqual("code check", scope["unverified_parts"][0]["development_evidence"][0]["method"])

    def test_only_mapped_actual_expectations_verify_a_part(self):
        self.cases[0]["expectations"][0]["covers_parts"] = [{"step_index": 1, "part_id": "microphone"}]
        scope = verification_scope(self.scope, self.cases)
        self.assertEqual([], scope["unverified_parts"])
        self.assertEqual("reproduced", self.verdict(scope))  # unrelated out_of_scope is not a failure
        self.cases[0]["expectations"][0]["status"] = "not_evaluated"
        self.assertTrue(verification_scope(self.scope, self.cases)["uncovered_steps"])

    def test_unmapped_step_prevents_full_reproduction(self):
        self.scope["steps"].append({"step_index": 2, "step": "save", "disposition": "implemented"})
        scope = verification_scope(self.scope, self.cases)
        self.assertEqual([2], [s["step_index"] for s in scope["uncovered_steps"]])
        self.assertEqual("partially_reproduced", self.verdict(scope))

    def test_new_rule_does_not_relabel_historical_results_on_read(self):
        result = {"outcome": {"passed": 1, "failed": 0, "not_evaluated": 0, "cases_completed": 1, "cases_total": 1},
                  "cases": [{"execution_status": "completed"}], "scope": {"uncovered_steps": [{"step_index": 2}]},
                  "code_review": {"status": "passed"}}
        self.assertEqual("reproduced", web_reproduction_status(result, legacy=True))
        self.assertEqual("partially_reproduced", web_reproduction_status(result))

    def test_company_json_preserves_untested_parts_and_other_scope(self):
        import os
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _write_cli(root / "real")
            research = _web_research()
            scenario = research["claims"][0]["second_pass"]["replication_contract"][1]
            scenario["step_coverage"][0]["verification_parts"] = deepcopy(self.scope["steps"][0]["verification_parts"])
            scenario["out_of_scope"] = self.scope["out_of_scope"]
            with patch.dict(os.environ, {"PATH": f"{root / 'real'}{os.pathsep}{os.environ['PATH']}"}):
                registry = _bind_web_app(root / "run", research)
                evaluate_agent_bundle(registry, "claim-001", tester=_scripted_tester(APPROVE), judge=_passing_judge,
                                      reviewer=_passing_review)
                finished = finish_agent_harness(registry)
            company = json.loads((root / "run" / finished["company_result"]["path"]).read_text())
            claim = company["claims"][0]
            self.assertEqual("partially_reproduced", claim["reproduction_status"])
            self.assertEqual(self.scope["out_of_scope"], claim["out_of_scope"])
            self.assertEqual("microphone", claim["web_demo"]["scope"]["unverified_parts"][0]["id"])
