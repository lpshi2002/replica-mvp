"""Token usage of agent sessions read from the runtimes' own session logs.

Claude Code writes one JSONL transcript per session (`<projects>/<project>/<id>.jsonl`)
and one per subagent (`.../subagents/agent-<id>.jsonl`); every assistant message
carries `usage` and `model`, and one message can appear on several lines, so lines
are counted once per message id. Codex writes `rollout-...-<id>.jsonl` with a
cumulative `token_count` event; its last value is the session total.
An agent whose log cannot be found is reported as unknown, never as zero.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _claude_root() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "projects"


def _codex_root() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "sessions"


def _add(total: dict[str, int], usage: dict[str, Any]) -> None:
    for key, value in usage.items():
        if type(value) is int:
            total[key] = total.get(key, 0) + value


def _claude_transcript(path: Path) -> dict[str, Any]:
    messages: dict[str, dict[str, Any]] = {}
    models, first, last = set(), None, None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        message = entry.get("message") if isinstance(entry, dict) else None
        if entry.get("type") != "assistant" or not isinstance(message, dict) or not isinstance(message.get("usage"), dict):
            continue
        if message.get("model") == "<synthetic>":
            continue  # Client-generated notices, not model calls.
        # The last line of a message holds its final usage.
        messages[message.get("id") or entry.get("uuid") or str(len(messages))] = message["usage"]
        if message.get("model"):
            models.add(message["model"])
        stamp = entry.get("timestamp")
        if isinstance(stamp, str):
            first, last = first or stamp, stamp
    usage: dict[str, int] = {}
    for item in messages.values():
        _add(usage, item)
    return {"usage": usage, "messages": len(messages), "models": sorted(models), "first_at": first, "last_at": last}


def _codex_rollout(path: Path) -> dict[str, Any]:
    usage, models, first, last = None, set(), None, None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        stamp = entry.get("timestamp")
        if isinstance(stamp, str):
            first, last = first or stamp, stamp
        payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
        if isinstance(payload.get("model"), str):
            models.add(payload["model"])
        info = payload.get("info") if payload.get("type") == "token_count" else None
        if isinstance(info, dict) and isinstance(info.get("total_token_usage"), dict):
            usage = {k: v for k, v in info["total_token_usage"].items() if type(v) is int}
    return {"usage": usage, "messages": None, "models": sorted(models), "first_at": first, "last_at": last}


def agent_usage(agent_id: Any, runtime: str, exclude: frozenset[str] = frozenset()) -> dict[str, Any]:
    """Usage of one recorded agent session, including a Claude session's own subagents.

    Subagents named in `exclude` are recorded under another role and are left out here,
    so a parent session and its recorded children are not counted twice.
    """
    unknown = {"agent_id": agent_id, "runtime": runtime, "status": "unknown", "usage": None, "models": [],
               "sources": [], "basis": "No session log was found for this agent id."}
    if not isinstance(agent_id, str) or not agent_id or "/" in agent_id or agent_id in {".", ".."}:
        return {**unknown, "basis": "The recorded agent id cannot name a session log."}
    if runtime == "claude":
        root = _claude_root()
        name = agent_id.removeprefix("agent-")
        sessions = sorted(root.glob(f"*/{name}.jsonl")) + sorted(root.glob(f"*/*/subagents/agent-{name}.jsonl"))
        if not sessions:
            return unknown
        excluded = {f"agent-{name.removeprefix('agent-')}" for name in exclude}
        files = sessions + sorted(p for s in sessions if s.parent.parent == root
                                  for p in (s.parent / s.stem / "subagents").glob("agent-*.jsonl")
                                  if p.stem not in excluded)
        usage: dict[str, int] = {}
        models, messages, first, last = set(), 0, None, None
        for path in files:
            part = _claude_transcript(path)
            _add(usage, part["usage"])
            models |= set(part["models"])
            messages += part["messages"]
            first = min(filter(None, (first, part["first_at"])), default=None)
            last = max(filter(None, (last, part["last_at"])), default=None)
        if not messages:
            return {**unknown, "sources": [str(p) for p in files],
                    "basis": "The Claude Code session log has no assistant message with usage."}
        return {"agent_id": agent_id, "runtime": runtime, "status": "measured", "usage": usage,
                "models": sorted(models), "messages": messages, "first_at": first, "last_at": last,
                "sources": [str(p) for p in files],
                "basis": ("Claude Code session transcript usage, counted once per message id; includes the session's "
                          "subagents except those recorded under another role.")}
    if runtime == "codex":
        files = sorted(_codex_root().glob(f"**/rollout-*{agent_id}.jsonl"))
        if not files:
            return unknown
        part = _codex_rollout(files[-1])
        if part["usage"] is None:
            return {**unknown, "sources": [str(files[-1])], "basis": "The Codex session log has no token_count event."}
        return {"agent_id": agent_id, "runtime": runtime, "status": "measured", **part, "sources": [str(files[-1])],
                "basis": "Last cumulative token_count of the Codex session log."}
    return {**unknown, "basis": f"Unsupported agent runtime {runtime!r}."}


def sessions_usage(sessions: list[dict[str, Any]], runtime: str,
                   exclude: frozenset[str] = frozenset()) -> dict[str, Any]:
    """Per-role usage for recorded sessions; a role total sums only measured sessions."""
    roles: dict[str, dict[str, Any]] = {}
    for session in sessions:
        measured = agent_usage(session.get("agent_id"), session.get("runtime") or runtime, exclude)
        role = roles.setdefault(session["role"], {"sessions": [], "usage": {}, "measured": 0, "unknown": 0, "models": []})
        role["sessions"].append(measured)
        if measured["status"] == "measured":
            role["measured"] += 1
            _add(role["usage"], measured["usage"])
            role["models"] = sorted(set(role["models"]) | set(measured["models"]))
        else:
            role["unknown"] += 1
    return roles
