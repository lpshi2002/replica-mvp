import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from replica_mvp.cli import main


REPOSITORY_ROOT = Path(__file__).parents[1]
LEAD_EXAMPLE = (
    REPOSITORY_ROOT / "examples" / "second-pass-lead-qualification.json"
)


class PublicCliContractTest(unittest.TestCase):
    def test_cli_exposes_the_codex_operator_prepare_and_finalize_seam(self):
        prepared_result = {
            "schema_version": "replica-codex-operator-result/v1",
            "status": "AWAITING_CODEX_OPERATOR",
        }
        finalized_result = {
            "schema_version": "replica-codex-operator-result/v1",
            "status": "BUILT_AND_PASSED",
        }

        with (
            TemporaryDirectory() as tmp,
            patch(
                "replica_mvp.cli.prepare_codex_operator",
                return_value=prepared_result,
            ) as prepare_operator,
            patch(
                "replica_mvp.cli.finalize_codex_operator",
                return_value=finalized_result,
            ) as finalize_operator,
        ):
            workspace = Path(tmp) / "workspace"
            evaluator_vault = Path(tmp) / "evaluator-vault"
            task = workspace / "operator-tasks" / "replica" / "digest"
            with redirect_stdout(StringIO()):
                prepare_exit = main(
                    [
                        "prepare-operator",
                        str(LEAD_EXAMPLE),
                        "--workspace",
                        str(workspace),
                        "--evaluation-vault",
                        str(evaluator_vault),
                    ]
                )
                finalize_exit = main(
                    [
                        "finalize-operator",
                        str(task),
                        "--workspace",
                        str(workspace),
                        "--evaluation-vault",
                        str(evaluator_vault),
                        "--report",
                    ]
                )

        self.assertEqual(0, prepare_exit)
        self.assertEqual(0, finalize_exit)
        prepare_operator.assert_called_once_with(
            LEAD_EXAMPLE,
            workspace,
            evaluator_vault,
        )
        finalize_operator.assert_called_once_with(
            task,
            workspace,
            evaluator_vault,
            include_report=True,
        )

    def test_cli_has_no_legacy_replicate_or_generator_flags(self):
        parser = __import__("replica_mvp.cli", fromlist=["_parser"])._parser()

        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["replicate", str(LEAD_EXAMPLE)])


if __name__ == "__main__":
    unittest.main()
