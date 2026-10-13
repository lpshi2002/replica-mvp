"""One web app per company: a shared shell that serves each claim's web-app bundle under its own path.

Each bundle stays an independent implementation, started under the base path /<claim-id>. The shell
owns one loopback address: / shows the feature menu, /<claim-id>/... is forwarded unchanged to that
feature's server, and every HTML page a feature returns gets the shell's navigation bar so a person or
the AI tester can move between features. Features do not share data or state through the shell.
"""
from __future__ import annotations

import contextlib
import html
import http.client
import json
import re
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .bundle_runtime import mountable, validate_web_runtime, web_app_session


# Hop-by-hop headers, and the ones the shell recomputes after it reads the whole response.
_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
        "transfer-encoding", "upgrade", "content-length", "accept-encoding"}
_BODY_OPEN = re.compile(rb"<body\b[^>]*>", re.IGNORECASE)
NAV_MARKER = "data-company-shell"


def _nav(company: str, features: list[dict[str, Any]], current: str | None) -> str:
    links = "".join(
        f'<a href="/{html.escape(f["id"])}/"{" aria-current=page" if f["id"] == current else ""} '
        f'style="color:inherit;text-decoration:{"underline" if f["id"] == current else "none"};margin-right:16px">'
        f'{html.escape(f["title"])}</a>' for f in features)
    return (f'<nav {NAV_MARKER} aria-label="Company app" style="font:14px/1.4 system-ui,sans-serif;'
            f'background:#20262b;color:#fff;padding:8px 16px;display:flex;flex-wrap:wrap;align-items:center;gap:4px">'
            f'<a href="/" style="color:inherit;font-weight:600;text-decoration:none;margin-right:20px">'
            f'{html.escape(company)}</a>{links}</nav>')


def _menu(company: str, features: list[dict[str, Any]]) -> bytes:
    items = "".join(
        f'<li><a href="/{html.escape(f["id"])}/">{html.escape(f["title"])}</a>'
        + (f'<p>{html.escape(f["summary"])}</p>' if f.get("summary") else "") + "</li>" for f in features)
    return (f"<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width'>"
            f"<title>{html.escape(company)}</title><style>body{{margin:0;font:16px/1.5 system-ui,sans-serif}}"
            f"main{{max-width:760px;margin:0 auto;padding:24px 16px}}li{{margin:0 0 16px}}li p{{margin:4px 0 0;color:#555}}"
            f"</style></head><body>{_nav(company, features, None)}<main><h1>{html.escape(company)}</h1>"
            f"<p>Choose a feature.</p><ul>{items}</ul></main></body></html>").encode()


@contextlib.contextmanager
def company_shell(company: str, features: list[dict[str, Any]], *, port: int = 0) -> Iterator[str]:
    """Serve the menu and forward /<id>/... to each feature's url (which ends in /<id>); yield the shell URL."""
    targets = {}
    for feature in features:
        parts = urlsplit(feature["url"])
        if parts.path != f"/{feature['id']}" or parts.hostname != "127.0.0.1":
            raise ValueError("a company feature must run on loopback under /<feature id>")
        targets[feature["id"]] = (parts.hostname, parts.port, f"http://127.0.0.1:{parts.port}")
    menu = _menu(company, features)

    class Shell(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def handle_any(self):
            path = urlsplit(self.path).path
            if path == "/":
                return self.reply(200, [("Content-Type", "text/html; charset=utf-8")], menu)
            first = path.split("/")[1]
            if first not in targets:
                return self.reply(404, [("Content-Type", "text/plain; charset=utf-8")], b"not found")
            if path == f"/{first}":
                return self.reply(308, [("Location", f"/{first}/")], b"")
            host, target_port, origin = targets[first]
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else None
            headers = {k: v for k, v in self.headers.items() if k.lower() not in _HOP}
            headers["Host"] = f"{host}:{target_port}"
            connection = http.client.HTTPConnection(host, target_port, timeout=900)
            try:
                connection.request(self.command, self.path, body, headers)
                response = connection.getresponse()
                data = response.read()
            except OSError as error:
                return self.reply(502, [("Content-Type", "text/plain; charset=utf-8")],
                                  f"feature unavailable: {error}".encode())
            finally:
                connection.close()
            shell_origin = f"http://{self.headers.get('Host') or '127.0.0.1'}"
            out = [(k, v.replace(origin, shell_origin) if k.lower() == "location" else v)
                   for k, v in response.getheaders() if k.lower() not in _HOP]
            if "text/html" in (response.getheader("Content-Type") or "") and self.command != "HEAD":
                bar = _nav(company, features, first).encode()
                match = _BODY_OPEN.search(data)
                data = data[:match.end()] + bar + data[match.end():] if match else bar + data
            self.reply(response.status, out, data, response.reason)

        def reply(self, status, headers, data, reason=None):
            self.send_response(status, reason)
            for key, value in headers:
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = handle_any

    server = ThreadingHTTPServer(("127.0.0.1", port), Shell)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@contextlib.contextmanager
def company_app_session(company: str, features: list[dict[str, Any]], timeout: float, *,
                        path_prefix: Path | None = None, logs: dict[str, Any] | None = None,
                        port: int = 0) -> Iterator[tuple[str, dict[str, Path]]]:
    """Start each mountable bundle under /<id> and the shell in front of them.

    features: [{id, title, manifest, workspace, summary?}]. Yields (shell URL, {id: workspace root}).
    """
    with contextlib.ExitStack() as stack:
        running, roots = [], {}
        for feature in features:
            manifest = json.loads(Path(feature["manifest"]).read_text(encoding="utf-8"))
            if not mountable(validate_web_runtime(manifest.get("runtime"))):
                raise ValueError(f"{feature['id']}: the bundle declares no base_path_argument, "
                                 "so it cannot be mounted in the company app")
            url, root = stack.enter_context(web_app_session(
                Path(feature["manifest"]), timeout, workspace=Path(feature["workspace"]), path_prefix=path_prefix,
                log=(logs or {}).get(feature["id"]), base_path=f"/{feature['id']}"))
            running.append({**feature, "url": url})
            roots[feature["id"]] = root
        shell = stack.enter_context(company_shell(company, running, port=port))
        yield shell, roots


def company_features(registry: dict[str, Any], root: Path, state: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Bound web-app features of a run that the company app can mount, and the claims it leaves out."""
    features, excluded = [], []
    for claim in registry["claims"]:
        bound = claim.get("implementation_result")
        if not bound or not claim.get("web_demo"):
            excluded.append({"claim_id": claim["claim_id"], "reason": "no bound web-app implementation"})
            continue
        manifest = root / bound["candidate_path"]
        if not mountable(json.loads(manifest.read_text(encoding="utf-8")).get("runtime") or {}):
            excluded.append({"claim_id": claim["claim_id"],
                             "reason": "bundle declares no base_path_argument (built before the company app)"})
            continue
        plan = json.loads((root / claim["web_demo"]["plan_path"]).read_text(encoding="utf-8"))
        features.append({"id": claim["claim_id"], "title": plan["title"], "manifest": manifest,
                         "workspace": state / claim["claim_id"]})
    return features, excluded


def check_company_app(registry: dict[str, Any], root: Path, timeout: float = 180) -> dict[str, Any]:
    """Start every mountable bound feature in one shell and load each feature's first page through it.

    A startup check only: each feature's behavior is judged by its own demo evaluation.
    """
    import tempfile
    import time
    import urllib.request
    company = (registry.get("company") or {}).get("name") or "Company app"
    with tempfile.TemporaryDirectory(prefix="replica-company-check-") as temporary:
        features, excluded = company_features(registry, root, Path(temporary))
        record: dict[str, Any] = {
            "checked_at": time.time(), "features": [], "excluded": excluded,
            "note": "Startup check: each mounted feature's first page loads through the shared shell. "
                    "Feature behavior is judged by each claim's demo evaluation.",
        }
        if not features:
            return {**record, "status": "not_assembled"}
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with company_app_session(company, features, timeout) as (shell, _):
                for feature in features:
                    entry = {"claim_id": feature["id"], "path": f"/{feature['id']}/"}
                    try:
                        with opener.open(f"{shell}/{feature['id']}/", timeout=30) as response:
                            body = response.read().decode("utf-8", errors="replace")
                            entry.update(http_status=response.status, shell_navigation=NAV_MARKER in body,
                                         status="loaded" if response.status == 200 else "failed")
                    except OSError as error:
                        entry.update(status="failed", reason=f"{type(error).__name__}: {str(error)[:200]}")
                    record["features"].append(entry)
        except Exception as error:  # A feature that cannot start is a recorded result, not a crash of finish.
            return {**record, "status": "failed", "reason": f"{type(error).__name__}: {str(error)[:300]}"}
    loaded = sum(f["status"] == "loaded" for f in record["features"])
    record["status"] = "assembled" if loaded == len(features) else "partially_assembled" if loaded else "failed"
    return record
