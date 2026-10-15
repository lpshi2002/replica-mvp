"""Guarded multi-action tester plans for the web demo.

The tester may return several atomic actions observed on one page. The runner
performs them one by one as real UI actions and stops the rest of the plan as
soon as the page stops matching what the tester saw: a different node behind a
ref, a value the app did not accept, a new field, changed text, navigation, or
a dialog, alert or page error. The tester then gets a fresh observation.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

FIELD_ACTIONS = {"fill", "select", "upload", "check", "uncheck"}
SUBMISSIONS = {"click", "press"}
WAITS = {"wait", "wait_for"}
TERMINAL = {"done", "give_up"}
PLAN_ACTIONS = FIELD_ACTIONS | SUBMISSIONS | WAITS | TERMINAL | {"read"}
_NEEDS_REF = FIELD_ACTIONS | {"click", "read"}
_SIGNAL_TEXT_LIMIT = 2000
_PAGE_TEXT_LIMIT = 8000

PLAN_INSTRUCTION = (
    "Return the next actions for the current page as a plan in actions, each referring to an element by its ref "
    "on this page. A plan may fill several visible fields and set selects, checkboxes or uploads, then end with "
    "at most one click or press, which may be followed only by one wait or wait_for for its result. Plan only "
    "actions on elements already on this page; anything that appears later is shown in a new observation. "
    "done or give_up must be the only action of its plan, and read must be its last action. The runner performs "
    "the actions in order and stops a plan early when the page changes unexpectedly, a value is not accepted, "
    "or a message or dialog appears; last_plan then lists the actions that were not performed and "
    "previous_actions the ones that were, so never repeat a click or press that was already performed. "
    "A fill may be followed by press on the same field. A wait_for must refer to text actually observed "
    "on the UI; otherwise use a bounded wait and inspect the next observation. "
)

# Transient alerts can appear and vanish between two observations; record them as they appear.
SIGNAL_SCRIPT = """(() => {
  if (window.__replicaSignals) return;
  window.__replicaSignals = [];
  const seen = new WeakMap();
  const selector = '[role=alert], [role=alertdialog], [aria-live=assertive], dialog[open]';
  const scan = () => {
    for (const el of document.querySelectorAll(selector)) {
      const text = (el.innerText || el.textContent || '').trim();
      if (text && seen.get(el) !== text) {
        seen.set(el, text);
        window.__replicaSignals.push({kind: el.getAttribute('role') || (el.tagName === 'DIALOG' ? 'dialog' : 'live'),
                                      text: text.slice(0, %d)});
      }
    }
  };
  new MutationObserver(scan).observe(document, {subtree: true, childList: true, characterData: true,
    attributes: true, attributeFilter: ['role', 'aria-live', 'open', 'hidden', 'style', 'class']});
})();""" % _SIGNAL_TEXT_LIMIT
_DRAIN_SCRIPT = "() => (window.__replicaSignals || []).splice(0)"

# Remember the real node behind each ref, so a re-rendered node with the same ref, role and name is not trusted.
REGISTER_SCRIPT = """() => {
  window.__replicaNodes = new Map();
  document.querySelectorAll('[data-replica-ref]').forEach(
    e => window.__replicaNodes.set(Number(e.getAttribute('data-replica-ref')), e));
}"""

# Observe between plan steps without renumbering refs.
PEEK_SCRIPT = """() => {
  const selector = 'a[href], button, input, select, textarea, summary, [role=button], [role=link], '
    + '[role=checkbox], [role=tab], [role=menuitem], [contenteditable=true]';
  const visible = el => {
    if (el.tagName === 'INPUT' && el.type === 'file') return el.isConnected;
    const box = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return el.isConnected && el.type !== 'hidden' && style.display !== 'none' && style.visibility !== 'hidden'
      && !(box.width === 0 && box.height === 0);
  };
  const label = el => ((el.labels && el.labels[0] && el.labels[0].innerText) || el.getAttribute('aria-label')
    || el.getAttribute('placeholder') || el.getAttribute('title') || el.innerText || el.getAttribute('value')
    || el.getAttribute('name') || '').trim().slice(0, 200);
  const map = window.__replicaNodes || new Map();
  const hash = text => { let h = 0; for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) | 0;
    return h; };
  const known = new Set(map.values());
  const elements = [], missing = [], fresh = [];
  for (const [ref, el] of map) {
    if (!visible(el)) { missing.push(ref); continue; }
    const editable = ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) && el.type !== 'file'
      && el.type !== 'password';
    elements.push({ref, tag: el.tagName.toLowerCase(), type: el.getAttribute('type'), label: label(el),
      value: editable ? String(el.value).slice(0, 200) : null,
      value_length: editable ? String(el.value).length : null,
      value_truncated: editable && String(el.value).length > 200,
      value_hash: editable ? hash(String(el.value)) : null,
      checked: ['checkbox', 'radio'].includes(el.type) ? el.checked : null,
      disabled: !!el.disabled, readonly: !!el.readOnly, required: !!el.required,
      href: el.getAttribute('href'), aria: Object.fromEntries([...el.attributes]
        .filter(a => a.name.startsWith('aria-')).map(a => [a.name, a.value])),
      options: el.tagName === 'SELECT' ? [...el.options].map(o => ({text: o.text, value: o.value,
        disabled: o.disabled})) : null,
      selected: el.tagName === 'SELECT' ? [...el.selectedOptions].map(o => o.value) : null,
      files: el.files ? [...el.files].map(f => f.name) : null});
  }
  for (const el of document.querySelectorAll(selector)) {
    if (!known.has(el) && visible(el) && fresh.length < 20) {
      fresh.push({tag: el.tagName.toLowerCase(), type: el.getAttribute('type'), label: label(el)});
    }
  }
  const text = document.body ? document.body.innerText : '';
  return {url: location.href, title: document.title, text: text.slice(0, %d), text_hash: hash(text),
          elements, new_elements: fresh, missing_refs: missing};
}""" % _PAGE_TEXT_LIMIT

_STATE_SCRIPT = """(ref) => {
  const map = window.__replicaNodes;
  const nodes = document.querySelectorAll(`[data-replica-ref="${ref}"]`);
  const node = map ? map.get(ref) : undefined;
  let identity = 'ok';
  if (!map) identity = 'page_replaced';
  else if (!node || !node.isConnected) identity = 'node_replaced';
  else if (nodes.length === 0) identity = 'target_missing';
  else if (nodes.length > 1) identity = 'target_ambiguous';
  else if (nodes[0] !== node) identity = 'node_replaced';
  if (!node || !node.isConnected) return {identity};
  const field = ['INPUT', 'TEXTAREA', 'SELECT'].includes(node.tagName);
  return {identity, password: node.type === 'password',
    value: field ? String(node.value) : (node.isContentEditable ? node.innerText : null),
    checked: ['checkbox', 'radio'].includes(node.type) ? node.checked : null,
    aria_checked: node.getAttribute('aria-checked'),
    selected: node.tagName === 'SELECT' ? [...node.selectedOptions].map(o => ({text: o.text.trim(), value: o.value})) : null,
    files: node.files ? [...node.files].map(f => f.name) : null};
}"""


class PageSignals:
    """Record dialogs, page errors and transient alerts; dismiss dialogs the way Playwright does by default."""

    def __init__(self, page):
        self.page, self.pending = page, []

    def __enter__(self) -> "PageSignals":
        self.page.on("dialog", self._dialog)
        self.page.on("pageerror", self._error)
        self.page.on("console", self._console)
        self.page.on("popup", self._popup)
        return self

    def __exit__(self, *exc) -> None:
        self.page.remove_listener("dialog", self._dialog)
        self.page.remove_listener("pageerror", self._error)
        self.page.remove_listener("console", self._console)
        self.page.remove_listener("popup", self._popup)

    def _dialog(self, dialog) -> None:
        self.pending.append({"kind": "dialog", "type": dialog.type, "text": dialog.message[:_SIGNAL_TEXT_LIMIT]})
        try:
            dialog.dismiss()
        except Exception:  # The page may already be gone; the signal is still recorded.
            pass

    def _error(self, error) -> None:
        self.pending.append({"kind": "page_error", "text": str(error)[:_SIGNAL_TEXT_LIMIT]})

    def _console(self, message) -> None:
        if message.type == "error":
            self.pending.append({"kind": "console_error", "text": message.text[:_SIGNAL_TEXT_LIMIT]})

    def _popup(self, page) -> None:
        self.pending.append({"kind": "popup", "text": page.url[:_SIGNAL_TEXT_LIMIT]})

    def drain(self) -> list[dict[str, Any]]:
        found, self.pending = self.pending, []
        try:
            return found + self.page.evaluate(_DRAIN_SCRIPT)
        except Exception as error:  # A navigating or closed page cannot report its in-page alerts.
            return found + [{"kind": "signal_read_failed", "text": f"{type(error).__name__}: {str(error)[:300]}"}]


def read_plan(answer: Any, elements: list[dict[str, Any]], remaining: int,
              uploads: dict[str, Path]) -> tuple[list[dict[str, Any]], str | None]:
    """Return the plan's atomic actions and why it is invalid; a single action is a one-action plan."""
    if isinstance(answer, dict) and "actions" in answer:
        raw = answer["actions"]
    elif isinstance(answer, dict) and "action" in answer:
        raw = [answer]
    else:
        return [], "the answer has no actions"
    if not isinstance(raw, list) or not raw or not all(isinstance(a, dict) for a in raw):
        return [], "actions must be a non-empty list of action objects"
    actions = [{k: a.get(k) for k in ("action", "ref", "value", "reason")} for a in raw]
    return actions, _plan_problem(actions, elements, remaining, uploads)


def _plan_problem(actions: list[dict[str, Any]], elements: list[dict[str, Any]], remaining: int,
                  uploads: dict[str, Path]) -> str | None:
    kinds = [a["action"] for a in actions]
    last = len(kinds) - 1
    if len(kinds) > remaining:
        return f"the plan has {len(kinds)} actions but only {remaining} actions remain"
    if any(not isinstance(k, str) or k not in PLAN_ACTIONS for k in kinds):
        return "the plan contains an unknown action"
    if TERMINAL & set(kinds) and len(kinds) > 1:
        return "done or give_up must be the only action of its plan"
    submissions = [i for i, k in enumerate(kinds) if k in SUBMISSIONS]
    if len(submissions) > 1:
        return "a plan may contain at most one click or press"
    if submissions and submissions[0] != last and not (submissions[0] == last - 1 and kinds[last] in WAITS):
        return "the click or press must end the plan, optionally followed by one wait"
    if any(k in WAITS | {"read"} and i != last for i, k in enumerate(kinds)):
        return "wait, wait_for and read may only end a plan"
    refs = {e["ref"] for e in elements}
    used: dict[int, str] = {}
    for number, action in enumerate(actions, 1):
        kind, ref, value = action["action"], action["ref"], action["value"]
        if kind in _NEEDS_REF or (kind == "press" and ref is not None):
            if type(ref) is not int or ref not in refs:
                return f"action {number} names ref {ref!r}, which is not on the observed page"
            if ref in used and not (kind == "press" and used[ref] == "fill"):
                return f"the plan uses ref {ref} more than once"
            used[ref] = kind
        if kind in {"fill", "select"} and not isinstance(value, str):
            return f"action {number} ({kind}) needs a string value"
        if kind == "upload" and (not isinstance(value, str) or value not in uploads):
            return f"action {number} must upload one of the listed upload files"
        if kind in WAITS and not _valid_wait(kind, value):
            return f"action {number} has an invalid {kind} value"
    return None


def _valid_wait(kind: str, value: Any) -> bool:
    try:
        if kind == "wait":
            seconds = float(value or 2)
        else:
            condition = json.loads(value)
            if (not isinstance(condition, dict) or not isinstance(condition.get("text"), str) or not condition["text"]
                    or condition.get("state") not in {"present", "absent"}):
                return False
            seconds = float(condition.get("seconds", 120))
    except (TypeError, ValueError):
        return False
    return math.isfinite(seconds) and seconds >= 0


def target_state(page, ref: Any) -> dict[str, Any]:
    try:
        return page.evaluate(_STATE_SCRIPT, ref)
    except Exception as error:
        return {"identity": "observation_failed", "error": f"{type(error).__name__}: {str(error)[:300]}"}


def peek(page) -> dict[str, Any] | None:
    """Observe the page between plan steps without renumbering refs; None when the page cannot be read."""
    try:
        return page.evaluate(PEEK_SCRIPT)
    except Exception:
        return None


def identity_stop(page, action: dict[str, Any]) -> dict[str, Any] | None:
    """Stop when the node behind the next action's ref is no longer the node the tester observed."""
    if action["ref"] is None or action["action"] not in _NEEDS_REF | {"press"}:
        return None
    state = target_state(page, action["ref"])
    if state["identity"] != "ok":
        return {"reason": state["identity"], "detail": f"ref {action['ref']} no longer names the observed element"}
    return None


def postcondition(action: dict[str, Any], state: dict[str, Any]) -> dict[str, Any] | None:
    """Compare a field's full state after an action with what the action asked for."""
    kind, value = action["action"], action["value"]
    if kind not in FIELD_ACTIONS:
        return None
    if "value" not in state:
        return {"status": "unknown", "detail": "the element is no longer on the page"}
    if kind == "fill":
        # Text fields store line breaks as \n; anything else the app did not keep is a rejected value.
        expected, actual = (value or "").replace("\r\n", "\n").replace("\r", "\n"), state["value"] or ""
        result = {"status": "ok" if actual == expected else "mismatch",
                  "expected_length": len(expected), "actual_length": len(actual)}
        if result["status"] == "mismatch" and not state["password"]:
            result["actual"] = actual
        return result
    if kind == "select":
        selected = state["selected"] or []
        return {"status": "ok" if any(value in (o["text"], o["value"]) for o in selected) else "mismatch",
                "actual": selected}
    if kind == "upload":
        files = state["files"] or []
        return {"status": "ok" if Path(value).name in files else "mismatch", "actual": files}
    checked = state["checked"] if state["checked"] is not None else state["aria_checked"] == "true"
    return {"status": "ok" if checked == (kind == "check") else "mismatch", "actual": checked}


def observation_stop(before: dict[str, Any] | None, after: dict[str, Any] | None,
                     action: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Reject changes since an observation, allowing only the requested field value change."""
    if before is None or after is None:
        return {"reason": "observation_failed", "detail": "the page could not be observed"}
    if before["url"] != after["url"]:
        return {"reason": "url_changed", "detail": after["url"]}
    if after["new_elements"] != before["new_elements"]:
        return {"reason": "new_field", "detail": after["new_elements"]}
    if after["missing_refs"] != before["missing_refs"]:
        return {"reason": "element_removed", "detail": after["missing_refs"]}
    if (after["text_hash"], after["title"]) != (before["text_hash"], before["title"]):
        return {"reason": "text_changed", "detail": "page text changed since the observation"}
    fields = {e["ref"]: e for e in before["elements"]}
    for element in after["elements"]:
        prior = fields.get(element["ref"], {})
        allowed = set()
        if action and action["action"] in FIELD_ACTIONS and element["ref"] == action["ref"]:
            allowed = {"value", "value_hash", "value_length", "value_truncated", "checked", "selected", "files"}
        keys = set(prior) | set(element)
        changed = [k for k in keys - allowed if prior.get(k) != element.get(k)]
        # ARIA checked is the expected effect of setting a custom checkbox; other ARIA changes aren't.
        if action and action["action"] in {"check", "uncheck"} and element["ref"] == action["ref"]:
            if {k: v for k, v in prior.get("aria", {}).items() if k != "aria-checked"} == {
                    k: v for k, v in element.get("aria", {}).items() if k != "aria-checked"}:
                changed = [k for k in changed if k != "aria"]
        if changed:
            return {"reason": "field_changed", "detail": {"ref": element["ref"], "properties": sorted(changed)}}
    return None


def change_stop(action: dict[str, Any], error: str | None, effect: dict[str, Any] | None,
                signals: list[dict[str, Any]], start_url: str, url: str, before: dict[str, Any] | None,
                after: dict[str, Any] | None) -> dict[str, Any] | None:
    """Why the rest of a plan must not run after this action, or None."""
    if error:
        return {"reason": "action_failed", "detail": error}
    if url != start_url:
        return {"reason": "url_changed", "detail": url}
    if signals:
        return {"reason": "signal", "detail": signals}
    if effect and effect["status"] != "ok":
        return {"reason": "postcondition_mismatch", "detail": effect}
    if action["action"] in SUBMISSIONS:
        return None  # A submission is expected to change the page; only a trailing wait can follow.
    return observation_stop(before, after, action)


def plan_stats(plans: list[dict[str, Any]]) -> dict[str, Any]:
    stops: dict[str, int] = {}
    for plan in plans:
        if plan["stop"]:
            stops[plan["stop"]["reason"]] = stops.get(plan["stop"]["reason"], 0) + 1
    return {"plans": len(plans), "rejected": sum(p["status"] == "rejected" for p in plans),
            "stopped": sum(p["status"] == "stopped" for p in plans),
            "planned_actions": sum(p["size"] for p in plans if p["status"] != "rejected"),
            "performed_actions": sum(p["performed"] for p in plans),
            "cancelled_actions": sum(p["size"] - p["performed"] for p in plans if p["status"] == "stopped"),
            "multi_action_plans": sum(p["size"] > 1 for p in plans if p["status"] != "rejected"),
            "stop_reasons": stops}
