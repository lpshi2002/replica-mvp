import json
import os
import sys
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from replica_mvp.agent_harness import finish_agent_harness, require_company_mount
from replica_mvp.bundle_evaluation import evaluate_agent_bundle
from replica_mvp.bundle_runtime import validate_web_runtime, web_app_session
from replica_mvp.company_app import NAV_MARKER, SHELL_CSS_PATH, company_app_session
from tests.test_web_demo import HAS_PLAYWRIGHT, _passing_judge, _scripted_tester, _write_app, _write_cli
from tests.test_web_evaluation import APPROVE, WEB_RUNTIME, _bind_web_app, _passing_review

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def _mounted_app(directory: Path) -> Path:
    manifest_path = _write_app(directory)
    manifest = json.loads(manifest_path.read_text())
    manifest["runtime"] = dict(WEB_RUNTIME)
    manifest_path.write_text(json.dumps(manifest))
    return manifest_path


class RuntimeContractTest(unittest.TestCase):
    def test_base_path_argument_is_optional_and_distinct(self):
        legacy = {"transport": "web_app", "port_argument": "--port", "ready_path": "/"}
        self.assertEqual(legacy, validate_web_runtime(dict(legacy)))
        self.assertEqual(WEB_RUNTIME, validate_web_runtime(dict(WEB_RUNTIME)))
        for bad in ({**legacy, "base_path_argument": "base"}, {**legacy, "base_path_argument": "--port"},
                    {**legacy, "other": "--x"}):
            with self.assertRaisesRegex(ValueError, "web app runtime"):
                validate_web_runtime(bad)

    def test_company_feature_claim_requires_a_mountable_bundle(self):
        claim = {"web_demo": {"mount_path": "/claim-001"}}
        with self.assertRaisesRegex(ValueError, "base_path_argument"):
            require_company_mount(claim, {"runtime": {"transport": "web_app", "port_argument": "--port", "ready_path": "/"}})
        require_company_mount(claim, {"runtime": dict(WEB_RUNTIME)})
        # Claims frozen before the company app keep their standalone bundles.
        require_company_mount({"web_demo": {}}, {"runtime": {"transport": "web_app", "port_argument": "--port",
                                                             "ready_path": "/"}})


class CompanyShellTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        _write_cli(self.root / "real")
        self.env = patch.dict(os.environ, {"PATH": f"{self.root / 'real'}{os.pathsep}{os.environ['PATH']}"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.directory.cleanup()

    def test_shell_serves_menu_and_forwards_each_feature_under_its_path(self):
        features = [{"id": "claim-001", "title": "승인 워크플로", "manifest": _mounted_app(self.root / "a"),
                     "workspace": self.root / "state-a"},
                    {"id": "claim-002", "title": "두 번째 기능", "manifest": _mounted_app(self.root / "b"),
                     "workspace": self.root / "state-b"}]
        with company_app_session("Acme", features, 30) as (shell, roots):
            menu = _OPENER.open(shell + "/").read().decode()
            self.assertIn('href="/claim-001/"', menu)
            self.assertIn("두 번째 기능", menu)
            page = _OPENER.open(shell + "/claim-001/").read().decode()
            self.assertIn(NAV_MARKER, page)
            self.assertIn("action=/claim-001/requests", page)
            # The menu and every feature page share the shell's stylesheet.
            link = f'<link rel="stylesheet" href="{SHELL_CSS_PATH}">'
            self.assertIn(link, menu)
            self.assertIn(link, page)
            with _OPENER.open(shell + SHELL_CSS_PATH) as stylesheet:
                self.assertTrue(stylesheet.headers["Content-Type"].startswith("text/css"))
                self.assertIn(b"nav[data-company-shell]", stylesheet.read())
            # A form post goes through the shell; the redirect stays on the shell's address.
            data = urllib.parse.urlencode({"text": "의자"}).encode()
            with self.assertRaises(urllib.error.HTTPError) as redirect:
                urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect).open(
                    shell + "/claim-001/requests", data)
            self.assertEqual(303, redirect.exception.code)
            self.assertEqual("/claim-001/", redirect.exception.headers["Location"])
            self.assertIn("의자", _OPENER.open(shell + "/claim-001/").read().decode())
            self.assertNotIn("의자", _OPENER.open(shell + "/claim-002/").read().decode())
            with self.assertRaises(urllib.error.HTTPError) as missing:
                _OPENER.open(shell + "/claim-009/")
            self.assertEqual(404, missing.exception.code)
        self.assertTrue((roots["claim-001"] / "data" / "requests.json").is_file())
        self.assertFalse((roots["claim-002"] / "data" / "requests.json").exists())

    def test_standalone_bundle_is_not_mounted(self):
        manifest = _write_app(self.root / "legacy")
        feature = {"id": "claim-001", "title": "x", "manifest": manifest, "workspace": self.root / "s"}
        with self.assertRaisesRegex(ValueError, "base_path_argument"):
            with company_app_session("Acme", [feature], 30):
                pass
        with self.assertRaisesRegex(ValueError, "cannot be mounted"):
            with web_app_session(manifest, 30, workspace=self.root / "s2", base_path="/claim-001"):
                pass


@unittest.skipUnless(HAS_PLAYWRIGHT, "web demo needs the optional playwright dependency")
class CompanyAppEvaluationTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        _write_cli(self.root / "real")
        self.env = patch.dict(os.environ, {
            "PATH": f"{self.root / 'real'}{os.pathsep}{os.environ['PATH']}",
            "CLAUDE_CONFIG_DIR": str(self.root / "claude-home"), "CODEX_HOME": str(self.root / "codex-home"),
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.directory.cleanup()

    def test_new_run_refuses_a_standalone_bundle(self):
        legacy = {"transport": "web_app", "port_argument": "--port", "ready_path": "/"}
        with self.assertRaisesRegex(ValueError, "base_path_argument"):
            _bind_web_app(self.root / "run", runtime=legacy)

    def test_tester_starts_at_the_company_menu_and_finish_checks_the_assembled_app(self):
        registry = _bind_web_app(self.root / "run")
        claim = json.loads(registry.read_text())["claims"][0]
        self.assertEqual("/claim-001", claim["web_demo"]["mount_path"])
        evaluated = evaluate_agent_bundle(registry, "claim-001", tester=_scripted_tester(APPROVE),
                                          judge=_passing_judge, reviewer=_passing_review)
        claim = evaluated["claims"][0]
        self.assertEqual("RESULT_SUCCESS", claim["status"])
        run = registry.parent / claim["final_result"]["public_run_dir"]
        result = json.loads((run / "demo-result.json").read_text())
        self.assertEqual("company_app_browser", result["interaction_surface"])
        events = [json.loads(line) for line in (run / "events.jsonl").read_text().splitlines()]
        self.assertTrue(events[0]["url_before"].endswith("/"))
        self.assertIn("/claim-001/", events[0]["url_after"])
        finished = finish_agent_harness(registry)
        company = json.loads((registry.parent / finished["company_result"]["path"]).read_text())
        app = company["company_app"]
        self.assertEqual("assembled", app["status"])
        self.assertEqual([("claim-001", "/claim-001/", "loaded", True)],
                         [(f["claim_id"], f["path"], f["status"], f["shell_navigation"]) for f in app["features"]])
        self.assertIn("## 기업 앱", (registry.parent / finished["company_result"]["architecture_path"]).read_text())


if __name__ == "__main__":
    unittest.main()
