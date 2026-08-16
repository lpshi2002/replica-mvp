import unittest

from replica_mvp.python_component import (
    execute_python_component,
    validate_python_component_source,
)


class PythonComponentTest(unittest.TestCase):
    def test_executes_agent_written_algorithmic_code(self):
        source = (
            "def classify(value):\n"
            "    if value >= 80:\n"
            "        return 'high'\n"
            "    if value >= 50:\n"
            "        return 'medium'\n"
            "    return 'low'\n"
            "\n"
            "def replicate(runtime_input):\n"
            "    scores = runtime_input['scores']\n"
            "    return {\n"
            "        'labels': [classify(score) for score in scores],\n"
            "        'average': sum(scores) / len(scores),\n"
            "    }\n"
        )

        self.assertEqual(
            {
                "labels": ["high", "medium", "low"],
                "average": 57,
            },
            execute_python_component(
                source,
                {"scores": [90, 60, 21]},
            ),
        )

    def test_rejects_external_access_and_runtime_introspection(self):
        forbidden_sources = [
            (
                "def replicate(runtime_input):\n"
                "    import os\n"
                "    return os.environ\n",
                "forbidden syntax: Import",
            ),
            (
                "def replicate(runtime_input):\n"
                "    return open('secret.txt').read()\n",
                "forbidden function",
            ),
            (
                "def replicate(runtime_input):\n"
                "    return runtime_input.__class__\n",
                "forbidden attribute",
            ),
        ]

        for source, message in forbidden_sources:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    validate_python_component_source(source)

    def test_stops_code_that_exceeds_the_execution_step_budget(self):
        source = (
            "def replicate(runtime_input):\n"
            "    total = 0\n"
            "    for value in range(1000000):\n"
            "        total += value\n"
            "    return total\n"
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "execution failed",
        ):
            execute_python_component(source, {})

    def test_stops_single_expression_memory_amplification(self):
        source = (
            "def replicate(runtime_input):\n"
            "    return [0] * 500000000\n"
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "execution failed",
        ):
            execute_python_component(source, {})


if __name__ == "__main__":
    unittest.main()
