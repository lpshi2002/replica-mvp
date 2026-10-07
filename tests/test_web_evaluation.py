import hashlib
import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from replica_mvp.agent_harness import (
    finalize_agent_candidate, finish_agent_continuity, finish_agent_harness,
    prepare_agent_harness, record_agent_continuity_round, start_agent_continuity,
)
from replica_mvp.bundle_evaluation import evaluate_agent_bundle, retry_agent_bundle
from replica_mvp.session_usage import agent_usage
from replica_mvp.single_agent import bind_single_implementation, prepare_single_harness, start_single_implementation
from replica_mvp.web_demo import freeze_demo_plan
from tests.test_agent_continuity import _prepare_rich_ready_pair, _write_execution_state
from tests.test_second_pass import _research
from tests.test_web_demo import APP, _passing_judge, _scripted_tester, _write_cli


DEMO_PLAN = {
    "title": "승인 워크플로", "case_design": "prospective", "case_author": "pass-2 research worker",
    "budget": {"time_limit_seconds": 120, "max_actions_per_case": 8, "model_call_timeout_seconds": 30},
    "cases": [{
        "id": "approve", "goal": "요청을 등록하고 승인한다",
        "steps": ["요청 내용에 '노트북 구매'를 입력하고 등록한다", "등록된 요청을 승인한다"],
        "facts": ["요청 내용은 '노트북 구매'"], "targeted_barrier": None, "barrier_note": "공개 장벽 주장 미확인",
        "covers_steps": [1], "variation": None, "variation_note": "fixture",
        "expectations": [
            {"id": "outbox", "description": "승인하면 outbox에 기록된다",
             "basis": {"type": "public_rule", "source": "https://example.com/docs"},
             "check": {"type": "file_contains", "path": "outbox/*.json", "text": "노트북 구매"}},
            {"id": "summary", "description": "요약이 화면에 보인다",
             "basis": {"type": "public_rule", "source": "https://example.com/docs"}},
        ],
    }],
}
APPROVE = [("fill", "요청 내용", "노트북 구매"), ("click", "등록", None), ("click", "승인", None), ("done", None, None)]


def _passing_review(prompt):
    request = json.loads(prompt)
    assert "app.py" in request["files"] and request["research"]["workflow_steps"]
    return {"status": "passed", "reason": "Handles any request text; saves to outbox on approval.", "findings": []}, None


def _web_research(plan=None, sessions=None):
    research = _research()
    research["claims"][0]["second_pass"]["replication_contract"][1]["demo_plan"] = json.loads(
        json.dumps(plan or DEMO_PLAN, ensure_ascii=False))
    if sessions:
        research["agent_sessions"] = sessions
    return research


def _bind_web_app(root: Path, research=None, *, runtime=True, app=APP) -> Path:
    """Drive one pair to IMPLEMENTATION_READY with a web-app candidate, as the harness tests do for JSON."""
    with patch("tests.test_agent_continuity._research", return_value=research or _web_research()):
        registry, binding = _prepare_rich_ready_pair(root)
    claim_id = binding["claim_id"]
    start_agent_continuity(registry, claim_id, operator_agent_id=binding["operator_agent_id"],
                           builder_agent_id=binding["builder_agent_id"], nonce=binding["nonce"])
    record_agent_continuity_round(registry, claim_id, round_number=0, operator_agent_id=binding["operator_agent_id"],
                                  builder_agent_id=binding["builder_agent_id"], nonce=binding["nonce"],
                                  operator_to_builder_direct=True, builder_to_operator_direct=True)
    candidate = f"claims/{claim_id}/builder/implementation/manifest.json"
    state = _write_execution_state(registry, binding, terminal_state="SUCCESS", correction_count=0,
                                   candidate_path=candidate)
    finish_agent_continuity(registry, claim_id, terminal_state="SUCCESS", execution_state_path=state,
                            operator_agent_id=binding["operator_agent_id"], builder_agent_id=binding["builder_agent_id"],
                            nonce=binding["nonce"], terminal_acknowledged_directly=True)
    manifest_path = root / candidate
    manifest_path.parent.mkdir()
    (manifest_path.parent / "app.py").write_text(app)
    claim = json.loads((root / f"claims/{claim_id}/claim.json").read_text())
    manifest = {
        "schema_version": "replica-implementation-bundle/v1", "claim_id": claim_id, "scenario_id": "s-oss",
        "implementation_type": "hybrid", "dependency_level": "oss_only", "input_contract": claim["input_contract"],
        "output_contract": claim["output_contract"], "entrypoint": "app.py", "command": [sys.executable, "app.py"],
        "dependencies": [], "environment_variables": [],
        "files": [{"path": "app.py", "sha256": hashlib.sha256(app.encode()).hexdigest()}],
    }
    if runtime:
        manifest["runtime"] = {"transport": "web_app", "port_argument": "--port", "ready_path": "/"}
    manifest_path.write_text(json.dumps(manifest))
    finalize_agent_candidate(registry, claim_id, manifest_path)
    return registry


class WebHarnessTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        _write_cli(self.root / "real")
        # Session logs are read from these roots; keep them inside the test.
        self.env = patch.dict(os.environ, {
            "PATH": f"{self.root / 'real'}{os.pathsep}{os.environ['PATH']}",
            "CLAUDE_CONFIG_DIR": str(self.root / "claude-home"), "CODEX_HOME": str(self.root / "codex-home"),
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.directory.cleanup()

    def test_demo_plan_is_frozen_public_and_replaces_the_sealed_suite(self):
        registry = prepare_agent_harness(_web_research(), self.root / "run", replica_agent_id="/root/r",
                                         parent_agent_id="/root")
        claim = registry["claims"][0]
        self.assertEqual("PENDING", claim["status"])
        self.assertNotIn("bundle_evaluation", claim)
        plan_path = self.root / "run" / claim["web_demo"]["plan_path"]
        plan = json.loads(plan_path.read_text())
        self.assertEqual(("replica-web-demo-plan/v1", "claim-001"), (plan["schema_version"], plan["claim_id"]))
        self.assertEqual(hashlib.sha256(plan_path.read_bytes()).hexdigest(), claim["web_demo"]["plan_sha256"])
        context = json.loads((self.root / "run" / claim["builder_context_path"]).read_text())
        self.assertEqual("web_app", context["interface"]["kind"])
        self.assertEqual(claim["web_demo"]["plan_path"], context["interface"]["demo_plan_path"])
        self.assertIn("demo_plan", context["selected_scenario"])
        from replica_mvp.bundle_evaluation import prepare_bundle_evaluation
        with self.assertRaisesRegex(ValueError, "frozen public demo plan"):
            prepare_bundle_evaluation(self.root / "run" / "agent-harness.json", "claim-001")

    def test_plan_without_basis_or_missing_upload_is_a_research_gap(self):
        plan = json.loads(json.dumps(DEMO_PLAN))
        del plan["cases"][0]["expectations"][0]["basis"]
        registry = prepare_agent_harness(_web_research(plan), self.root / "a", replica_agent_id="/root/r",
                                         parent_agent_id="/root")
        self.assertEqual("RESEARCH_INCOMPLETE", registry["claims"][0]["status"])
        self.assertIn("basis", registry["claims"][0]["research_gaps"][0])
        plan = json.loads(json.dumps(DEMO_PLAN))
        plan["cases"][0]["uploads"] = [{"path": "inputs/order.pdf"}]
        registry = prepare_agent_harness(_web_research(plan), self.root / "b", replica_agent_id="/root/r",
                                         parent_agent_id="/root")
        self.assertIn("research directory", registry["claims"][0]["research_gaps"][0])
        # With the research directory, upload files are copied next to the frozen plan.
        (self.root / "research" / "inputs").mkdir(parents=True)
        (self.root / "research" / "inputs" / "order.pdf").write_bytes(b"%PDF")
        frozen = freeze_demo_plan(plan, "claim-001", self.root / "research", self.root / "c" / "demo")
        self.assertEqual(b"%PDF", (frozen.parent / "inputs" / "order.pdf").read_bytes())

    def test_web_claim_requires_a_web_app_manifest(self):
        with self.assertRaisesRegex(ValueError, "web_app runtime"):
            _bind_web_app(self.root / "run", runtime=False)

    def test_final_evaluation_runs_the_demo_and_company_result_carries_it(self):
        sessions_dir = self.root / "claude-home" / "projects" / "p"
        sessions_dir.mkdir(parents=True)
        line = {"type": "assistant", "timestamp": "2026-10-06T00:00:00Z",
                "message": {"id": "m1", "model": "claude-opus-5-5", "usage": {"input_tokens": 3, "output_tokens": 9}}}
        # The same message on two lines is counted once.
        (sessions_dir / "research-worker-1.jsonl").write_text(json.dumps(line) + "\n" + json.dumps(line) + "\n")
        research = _web_research(sessions=[{"role": "pass_2_worker", "agent_id": "research-worker-1", "runtime": "claude",
                                            "claim_id": "claim-001"},
                                           {"role": "pass_1_worker", "agent_id": "never-logged"}])
        registry = _bind_web_app(self.root / "run", research)
        evaluated = evaluate_agent_bundle(registry, "claim-001", tester=_scripted_tester(APPROVE), judge=_passing_judge,
                                          reviewer=_passing_review,
                                          semantic_judge=lambda request: {"pass": False, "reason": "unused"})
        claim = evaluated["claims"][0]
        self.assertEqual(("RESULT_SUCCESS", "reproduced"), (claim["status"], claim["final_result"]["reproduction_status"]))
        self.assertEqual("web_demo", claim["bundle_submissions"][0]["mode"])
        public = self.root / "run" / claim["final_result"]["public_run_dir"]
        self.assertTrue(public.is_relative_to(self.root / "run" / "final-results" / "runs"))
        self.assertTrue((public / "report.md").is_file())
        self.assertFalse((self.root / "run" / "evaluator-vault" / "claim-001" / "plan-001").exists())
        finished = finish_agent_harness(registry)
        company = json.loads((self.root / "run" / finished["company_result"]["path"]).read_text())
        entry = company["claims"][0]
        self.assertEqual(("reproduced", "s-oss"), (entry["outcome"], entry["scenario_id"]))
        self.assertEqual({"passed": 2, "failed": 0, "not_evaluated": 0, "cases_completed": 1, "cases_total": 1},
                         entry["web_demo"]["outcome"])
        self.assertEqual(1, entry["web_demo"]["costs"]["replica_runtime"]["calls"])
        self.assertEqual("passed", entry["web_demo"]["code_review"]["status"])
        # The case passes through step 1 only, so step 2 is reported as unverified, not hidden.
        self.assertEqual([2], [step["step_index"] for step in entry["web_demo"]["uncovered_steps"]])
        self.assertEqual({"operator", "builder"}, set(entry["development_usage"]))
        self.assertEqual(1, entry["development_usage"]["operator"]["unknown"])
        research_usage = company["research_usage"]
        self.assertEqual({"input_tokens": 3, "output_tokens": 9}, research_usage["pass_2_worker"]["usage"])
        self.assertEqual((0, 1), (research_usage["pass_1_worker"]["measured"], research_usage["pass_1_worker"]["unknown"]))

    def test_code_review_finding_keeps_a_passing_demo_from_counting_as_reproduced(self):
        registry = _bind_web_app(self.root / "run")

        def finding(prompt):
            return {"status": "failed", "reason": "Answers only the plan's literal request.",
                    "findings": [{"kind": "case_specific_branch", "detail": "if text == '노트북 구매'", "file": "app.py"}]}, None
        evaluated = evaluate_agent_bundle(registry, "claim-001", tester=_scripted_tester(APPROVE), judge=_passing_judge,
                                          reviewer=finding)
        claim = evaluated["claims"][0]
        self.assertEqual("partially_reproduced", claim["final_result"]["reproduction_status"])
        report = (self.root / "run" / claim["final_result"]["public_run_dir"] / "report.md").read_text()
        self.assertIn("case_specific_branch", report)

    def _varied_plan(self):
        plan = json.loads(json.dumps(DEMO_PLAN))
        plan["cases"][0]["variation"] = {"instruction": "다른 사무용품 이름으로 바꾼다"}
        del plan["cases"][0]["variation_note"]
        return plan

    @staticmethod
    def _chair(prompt):
        return {"goal": "요청을 등록하고 승인한다", "steps": ["요청 내용에 '의자 구매'를 입력하고 등록한다", "등록된 요청을 승인한다"],
                "facts": ["요청 내용은 '의자 구매'"], "replacements": [{"from": "노트북 구매", "to": "의자 구매"}]}, "instance-call"

    def test_cases_run_once_with_values_drawn_at_run_time(self):
        registry = _bind_web_app(self.root / "run", _web_research(self._varied_plan()))
        seen = []

        def generator(prompt):
            seen.append(json.loads(prompt))
            return self._chair(prompt)
        # The tester only ever sees the drawn values; the public example is never run.
        chair = [("fill", "요청 내용", "의자 구매"), ("click", "등록", None), ("click", "승인", None), ("done", None, None)]
        evaluated = evaluate_agent_bundle(registry, "claim-001", tester=_scripted_tester(chair), judge=_passing_judge,
                                          reviewer=_passing_review, instance_generator=generator)
        claim = evaluated["claims"][0]
        self.assertEqual("reproduced", claim["final_result"]["reproduction_status"])
        self.assertEqual(["노트북 구매"], seen[0]["check_texts"])
        self.assertNotIn("expectations", seen[0]["case"])
        result = json.loads((self.root / "run" / claim["final_result"]["public_run_dir"] / "demo-result.json").read_text())
        self.assertEqual(1, result["outcome"]["cases_total"])
        case = result["cases"][0]
        self.assertEqual(("drawn_at_run", ["요청 내용은 '의자 구매'"]), (case["instance"]["values"], case["instance"]["facts"]))
        self.assertIn("의자 구매", case["expectations"][0]["reason"])

    def test_replica_fitted_to_the_public_example_fails_on_drawn_values(self):
        fitted = APP.replace('if item["state"] == "approved":', 'if item["state"] == "approved" and item["text"] == "노트북 구매":')
        registry = _bind_web_app(self.root / "run", _web_research(self._varied_plan()), app=fitted)
        chair = [("fill", "요청 내용", "의자 구매"), ("click", "등록", None), ("click", "승인", None), ("done", None, None)]
        evaluated = evaluate_agent_bundle(registry, "claim-001", tester=_scripted_tester(chair), judge=_passing_judge,
                                          reviewer=_passing_review, instance_generator=self._chair)
        claim = evaluated["claims"][0]
        self.assertNotEqual("reproduced", claim["final_result"]["reproduction_status"])
        retry_agent_bundle(registry, "claim-001")
        feedback = json.loads((self.root / "run" / "claims/claim-001/operator/retry-feedback-001.json").read_text())
        outbox = feedback["cases"][0]["expectations"][0]
        self.assertEqual(("failed", "승인하면 outbox에 기록된다"), (outbox["status"], outbox["description"]))
        self.assertNotIn("instance", feedback["cases"][0])

    def test_failed_instance_generation_does_not_fall_back_to_the_example(self):
        def broken(prompt):
            raise RuntimeError("generator down")
        registry = _bind_web_app(self.root / "run", _web_research(self._varied_plan()))
        evaluated = evaluate_agent_bundle(registry, "claim-001", tester=_scripted_tester([]), judge=_passing_judge,
                                          reviewer=_passing_review, instance_generator=broken)
        claim = evaluated["claims"][0]
        self.assertEqual("execution_blocked", claim["final_result"]["reproduction_status"])
        result = json.loads((self.root / "run" / claim["final_result"]["public_run_dir"] / "demo-result.json").read_text())
        case = result["cases"][0]
        self.assertEqual("blocked", case["execution_status"])
        self.assertIn("instance generation failed", case["stop_reason"])
        self.assertEqual({"not_evaluated"}, {e["status"] for e in case["expectations"]})

    def test_covers_steps_outside_the_workflow_is_a_research_gap(self):
        plan = json.loads(json.dumps(DEMO_PLAN))
        plan["cases"][0]["covers_steps"] = [9]
        registry = prepare_agent_harness(_web_research(plan), self.root / "run", replica_agent_id="/root/r",
                                         parent_agent_id="/root")
        self.assertIn("covers_steps", registry["claims"][0]["research_gaps"][0])

    def test_unevaluated_demo_is_not_reported_as_a_failure_and_can_be_retried(self):
        registry = _bind_web_app(self.root / "run")

        def broken_judge(prompt):
            raise RuntimeError("judge unavailable")
        evaluated = evaluate_agent_bundle(registry, "claim-001", tester=_scripted_tester(APPROVE), judge=broken_judge)
        claim = evaluated["claims"][0]
        self.assertEqual("partially_reproduced", claim["final_result"]["reproduction_status"])
        self.assertEqual("RESULT_FAILED", claim["status"])
        reopened = retry_agent_bundle(registry, "claim-001")
        self.assertEqual("READY_FOR_PROTOCOL", reopened["claims"][0]["status"])
        feedback = json.loads((self.root / "run" / "claims/claim-001/operator/retry-feedback-001.json").read_text())
        reasons = {item["id"]: (item["status"], item["reason"]) for item in feedback["cases"][0]["expectations"]}
        self.assertEqual("not_evaluated", reasons["summary"][0])
        self.assertIn("judge unavailable", reasons["summary"][1])
        # Reasons only: no screenshots, page text or action records go back to the implementer.
        self.assertNotIn("screens", json.dumps(feedback))
        self.assertNotIn("final_page", feedback["cases"][0])

    def test_blocked_browser_reports_execution_blocked(self):
        registry = _bind_web_app(self.root / "run")

        def no_browser():
            raise RuntimeError("no browser")
        evaluated = evaluate_agent_bundle(registry, "claim-001", tester=_scripted_tester([]), judge=_passing_judge,
                                          browser_factory=no_browser)
        self.assertEqual("execution_blocked", evaluated["claims"][0]["final_result"]["reproduction_status"])
        company = json.loads((self.root / "run" / finish_agent_harness(registry)["company_result"]["path"]).read_text())
        self.assertEqual("experiment_blocked", company["claims"][0]["outcome"])


class SingleWebRouteTest(unittest.TestCase):
    def test_single_implementer_builds_web_app_and_its_session_cost_is_measured(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _write_cli(root / "real")
            plan = json.loads(json.dumps(DEMO_PLAN))
            plan["cases"][0]["uploads"] = [{"path": "inputs/order.txt"}]
            research = _web_research(plan)
            (root / "second_pass").mkdir()
            (root / "inputs").mkdir()
            (root / "inputs" / "order.txt").write_text("노트북 1대")
            for claim in research["claims"]:
                claim["second_pass"]["handoff"]["experiment_budget"] = {
                    "time_limit_seconds": 7200, "cost_limit": None, "stop_on_blocked": True}
                claim["second_pass"]["run"] = {"fragment": f"second_pass/{claim['id']}.json"}
                (root / claim["second_pass"]["run"]["fragment"]).write_text(json.dumps(claim["second_pass"]))
            (root / "research.json").write_text(json.dumps(research, ensure_ascii=False))
            rollout = root / "codex-home" / "sessions" / "2026" / "10" / "06" / "rollout-2026-10-06T00-00-00-real-child.jsonl"
            rollout.parent.mkdir(parents=True)
            rollout.write_text(json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {
                "total_token_usage": {"input_tokens": 1200, "output_tokens": 300}}}}))
            with patch.dict(os.environ, {"PATH": f"{root / 'real'}{os.pathsep}{os.environ['PATH']}",
                                         "CLAUDE_CONFIG_DIR": str(root / "claude-home"),
                                         "CODEX_HOME": str(root / "codex-home")}):
                registry = prepare_single_harness(root / "research.json", root / "run", orchestrator_id="root")
                path = root / "run" / "agent-harness.json"
                claim = registry["claims"][0]
                self.assertNotIn("bundle_evaluation", claim)
                plan_dir = (path.parent / claim["web_demo"]["plan_path"]).parent
                self.assertEqual("노트북 1대", (plan_dir / "inputs" / "order.txt").read_text())
                start_single_implementation(path, "claim-001", agent_id="real-child", model="gpt-6-astra",
                                            reasoning_effort="low")
                workspace = path.parent / "claims/claim-001/implementer"
                (workspace / "implementation").mkdir()
                (workspace / "implementation" / "app.py").write_text(APP)
                public = json.loads((workspace.parent / "claim.json").read_text())
                (workspace / "implementation" / "manifest.json").write_text(json.dumps({
                    "schema_version": "replica-implementation-bundle/v1", "claim_id": "claim-001", "scenario_id": "s-oss",
                    "implementation_type": "hybrid", "dependency_level": "oss_only",
                    "input_contract": public["input_contract"], "output_contract": public["output_contract"],
                    "entrypoint": "app.py", "command": [sys.executable, "app.py"], "dependencies": [],
                    "environment_variables": [],
                    "files": [{"path": "app.py", "sha256": hashlib.sha256(APP.encode()).hexdigest()}],
                    "runtime": {"transport": "web_app", "port_argument": "--port", "ready_path": "/"},
                }))
                (workspace / "development.json").write_text(json.dumps({"status": "passed", "checks": [
                    {"command": "browser self-check fixture", "exit_code": 0}]}))
                (workspace / "development-log.jsonl").write_text(
                    json.dumps({"attempt": 1, "changed": "first build", "failed": "approve button missing"}) + "\n"
                    + json.dumps({"attempt": 2, "changed": "added approve form", "failed": None}) + "\n")
                bind_single_implementation(path, "claim-001", agent_id="real-child")
                evaluated = evaluate_agent_bundle(path, "claim-001", tester=_scripted_tester(APPROVE),
                                                  judge=_passing_judge, reviewer=_passing_review)
                self.assertEqual("RESULT_SUCCESS", evaluated["claims"][0]["status"])
                company = json.loads((path.parent / finish_agent_harness(path)["company_result"]["path"]).read_text())
            self.assertEqual(2, company["claims"][0]["development_log"]["entries"])
            usage = company["claims"][0]["development_usage"]["implementer"]
            self.assertEqual(({"input_tokens": 1200, "output_tokens": 300}, 1), (usage["usage"], usage["measured"]))
            self.assertEqual("not_recorded", company["research_usage"]["status"])


class SessionUsageTest(unittest.TestCase):
    def test_reads_claude_subagents_and_codex_cumulative_totals(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            claude = root / "claude" / "projects" / "p"
            (claude / "s1" / "subagents").mkdir(parents=True)

            def message(identifier, tokens, model="claude-opus-5-5"):
                return json.dumps({"type": "assistant", "message": {"id": identifier, "model": model,
                                   "usage": {"output_tokens": tokens, "cache_creation": {"x": 1}}}})
            (claude / "s1.jsonl").write_text("\n".join([message("a", 5), message("a", 5), message("b", 7),
                                                         message("z", 0, "<synthetic>")]))
            (claude / "s1" / "subagents" / "agent-sub1.jsonl").write_text(message("c", 11))
            codex = root / "codex" / "sessions" / "2026" / "10" / "06"
            codex.mkdir(parents=True)
            events = [{"type": "turn_context", "payload": {"model": "gpt-6-astra"}},
                      {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 10}}}},
                      {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 25}}}}]
            (codex / "rollout-2026-10-06T00-00-00-abc-123.jsonl").write_text("\n".join(json.dumps(e) for e in events))
            with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(root / "claude"), "CODEX_HOME": str(root / "codex")}):
                session = agent_usage("s1", "claude")
                subagent = agent_usage("sub1", "claude")
                rollout = agent_usage("abc-123", "codex")
                missing = agent_usage("nope", "codex")
                path_like = agent_usage("/root/replica_agent/operator", "codex")
        self.assertEqual(({"output_tokens": 23}, 3, ["claude-opus-5-5"]),
                         (session["usage"], session["messages"], session["models"]))
        self.assertEqual({"output_tokens": 11}, subagent["usage"])
        self.assertEqual(({"input_tokens": 25}, ["gpt-6-astra"]), (rollout["usage"], rollout["models"]))
        self.assertEqual(("unknown", None), (missing["status"], missing["usage"]))
        self.assertEqual("unknown", path_like["status"])


if __name__ == "__main__":
    unittest.main()
