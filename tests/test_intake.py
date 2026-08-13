import hashlib
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from replica_mvp import receive_second_pass
from replica_mvp.cli import main


class SecondPassIntakeTest(unittest.TestCase):
    def test_receives_json_and_preserves_source_with_digest(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "second-pass.json"
            source_bytes = '{"canonical_claim":"공개 기능"}\n'.encode()
            source.write_bytes(source_bytes)

            result = receive_second_pass(source, root / "workspace")

            digest = hashlib.sha256(source_bytes).hexdigest()
            intake_dir = root / "workspace" / "intakes" / digest
            self.assertEqual("AWAITING_CONTRACT_VALIDATION", result["status"])
            self.assertEqual(digest, result["sha256"])
            self.assertEqual("second-pass.json", result["source_name"])
            self.assertEqual(source_bytes, (intake_dir / "source.json").read_bytes())
            self.assertEqual(
                result,
                json.loads((intake_dir / "intake.json").read_text(encoding="utf-8")),
            )

    def test_receiving_same_content_returns_existing_intake(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "second-pass.json"
            source.write_text('{"canonical_claim":"same"}', encoding="utf-8")
            workspace = root / "workspace"

            first = receive_second_pass(source, workspace)
            source.rename(root / "renamed.json")
            second = receive_second_pass(root / "renamed.json", workspace)

            self.assertEqual(first, second)
            self.assertEqual(
                1,
                len(list((workspace / "intakes").iterdir())),
            )

    def test_rejects_invalid_json_without_creating_workspace(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "second-pass.json"
            source.write_text('{"canonical_claim":', encoding="utf-8")
            workspace = root / "workspace"

            with self.assertRaisesRegex(ValueError, "invalid JSON"):
                receive_second_pass(source, workspace)

            self.assertFalse(workspace.exists())

    def test_rejects_nonstandard_json_constants_without_creating_workspace(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "second-pass.json"
            source.write_text('{"score": NaN}', encoding="utf-8")
            workspace = root / "workspace"

            with self.assertRaisesRegex(ValueError, "invalid JSON"):
                receive_second_pass(source, workspace)

            self.assertFalse(workspace.exists())

    def test_rejects_non_object_json_without_creating_workspace(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "second-pass.json"
            source.write_text("[]", encoding="utf-8")
            workspace = root / "workspace"

            with self.assertRaisesRegex(ValueError, "JSON object"):
                receive_second_pass(source, workspace)

            self.assertFalse(workspace.exists())

    def test_cli_receives_second_pass_file(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "second-pass.json"
            source.write_text('{"canonical_claim":"cli"}', encoding="utf-8")
            workspace = root / "workspace"
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "intake",
                        str(source),
                        "--workspace",
                        str(workspace),
                    ]
                )

            result = json.loads(stdout.getvalue())
            self.assertEqual(0, exit_code)
            self.assertEqual("AWAITING_CONTRACT_VALIDATION", result["status"])
            self.assertTrue(
                (workspace / "intakes" / result["sha256"] / "source.json").exists()
            )
