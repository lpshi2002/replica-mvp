"""One web app per company: a shared shell that serves each claim's web-app bundle under its own path.

Each bundle stays an independent implementation, started under the base path /<claim-id>. The shell
owns one loopback address: / shows the feature menu, /<claim-id>/... is forwarded unchanged to that
feature's server, and every HTML page a feature returns gets the shell's stylesheet and sidebar
navigation so a person or the AI tester can move between features. Features do not share data or state
through the shell.
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
SHELL_CSS_PATH = "/_company-shell.css"

# The shell's sidebar and menu, plus plain defaults for a feature's HTML elements. The defaults sit in
# :where() (zero specificity), so a feature's own CSS always wins over them; the sidebar rules do not.
SHELL_CSS = b"""\
:root { --shell-w: 232px; --shell-side: #1e2530; --shell-side-text: #c9d1db; --shell-accent: #0f8a6c;
  --shell-accent-soft: #e2f4ef; --shell-bg: #eef0f3; --shell-surface: #fff; --shell-text: #1b1f24;
  --shell-muted: #646d78; --shell-line: #e0e3e8; }
html:has(> body > nav[data-company-shell]) { padding-left: var(--shell-w); }
nav[data-company-shell] { position: fixed; inset: 0 auto 0 0; z-index: 2147483000; width: var(--shell-w);
  box-sizing: border-box; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; padding: 20px 12px;
  background: var(--shell-side); font: 14px/1.4 system-ui, -apple-system, "Apple SD Gothic Neo", sans-serif; }
nav[data-company-shell] a { color: var(--shell-side-text); text-decoration: none; padding: 9px 12px;
  border-radius: 8px; }
nav[data-company-shell] a:hover { background: rgb(255 255 255 / .06); color: #fff; }
nav[data-company-shell] a:focus-visible { outline: 2px solid #fff; outline-offset: -2px; }
nav[data-company-shell] a[aria-current="page"] { background: var(--shell-accent); color: #fff; font-weight: 600; }
nav[data-company-shell] a.shell-home { color: #fff; font-size: 17px; font-weight: 700; padding-bottom: 16px;
  margin-bottom: 8px; border-bottom: 1px solid rgb(255 255 255 / .1); border-radius: 0; }
@media (max-width: 760px) {
  html:has(> body > nav[data-company-shell]) { padding-left: 0; }
  nav[data-company-shell] { position: sticky; inset: 0 auto auto 0; width: auto; flex-direction: row;
    flex-wrap: wrap; padding: 10px 12px; }
  nav[data-company-shell] a.shell-home { padding-bottom: 9px; margin: 0 8px 0 0; border: 0; }
}
.shell-lead { color: var(--shell-muted); margin-top: -8px; }
.shell-features { list-style: none; padding: 0; display: grid; gap: 10px; }
.shell-features a { display: grid; grid-template-columns: 1fr auto; align-items: center; gap: 2px 16px;
  padding: 16px 20px; background: var(--shell-surface); border-radius: 12px; color: inherit;
  text-decoration: none; box-shadow: 0 1px 2px rgb(0 0 0 / .06); }
.shell-features a::after { content: "Open \\2192"; grid-row: 1 / 3; grid-column: 2; color: var(--shell-accent);
  font-weight: 600; font-size: 14px; }
.shell-features a:hover, .shell-features a:focus-visible { outline: none; box-shadow: 0 0 0 2px var(--shell-accent); }
.shell-features strong { font-size: 16px; }
.shell-features span { color: var(--shell-muted); font-size: 14px; }
:where(html) { background: var(--shell-bg); color: var(--shell-text);
  font: 15px/1.6 system-ui, -apple-system, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif; }
:where(body) { margin: 0; }
:where(main) { display: block; max-width: 960px; padding: 32px 36px 64px; }
:where(h1) { font-size: 24px; line-height: 1.3; margin: 0 0 20px; }
:where(h2) { font-size: 18px; line-height: 1.35; margin: 0 0 14px; }
:where(main > section, main > article, main > form) { background: var(--shell-surface); border-radius: 12px;
  padding: 22px 24px; margin: 0 0 16px; box-shadow: 0 1px 2px rgb(0 0 0 / .06); }
:where(a) { color: var(--shell-accent); }
:where(label) { display: block; font-size: 13px; font-weight: 600; color: #3b434d; margin: 14px 0 6px; }
:where(label:has(> input[type=checkbox], > input[type=radio])) { display: flex; gap: 8px; align-items: center;
  font-size: 14px; font-weight: 400; color: inherit; }
:where(input:not([type=checkbox], [type=radio], [type=file], [type=hidden], [type=submit], [type=button]), textarea, select) {
  box-sizing: border-box; width: 100%; padding: 10px 12px; font: inherit; color: inherit; background: #f7f8fa;
  border: 1px solid var(--shell-line); border-radius: 8px; }
:where(input, textarea, select):focus { outline: none; background: var(--shell-surface);
  border-color: var(--shell-accent); box-shadow: 0 0 0 3px var(--shell-accent-soft); }
:where(button, input[type=submit], input[type=button]) { font: inherit; font-weight: 600; padding: 10px 18px;
  margin: 18px 8px 0 0; cursor: pointer; color: #fff; background: var(--shell-accent); border: 0; border-radius: 8px; }
:where(button, input[type=submit], input[type=button]):hover { filter: brightness(1.1); }
:where(button, input[type=submit], input[type=button]):focus-visible { outline: 3px solid var(--shell-accent-soft); }
:where(button:disabled, input:disabled) { opacity: .5; cursor: not-allowed; }
:where(button.secondary) { color: var(--shell-text); background: #eceff2; }
:where(table) { width: 100%; border-collapse: collapse; }
:where(th) { text-align: left; font-size: 13px; font-weight: 600; color: var(--shell-muted); background: #f7f8fa; }
:where(th, td) { padding: 11px 12px; border-bottom: 1px solid var(--shell-line); vertical-align: top; }
:where([role=status], [role=alert]) { padding: 12px 16px; border-radius: 10px; margin: 0 0 16px; font-weight: 500;
  background: var(--shell-accent-soft); color: #0b5e4a; }
:where([role=alert]) { background: #fdecec; color: #8a1f1f; }
:where(mark) { background: #ffe9b0; padding: 2px 8px; border-radius: 999px; }
:where(blockquote, pre) { margin: 12px 0; padding: 14px 16px; background: #f7f8fa; border-radius: 10px; }
:where(pre) { overflow-x: auto; white-space: pre-wrap; }
:where(img, video, audio) { max-width: 100%; }
:where(small) { color: var(--shell-muted); }
@media (max-width: 760px) {
  :where(main) { padding: 20px 16px 48px; }
  :where(main > section, main > article, main > form) { padding: 16px; }
}
"""
_STYLESHEET = f'<link rel="stylesheet" href="{SHELL_CSS_PATH}">'


def _nav(company: str, features: list[dict[str, Any]], current: str | None, locale: str = "en") -> str:
    links = "".join(
        f'<a href="/{html.escape(f["id"])}/"{" aria-current=page" if f["id"] == current else ""}>'
        f'{html.escape(f["title"])}</a>' for f in features)
    label = "기능 메뉴" if locale == "ko" else "Company app"
    return (f'<nav {NAV_MARKER} aria-label="{label}">'
            f'<a class="shell-home" href="/">{html.escape(company)}</a>{links}</nav>')


def _menu(company: str, features: list[dict[str, Any]], locale: str = "en") -> bytes:
    items = "".join(
        f'<li><a href="/{html.escape(f["id"])}/"><strong>{html.escape(f["title"])}</strong>'
        + (f'<span>{html.escape(f["summary"])}</span>' if f.get("summary") else "") + "</a></li>" for f in features)
    lead = "사용할 기능을 선택하세요." if locale == "ko" else "Choose a feature."
    return (f'<!doctype html><html lang="{html.escape(locale)}"><head><meta charset=utf-8><meta name=viewport content="width=device-width">'
            f"<title>{html.escape(company)}</title>{_STYLESHEET}</head><body>{_nav(company, features, None, locale)}"
            f"<main><h1>{html.escape(company)}</h1><p class=shell-lead>{lead}</p>"
            f"<ul class=shell-features>{items}</ul></main></body></html>").encode()


@contextlib.contextmanager
def company_shell(company: str, features: list[dict[str, Any]], *, port: int = 0,
                  locale: str = "en") -> Iterator[str]:
    """Serve the menu and forward /<id>/... to each feature's url (which ends in /<id>); yield the shell URL."""
    if locale not in {"en", "ko"}:
        raise ValueError("company app locale must be en or ko")
    targets = {}
    for feature in features:
        parts = urlsplit(feature["url"])
        if parts.path != f"/{feature['id']}" or parts.hostname != "127.0.0.1":
            raise ValueError("a company feature must run on loopback under /<feature id>")
        targets[feature["id"]] = (parts.hostname, parts.port, f"http://127.0.0.1:{parts.port}")
    menu = _menu(company, features, locale)
    css = SHELL_CSS.replace(b'Open \\2192', '열기 \\2192'.encode()) if locale == "ko" else SHELL_CSS

    class Shell(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def handle_any(self):
            path = urlsplit(self.path).path
            if path == "/":
                return self.reply(200, [("Content-Type", "text/html; charset=utf-8")], menu)
            if path == SHELL_CSS_PATH:
                return self.reply(200, [("Content-Type", "text/css; charset=utf-8")], css)
            first = path.split("/")[1]
            if first not in targets:
                return self.reply(404, [("Content-Type", "text/plain; charset=utf-8")],
                                  "페이지를 찾을 수 없습니다.".encode() if locale == "ko" else b"not found")
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
                                  ("기능에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요." if locale == "ko"
                                   else f"feature unavailable: {error}").encode())
            finally:
                connection.close()
            shell_origin = f"http://{self.headers.get('Host') or '127.0.0.1'}"
            out = [(k, v.replace(origin, shell_origin) if k.lower() == "location" else v)
                   for k, v in response.getheaders() if k.lower() not in _HOP]
            if "text/html" in (response.getheader("Content-Type") or "") and self.command != "HEAD":
                bar = (_STYLESHEET + _nav(company, features, first, locale)).encode()
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
                        port: int = 0, locale: str = "en") -> Iterator[tuple[str, dict[str, Path]]]:
    """Start each mountable bundle under /<id> and the shell in front of them.

    features: [{id, title, manifest, workspace, summary?}]. Yields (shell URL, {id: workspace root}).
    """
    with contextlib.ExitStack() as stack:
        running, roots = [], {}
        for feature in features:
            if feature.get("manifest_sha256"):
                from .web_checkpoint import digest
                if digest(Path(feature["manifest"])) != feature["manifest_sha256"]:
                    raise ValueError("bound feature manifest changed before startup")
            manifest = json.loads(Path(feature["manifest"]).read_text(encoding="utf-8"))
            if not mountable(validate_web_runtime(manifest.get("runtime"))):
                raise ValueError(f"{feature['id']}: the bundle declares no base_path_argument, "
                                 "so it cannot be mounted in the company app")
            url, root = stack.enter_context(web_app_session(
                Path(feature["manifest"]), timeout, workspace=Path(feature["workspace"]), path_prefix=path_prefix,
                log=(logs or {}).get(feature["id"]), base_path=f"/{feature['id']}"))
            running.append({**feature, "url": url})
            roots[feature["id"]] = root
        shell = stack.enter_context(company_shell(company, running, port=port, locale=locale))
        yield shell, roots


def company_features(registry: dict[str, Any], root: Path, state: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Bound web-app features of a run that the company app can mount, and the claims it leaves out."""
    from .agent_harness import _validate_bound_artifact
    from .bundle_runtime import validate_bundle_files
    features, excluded = [], []
    for claim in registry["claims"]:
        bound = claim.get("implementation_result")
        if not bound or not claim.get("web_demo"):
            excluded.append({"claim_id": claim["claim_id"], "reason": "no bound web-app implementation"})
            continue
        try:
            manifest = _validate_bound_artifact(root, {
                "path": bound["candidate_path"], "sha256": bound["candidate_sha256"]}, label=claim["claim_id"])
            value = validate_bundle_files(manifest)
            if not mountable(value.get("runtime") or {}):
                raise ValueError("bundle declares no base_path_argument (built before the company app)")
            plan = json.loads((root / claim["web_demo"]["plan_path"]).read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError, TypeError) as error:
            excluded.append({"claim_id": claim["claim_id"], "reason": str(error)})
            continue
        features.append({"id": claim["claim_id"], "title": plan["title"], "manifest": manifest,
                         "manifest_sha256": bound["candidate_sha256"], "workspace": state / claim["claim_id"]})
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
