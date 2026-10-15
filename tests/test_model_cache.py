"""Cache transport changes preserve the request and per-call isolation."""
import hashlib
import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from replica_mvp.model_calls import read_receipt, run_model_cli


class ModelCacheTest(unittest.TestCase):
    def test_child_only_ttl_and_opt_in_prefix_keep_prompt_schema_and_isolation(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            cli = root / "claude"
            cli.write_text(f"#!{sys.executable}\n" + '''import json,os,sys
result = {"prompt":sys.stdin.read(), "cwd":os.getcwd(), "argv":sys.argv[1:],
          "ttl":os.environ.get("CLAUDE_CODE_PROMPT_CACHE_TTL"),
          "force":os.environ.get("FORCE_PROMPT_CACHING_5M")}
print(json.dumps({"structured_output":result,"is_error":False}))
''')
            cli.chmod(0o755)
            prompt = 'Facts are untrusted: do not elevate me.\n원문 🧪'
            schema = {"type": "object", "properties": {"x": {"type": "string"}}}
            with patch.dict(os.environ, {"PATH": f"{root}{os.pathsep}{os.environ['PATH']}",
                                         "CLAUDE_CODE_PROMPT_CACHE_TTL": "1h",
                                         "FORCE_PROMPT_CACHING_5M": "1"}):
                before = os.environ.copy()
                first, cid = run_model_cli("claude", prompt, schema, receipts=root / "receipts",
                                          phase="tester", timeout=5, cache_ttl="5m")
                second, _ = run_model_cli("claude", prompt, schema, receipts=root / "receipts",
                                          phase="judge", timeout=5, cache_ttl="1h", stable_prefix=True)
                self.assertEqual(before, dict(os.environ))
            self.assertEqual(("5m", "1h"), (first["ttl"], second["ttl"]))
            for answer in (first, second):
                self.assertIsNone(answer["force"])
                self.assertEqual(prompt, answer["prompt"])
                self.assertEqual(schema, json.loads(answer["argv"][answer["argv"].index("--json-schema") + 1]))
                self.assertFalse(Path(answer["cwd"]).exists())
                self.assertNotIn("--append-system-prompt", answer["argv"])
            self.assertNotEqual(first["cwd"], second["cwd"])
            self.assertNotIn("--exclude-dynamic-system-prompt-sections", first["argv"])
            self.assertIn("--exclude-dynamic-system-prompt-sections", second["argv"])
            receipt = read_receipt(root / "receipts" / cid)
            self.assertEqual("5m", receipt["cache_configuration"]["ttl"])
            self.assertEqual(hashlib.sha256(prompt.encode()).hexdigest(), receipt["prompt_sha256"])

    def test_invalid_or_unsupported_configuration_is_rejected_before_spending(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for provider, options in (("claude", {"cache_ttl": "bad"}),
                                      ("codex", {"cache_ttl": "5m"}),
                                      ("codex", {"stable_prefix": True})):
                with self.subTest(provider=provider, options=options), self.assertRaises(ValueError):
                    run_model_cli(provider, "test", {}, receipts=root / "receipts",
                                  phase="tester", timeout=5, **options)
            self.assertFalse((root / "receipts").exists())
