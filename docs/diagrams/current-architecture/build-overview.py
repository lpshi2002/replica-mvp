"""Package the delivered Archify viewers into one offline HTML without altering them."""
import base64
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
documents = {}
for name in ("architecture", "workflow"):
    content = (ROOT / f"{name}.html").read_bytes()
    receipt = json.loads((ROOT / f"{name}.delivery.json").read_text())
    assert hashlib.sha256(content).hexdigest() == receipt["artifact"]["sha256"]
    documents[name] = base64.b64encode(content).decode("ascii")

template = r'''<!DOCTYPE html>
<html lang="ko" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark light">
<title>Replica MVP · 아키텍처와 워크플로</title>
<style>
*{box-sizing:border-box}
:root{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color-scheme:dark;--bg:#030817;--text:#edf3fc;--muted:#95a4ba;--line:#273449;--selected:#143c4c;--accent:#68deef}
:root[data-theme="light"]{color-scheme:light;--bg:#f7f9fc;--text:#142035;--muted:#516279;--line:#d9e2ef;--selected:#e0f5fa;--accent:#087e95}
html,body{margin:0;width:100%;height:100%;background:var(--bg);color:var(--text)}
body{height:100dvh;display:flex;flex-direction:column}
.topbar{flex:none;display:flex;align-items:center;justify-content:space-between;gap:20px;padding:10px 24px;border-bottom:1px solid var(--line);min-height:62px}
.identity{display:flex;align-items:baseline;gap:14px;min-width:0}
.identity strong{font-size:16px;white-space:nowrap}.identity span{color:var(--muted);font-size:12px}
[role="tablist"]{display:flex;gap:4px;padding:3px;border:1px solid var(--line);border-radius:11px;flex:none}
[role="tab"]{font:inherit;font-size:13px;font-weight:650;border:0;background:transparent;color:var(--muted);padding:8px 18px;border-radius:7px;cursor:pointer}
[role="tab"][aria-selected="true"]{background:var(--selected);color:var(--accent)}
[role="tab"]:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
main{flex:1;min-height:0;display:flex;flex-direction:column}
[role="tabpanel"]{flex:1;min-height:0}
[hidden]{display:none!important}
iframe{display:block;width:100%;height:100%;border:0;background:var(--bg)}
noscript{padding:24px}
@media(max-width:600px){.topbar{padding:10px 12px;gap:10px;flex-wrap:wrap}.identity span{display:none}[role="tab"]{padding:8px 14px}}
</style>
</head>
<body>
<header class="topbar">
  <div class="identity"><strong>Replica MVP</strong><span>현재 코드 · 아키텍처와 실행 흐름</span></div>
  <nav role="tablist" aria-label="다이어그램 선택">
    <button id="tab-architecture" role="tab" aria-controls="panel-architecture" aria-selected="true" tabindex="0" data-view="architecture">아키텍처</button>
    <button id="tab-workflow" role="tab" aria-controls="panel-workflow" aria-selected="false" tabindex="-1" data-view="workflow">워크플로</button>
  </nav>
</header>
<main>
  <section id="panel-architecture" role="tabpanel" aria-labelledby="tab-architecture"><iframe id="view-architecture" title="Replica MVP 전체 아키텍처" allow="fullscreen" allowfullscreen></iframe></section>
  <section id="panel-workflow" role="tabpanel" aria-labelledby="tab-workflow" hidden><iframe id="view-workflow" title="Replica MVP 전체 워크플로" allow="fullscreen" allowfullscreen></iframe></section>
</main>
<noscript>두 다이어그램을 표시하려면 JavaScript를 켜 주세요.</noscript>
<script id="embedded-diagrams" type="application/json">__DOCUMENTS__</script>
<script>
(() => {
  const documents = JSON.parse(document.getElementById('embedded-diagrams').textContent);
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  const loaded = new Set();
  let active = 'architecture';
  function syncTheme(name) {
    if (name !== active) return;
    const root = document.getElementById('view-' + name).contentDocument?.documentElement;
    if (root?.dataset.theme) document.documentElement.dataset.theme = root.dataset.theme;
  }
  for (const name of Object.keys(documents)) {
    const frame = document.getElementById('view-' + name);
    frame.addEventListener('load', () => {
      const root = frame.contentDocument?.documentElement;
      if (!root) return;
      syncTheme(name);
      new MutationObserver(() => syncTheme(name)).observe(root, {attributes:true, attributeFilter:['data-theme']});
    });
  }
  function select(name, focus = false) {
    if (!Object.hasOwn(documents, name)) name = 'architecture';
    active = name;
    for (const tab of tabs) {
      const selected = tab.dataset.view === name;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
      document.getElementById(tab.getAttribute('aria-controls')).hidden = !selected;
      if (selected && focus) tab.focus();
    }
    if (!loaded.has(name)) {
      const bytes = Uint8Array.from(atob(documents[name]), char => char.charCodeAt(0));
      document.getElementById('view-' + name).srcdoc = new TextDecoder().decode(bytes);
      loaded.add(name);
    }
    syncTheme(name);
    history.replaceState(null, '', '#' + name);
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => select(tab.dataset.view));
    tab.addEventListener('keydown', event => {
      let target;
      if (event.key === 'ArrowRight') target = (index + 1) % tabs.length;
      if (event.key === 'ArrowLeft') target = (index + tabs.length - 1) % tabs.length;
      if (event.key === 'Home') target = 0;
      if (event.key === 'End') target = tabs.length - 1;
      if (target !== undefined) {event.preventDefault();select(tabs[target].dataset.view, true);}
    });
  });
  addEventListener('hashchange', () => select(location.hash.slice(1)));
  select(location.hash.slice(1));
})();
</script>
</body>
</html>
'''

(ROOT / "overview.html").write_text(
    template.replace("__DOCUMENTS__", json.dumps(documents)), encoding="utf-8"
)
print(ROOT / "overview.html")
