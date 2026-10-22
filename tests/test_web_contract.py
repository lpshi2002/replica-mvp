import json
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from replica_mvp.web_demo import freeze_demo_plan, validate_demo_plan
from tests.test_web_demo import _plan


class CriteriaTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.plan = json.loads(_plan(self.root).read_text())

    def test_legacy_is_readable_but_cannot_start_a_new_execution(self):
        self.plan.pop("criteria_version")
        validate_demo_plan(self.plan, self.root)
        with self.assertRaisesRegex(ValueError, "freeze a corrected plan"):
            validate_demo_plan(self.plan, self.root, for_execution=True)

    def test_quote_must_belong_to_the_bound_source(self):
        for mutation in ("quote", "source", "source_id", "interpretation"):
            with self.subTest(mutation=mutation):
                plan = deepcopy(self.plan)
                plan["cases"][0]["expectations"][1]["basis"][mutation] = "" if mutation == "interpretation" else "unrecorded"
                with self.assertRaisesRegex(ValueError, "recorded source"):
                    validate_demo_plan(plan, self.root)

    def test_public_rule_cannot_carry_a_bound_its_quote_does_not_state(self):
        expectation = self.plan["cases"][0]["expectations"][1]
        expectation["description"] += " If this does not happen within six answers, the expectation fails."
        with self.assertRaisesRegex(ValueError, "public_rule states within six, which its quote does not"):
            validate_demo_plan(self.plan, self.root)
        # Our own bound is allowed as an outcome condition with its reason.
        expectation["basis"] = {"type": "our_condition", "source": "pass-2 research",
                                "rationale": "A customer should finish the task within reasonable effort."}
        validate_demo_plan(self.plan, self.root)

    def test_own_condition_needs_reason_and_limits_cannot_be_expectations(self):
        expectation = self.plan["cases"][0]["expectations"][0]
        expectation["basis"].pop("rationale")
        with self.assertRaisesRegex(ValueError, "rationale"):
            validate_demo_plan(self.plan, self.root)
        expectation["basis"]["rationale"] = "Meaningful output for the user"
        expectation["purpose"] = "execution_limit"
        with self.assertRaisesRegex(ValueError, "execution limit"):
            validate_demo_plan(self.plan, self.root)

    def test_stopping_budget_and_conditional_product_rule_are_separate(self):
        case = self.plan["cases"][0]
        case["execution_limits"] = ["Stop after six detailed answers; the limit is a trial budget."]
        e = case["expectations"][1]
        e["precondition"] = "The topic has reached 100% completion."
        validate_demo_plan(self.plan, self.root, for_execution=True)
        e["check"] = {"type": "page_contains", "text": "new topic"}
        with self.assertRaisesRegex(ValueError, "precondition"):
            validate_demo_plan(self.plan, self.root)

    def test_observation_and_independent_verification_need_context(self):
        for kind, field in (("original_observation", "conditions"), ("separate_verification", "method")):
            plan = deepcopy(self.plan)
            basis = plan["cases"][0]["expectations"][1]["basis"]
            basis["type"] = kind
            with self.assertRaisesRegex(ValueError, field):
                validate_demo_plan(plan, self.root)
            basis[field] = "Recorded version, input, observation and verification procedure"
            validate_demo_plan(plan, self.root)

    def test_expectation_cannot_claim_a_step_outside_its_case(self):
        self.plan["cases"][0]["expectations"][0]["covers_steps"] = [99]
        with self.assertRaisesRegex(ValueError, "covers_steps"):
            validate_demo_plan(self.plan, self.root)
