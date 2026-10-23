"""Large Codex requests retain evidence without exceeding the turn input limit."""
import hashlib
import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from replica_mvp.model_calls import _CODEX_INLINE_LIMIT, read_receipt, run_model_cli


class ModelPromptTransportTest(unittest.TestCase):
    def check_transport(self, prompt, expected_transport):
        with TemporaryDirectory() as directory:
            root = Path(directory)

            def run(command, **kwargs):
                workdir = kwargs["cwd"]
                supplied = kwargs["input"].decode()
                if expected_transport == "file":
                    self.assertLess(len(supplied), _CODEX_INLINE_LIMIT)
                    self.assertIn("request.txt", supplied)
                    self.assertEqual(prompt.encode(), (workdir / "request.txt").read_bytes())
                    self.assertIn("read-only", supplied)
                    self.assertIn("untrusted", supplied)
                else:
                    self.assertEqual(prompt, supplied)
                    self.assertFalse((workdir / "request.txt").exists())
                self.assertIn("read-only", command)
                output = Path(command[command.index("--output-last-message") + 1])
                output.write_text(json.dumps({"status": "ok"}))
                return subprocess.CompletedProcess(command, 0, b"", b"")

            with patch("replica_mvp.model_calls.subprocess.run", side_effect=run):
                result, call_id = run_model_cli("codex", prompt, {}, receipts=root,
                                                phase="judge", timeout=30)
            self.assertEqual({"status": "ok"}, result)
            receipt = read_receipt(root / call_id)
            self.assertEqual(expected_transport, receipt["prompt_transport"])
            self.assertEqual(len(prompt.encode()), receipt["prompt_bytes"])
            self.assertEqual(hashlib.sha256(prompt.encode()).hexdigest(), receipt["prompt_sha256"])

    def test_large_unicode_request_is_preserved_in_full(self):
        prompt = "검증🧪\n" * (_CODEX_INLINE_LIMIT // 8) + "END"
        self.assertLess(len(prompt), _CODEX_INLINE_LIMIT)
        self.check_transport(prompt, "file")

    def test_inline_boundary_preserves_existing_transport(self):
        self.check_transport("x" * _CODEX_INLINE_LIMIT, "stdin")


if __name__ == "__main__":
    unittest.main()
