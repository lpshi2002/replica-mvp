import unittest

from replica_mvp import assess_plan_safety


class ExecutionPlanSafetyTest(unittest.TestCase):
    def test_blocks_malformed_json_types_instead_of_raising(self):
        step = {
            "id": "render-output",
            "strategy": "known_component",
            "operation": "render_static_site",
            "depends_on": [],
            "access": {
                "network": False,
                "external_credentials": [],
            },
            "limits": {
                "timeout_seconds": 30,
                "max_output_bytes": 1_000_000,
            },
        }
        malformed_plans = [
            [],
            {
                "schema_version": "replica-execution-plan/v1",
                "steps": [{**step, "access": None}],
            },
            {
                "schema_version": "replica-execution-plan/v1",
                "steps": [{**step, "limits": None}],
            },
            {
                "schema_version": "replica-execution-plan/v1",
                "steps": [{**step, "operation": []}],
            },
        ]

        for plan in malformed_plans:
            with self.subTest(plan=plan):
                assessment = assess_plan_safety(
                    plan,
                    available_operations={"render_static_site"},
                )
                self.assertEqual("BLOCKED", assessment["status"])
                self.assertEqual(
                    "INVALID_PLAN_SCHEMA",
                    assessment["violations"][0]["code"],
                )

    def test_blocks_undefined_execution_fields(self):
        plan = {
            "schema_version": "replica-execution-plan/v1",
            "steps": [
                {
                    "id": "disguised-command",
                    "strategy": "known_component",
                    "operation": "render_static_site",
                    "depends_on": [],
                    "access": {
                        "network": False,
                        "external_credentials": [],
                    },
                    "limits": {
                        "timeout_seconds": 30,
                        "max_output_bytes": 1_000_000,
                    },
                    "command": "python generated.py",
                }
            ],
        }

        assessment = assess_plan_safety(
            plan,
            available_operations={"render_static_site"},
        )

        self.assertEqual("BLOCKED", assessment["status"])
        self.assertEqual(
            "INVALID_PLAN_SCHEMA",
            assessment["violations"][0]["code"],
        )

    def test_blocks_undeclared_operation_inputs(self):
        plan = {
            "schema_version": "replica-execution-plan/v1",
            "steps": [
                {
                    "id": "disguised-input",
                    "strategy": "known_component",
                    "operation": "render_static_site",
                    "depends_on": [],
                    "inputs": {
                        "generated_code": "open('escaped.txt', 'w').write('x')",
                    },
                    "access": {
                        "network": False,
                        "external_credentials": [],
                    },
                    "limits": {
                        "timeout_seconds": 30,
                        "max_output_bytes": 1_000_000,
                    },
                }
            ],
        }

        assessment = assess_plan_safety(
            plan,
            available_operations={"render_static_site"},
        )

        self.assertEqual("BLOCKED", assessment["status"])
        self.assertIn(
            {
                "code": "UNDECLARED_OPERATION_INPUT",
                "step_id": "disguised-input",
            },
            assessment["violations"],
        )

    def test_blocks_an_empty_or_unknown_plan_schema(self):
        assessment = assess_plan_safety(
            {"schema_version": "unknown", "steps": []},
            available_operations={"render_static_site"},
        )

        self.assertEqual(
            {
                "status": "BLOCKED",
                "violations": [
                    {
                        "code": "INVALID_PLAN_SCHEMA",
                        "step_id": "",
                    }
                ],
            },
            assessment,
        )

    def test_allows_a_registered_operation_without_external_access(self):
        plan = {
            "schema_version": "replica-execution-plan/v1",
            "steps": [
                {
                    "id": "render-output",
                    "strategy": "known_component",
                    "operation": "render_static_site",
                    "depends_on": [],
                    "inputs": {
                        "requirements": "responsive public landing page",
                    },
                    "access": {
                        "network": False,
                        "external_credentials": [],
                    },
                    "limits": {
                        "timeout_seconds": 30,
                        "max_output_bytes": 1_000_000,
                    },
                }
            ],
        }

        assessment = assess_plan_safety(
            plan,
            available_operations={"render_static_site"},
            operation_input_fields={"render_static_site": {"requirements"}},
        )

        self.assertEqual(
            {
                "status": "SAFE_TO_EXECUTE",
                "violations": [],
            },
            assessment,
        )

    def test_blocks_network_access_before_execution(self):
        plan = {
            "schema_version": "replica-execution-plan/v1",
            "steps": [
                {
                    "id": "fetch-private-api",
                    "strategy": "known_component",
                    "operation": "render_static_site",
                    "depends_on": [],
                    "access": {
                        "network": True,
                        "external_credentials": [],
                    },
                    "limits": {
                        "timeout_seconds": 30,
                        "max_output_bytes": 1_000_000,
                    },
                }
            ],
        }

        assessment = assess_plan_safety(
            plan,
            available_operations={"render_static_site"},
        )

        self.assertEqual("BLOCKED", assessment["status"])
        self.assertIn(
            {
                "code": "NETWORK_ACCESS_FORBIDDEN",
                "step_id": "fetch-private-api",
            },
            assessment["violations"],
        )

    def test_blocks_external_credentials_before_execution(self):
        plan = {
            "schema_version": "replica-execution-plan/v1",
            "steps": [
                {
                    "id": "call-vendor",
                    "strategy": "known_component",
                    "operation": "render_static_site",
                    "depends_on": [],
                    "access": {
                        "network": False,
                        "external_credentials": ["VENDOR_API_KEY"],
                    },
                    "limits": {
                        "timeout_seconds": 30,
                        "max_output_bytes": 1_000_000,
                    },
                }
            ],
        }

        assessment = assess_plan_safety(
            plan,
            available_operations={"render_static_site"},
        )

        self.assertEqual("BLOCKED", assessment["status"])
        self.assertIn(
            {
                "code": "EXTERNAL_CREDENTIALS_FORBIDDEN",
                "step_id": "call-vendor",
            },
            assessment["violations"],
        )

    def test_blocks_generated_code_until_a_sandbox_runner_exists(self):
        plan = {
            "schema_version": "replica-execution-plan/v1",
            "steps": [
                {
                    "id": "generated-builder",
                    "strategy": "generated_component",
                    "operation": "render_static_site",
                    "depends_on": [],
                    "access": {
                        "network": False,
                        "external_credentials": [],
                    },
                    "limits": {
                        "timeout_seconds": 30,
                        "max_output_bytes": 1_000_000,
                    },
                }
            ],
        }

        assessment = assess_plan_safety(
            plan,
            available_operations={"render_static_site"},
        )

        self.assertEqual("BLOCKED", assessment["status"])
        self.assertIn(
            {
                "code": "GENERATED_COMPONENT_FORBIDDEN",
                "step_id": "generated-builder",
            },
            assessment["violations"],
        )

    def test_allows_only_the_registered_generated_component_runner(self):
        plan = {
            "schema_version": "replica-execution-plan/v1",
            "steps": [
                {
                    "id": "generated-expression",
                    "strategy": "generated_component",
                    "operation": "execute_generated_component",
                    "depends_on": [],
                    "inputs": {
                        "component_sha256": "a" * 64,
                        "request_sha256": "b" * 64,
                    },
                    "access": {
                        "network": False,
                        "external_credentials": [],
                    },
                    "limits": {
                        "timeout_seconds": 30,
                        "max_output_bytes": 1_000_000,
                    },
                }
            ],
        }

        assessment = assess_plan_safety(
            plan,
            available_operations={"execute_generated_component"},
            operation_input_fields={
                "execute_generated_component": {
                    "component_sha256",
                    "request_sha256",
                }
            },
            generated_component_operations={"execute_generated_component"},
        )

        self.assertEqual(
            {
                "status": "SAFE_TO_EXECUTE",
                "violations": [],
            },
            assessment,
        )

    def test_allows_generated_code_only_with_the_restricted_runner(self):
        plan = {
            "schema_version": "replica-execution-plan/v1",
            "steps": [
                {
                    "id": "agent-written-python",
                    "strategy": "generated_code",
                    "operation": "execute_generated_component",
                    "depends_on": [],
                    "inputs": {
                        "component_sha256": "a" * 64,
                        "request_sha256": "b" * 64,
                    },
                    "access": {
                        "network": False,
                        "external_credentials": [],
                    },
                    "limits": {
                        "timeout_seconds": 10,
                        "max_output_bytes": 1_000_000,
                    },
                }
            ],
        }

        assessment = assess_plan_safety(
            plan,
            available_operations={"execute_generated_component"},
            operation_input_fields={
                "execute_generated_component": {
                    "component_sha256",
                    "request_sha256",
                }
            },
            generated_code_operations={"execute_generated_component"},
        )

        self.assertEqual(
            {
                "status": "SAFE_TO_EXECUTE",
                "violations": [],
            },
            assessment,
        )

    def test_requires_bounded_runtime_and_output(self):
        plan = {
            "schema_version": "replica-execution-plan/v1",
            "steps": [
                {
                    "id": "unbounded-render",
                    "strategy": "known_component",
                    "operation": "render_static_site",
                    "depends_on": [],
                    "access": {
                        "network": False,
                        "external_credentials": [],
                    },
                }
            ],
        }

        assessment = assess_plan_safety(
            plan,
            available_operations={"render_static_site"},
        )

        self.assertEqual("BLOCKED", assessment["status"])
        self.assertIn(
            {
                "code": "RESOURCE_LIMITS_REQUIRED",
                "step_id": "unbounded-render",
            },
            assessment["violations"],
        )

    def test_blocks_resource_limits_above_the_mvp_policy(self):
        plan = {
            "schema_version": "replica-execution-plan/v1",
            "steps": [
                {
                    "id": "oversized-render",
                    "strategy": "known_component",
                    "operation": "render_static_site",
                    "depends_on": [],
                    "access": {
                        "network": False,
                        "external_credentials": [],
                    },
                    "limits": {
                        "timeout_seconds": 121,
                        "max_output_bytes": 10_000_001,
                    },
                }
            ],
        }

        assessment = assess_plan_safety(
            plan,
            available_operations={"render_static_site"},
        )

        self.assertEqual("BLOCKED", assessment["status"])
        self.assertIn(
            {
                "code": "RESOURCE_LIMITS_EXCEEDED",
                "step_id": "oversized-render",
            },
            assessment["violations"],
        )

    def test_blocks_a_dependency_on_an_unknown_step(self):
        plan = {
            "schema_version": "replica-execution-plan/v1",
            "steps": [
                {
                    "id": "render-output",
                    "strategy": "known_component",
                    "operation": "render_static_site",
                    "depends_on": ["missing-input"],
                    "access": {
                        "network": False,
                        "external_credentials": [],
                    },
                    "limits": {
                        "timeout_seconds": 30,
                        "max_output_bytes": 1_000_000,
                    },
                }
            ],
        }

        assessment = assess_plan_safety(
            plan,
            available_operations={"render_static_site"},
        )

        self.assertEqual("BLOCKED", assessment["status"])
        self.assertIn(
            {
                "code": "UNKNOWN_DEPENDENCY",
                "step_id": "render-output",
            },
            assessment["violations"],
        )

    def test_blocks_cyclic_step_dependencies(self):
        def step(step_id, depends_on):
            return {
                "id": step_id,
                "strategy": "known_component",
                "operation": "render_static_site",
                "depends_on": depends_on,
                "access": {
                    "network": False,
                    "external_credentials": [],
                },
                "limits": {
                    "timeout_seconds": 30,
                    "max_output_bytes": 1_000_000,
                },
            }

        plan = {
            "schema_version": "replica-execution-plan/v1",
            "steps": [
                step("prepare-input", ["render-output"]),
                step("render-output", ["prepare-input"]),
            ],
        }

        assessment = assess_plan_safety(
            plan,
            available_operations={"render_static_site"},
        )

        self.assertEqual("BLOCKED", assessment["status"])
        self.assertIn(
            {
                "code": "CYCLIC_DEPENDENCY",
                "step_id": "prepare-input",
            },
            assessment["violations"],
        )


if __name__ == "__main__":
    unittest.main()
