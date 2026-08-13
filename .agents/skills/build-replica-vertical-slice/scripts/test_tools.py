from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from compile_contract import compile_contract
from evaluate_hybrid import evaluate
from materialize_assets import materialize
from run_hybrid import run


REPOSITORY_ROOT = Path(__file__).parents[4]
EXAMPLE = REPOSITORY_ROOT / "examples" / "second-pass-static-site.json"


class VerticalSliceToolTest(unittest.TestCase):
    def test_compiles_materializes_and_runs_one_candidate(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            workspace = root / "workspace"
            vault = root / "vault"
            prepared = compile_contract(EXAMPLE, workspace, vault)
            task_dir = Path(prepared["task_dir"])

            self.assertTrue(Path(prepared["request_path"]).is_file())
            self.assertFalse((task_dir / "tests.json").exists())
            private_tests = list(vault.glob("hybrid-runs/*/*/tests.json"))
            self.assertEqual(1, len(private_tests))

            requests_path = Path(prepared["asset_requests_path"])
            requests_path.write_text(
                json.dumps(
                    {
                        "schema_version": "replica-asset-requests/v1",
                        "assets": [
                            {
                                "id": "public-contract",
                                "source": {"type": "local", "location": str(EXAMPLE)},
                                "media_type": "application/json",
                                "license": "test fixture",
                                "provenance": "public",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            manifest = materialize(requests_path, task_dir, 1_000_000, 5)
            self.assertEqual(1, len(manifest["assets"]))
            self.assertRegex(manifest["assets"][0]["sha256"], r"^[0-9a-f]{64}$")

            implementation_path = Path(prepared["implementation_path"])
            implementation_path.write_text(
                """from __future__ import annotations
import json
import sys
request = json.load(sys.stdin)
json.dump({"asset_count": len(request["assets"]), "input": request["input"]}, sys.stdout)
""",
                encoding="utf-8",
            )
            input_path = root / "input.json"
            input_path.write_text('{"title":"Smoke test"}', encoding="utf-8")
            result = run(task_dir, 1, input_path, 10, 100_000)
            self.assertEqual({"asset_count": 1, "input": {"title": "Smoke test"}}, result)
            evaluation = evaluate(task_dir, vault, 1, 10, 100_000)
            self.assertEqual("EVALUATION_FAILED", evaluation["status"])
            self.assertEqual(3, evaluation["total"])
            self.assertNotIn("path", evaluation)

    def test_rejects_overlapping_public_and_private_roots(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with self.assertRaisesRegex(ValueError, "must not overlap"):
                compile_contract(EXAMPLE, root, root / "vault")


if __name__ == "__main__":
    unittest.main()
