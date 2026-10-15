"""Per-call receipts for local model CLI calls and their cost summary.

Every call leaves one directory under a receipts root with its raw stdout and
stderr, start and end records, and the phase it served. Calls made by the
runner (AI tester, judge) and calls made inside a running Replica (through PATH
wrappers) share this format, so one summary covers both without double counting.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any


METERED_TOOLS = ("claude", "codex")
_RAW_LIMIT = 4_000_000
# A run directory holding this file has hit the shared account's usage limit; no further model
# call is sent from that run, including calls the Replica itself makes through the metering wrapper.
LIMIT_GATE_NAME = "usage-limit.json"
_LIMIT_PATTERN = (r"hit your (?:session |usage |weekly |daily |monthly )?limit|usage limit|rate[ _-]?limit"
                  r"|too many requests|quota exceeded|insufficient_quota")
_LIMIT_TEXT = re.compile(_LIMIT_PATTERN, re.IGNORECASE)


class ModelUsageLimitError(RuntimeError):
    """The shared model account refused or would refuse the call: an environment stop, not a Replica defect."""


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def new_call_dir(receipts: Path) -> Path:
    directory = receipts / f"{time.time_ns()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    directory.mkdir(parents=True)
    return directory


def _envelopes(stdout: bytes) -> tuple[str, list[Any]]:
    text = stdout.decode("utf-8", errors="replace").strip()
    try:
        return "json", [json.loads(text)]
    except ValueError:
        envelopes = []
        for line in text.splitlines():
            try:
                envelopes.append(json.loads(line))
            except ValueError:
                continue
        return ("jsonl" if envelopes else "unparsed"), envelopes


def usage_limit_message(stdout: bytes, stderr: bytes = b"") -> str | None:
    """The CLI's own words when the account's usage or rate limit refused the call, else None.

    The Claude CLI reports the limit in its stdout JSON envelope and may leave stderr empty.
    """
    for event in _envelopes(stdout)[1]:
        if not isinstance(event, dict):
            continue
        result = event.get("result") if isinstance(event.get("result"), str) else ""
        if event.get("api_error_status") == 429 or (event.get("is_error") and _LIMIT_TEXT.search(result)):
            return (result or "HTTP 429").strip()[:300]
        if event.get("type") in {"turn.failed", "error"}:
            detail = json.dumps(event.get("error") or event.get("message") or event, ensure_ascii=False)
            if _LIMIT_TEXT.search(detail):
                return detail[:300]
    for line in reversed(stderr.decode("utf-8", errors="replace").splitlines()):
        if _LIMIT_TEXT.search(line):
            return line.strip()[:300]
    return None


def _error_text(stdout: bytes, stderr: bytes) -> str:
    """The CLI's error words for a failed call: stderr, or the envelope's result when stderr is empty."""
    text = stderr.decode("utf-8", errors="replace").strip()
    if not text:
        text = " ".join(str(e.get("result")) for e in _envelopes(stdout)[1]
                        if isinstance(e, dict) and isinstance(e.get("result"), str))
    return text[-500:]


def read_limit_gate(gate: Path | None) -> dict[str, Any] | None:
    if gate is None or not gate.exists():
        return None
    try:
        return json.loads(gate.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"message": "usage limit gate is present"}


def trip_limit_gate(gate: Path | None, info: dict[str, Any]) -> None:
    """Record the first usage-limit stop of a run; later stops keep the first record."""
    if gate is None:
        return
    try:
        handle = os.open(gate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        return
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        json.dump({"kind": "provider_usage_limit", "detected_at": time.time(), **info}, stream, ensure_ascii=False)


def parse_cli_output(stdout: bytes) -> dict[str, Any]:
    """Read usage, observed models and the CLI's own list-price estimate from raw output."""
    parsed: dict[str, Any] = {"format": "unparsed", "usage": None, "models": [], "cost_usd": None,
                              "cost_basis": None, "is_error": None}
    parsed["format"], envelopes = _envelopes(stdout)
    for event in envelopes:
        if not isinstance(event, dict):
            continue
        # Claude CLI result envelope (json, or the final stream-json event).
        if event.get("type") == "result" or "is_error" in event or "total_cost_usd" in event or "modelUsage" in event:
            if isinstance(event.get("usage"), dict):
                parsed["usage"] = event["usage"]
            models = event.get("modelUsage")
            if isinstance(models, dict):
                parsed["models"] = sorted(models)
                bases = {m.get("costBasis") for m in models.values() if isinstance(m, dict)}
                parsed["cost_basis"] = ",".join(sorted(b for b in bases if b)) or None
            if isinstance(event.get("total_cost_usd"), (int, float)):
                parsed["cost_usd"] = float(event["total_cost_usd"])
            if isinstance(event.get("is_error"), bool):
                parsed["is_error"] = event["is_error"]
        # Codex exec --json: the last completed turn carries usage.
        elif event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            parsed["usage"] = event["usage"]
        elif event.get("type") == "turn.failed":
            parsed["is_error"] = True
    return parsed


def read_receipt(directory: Path) -> dict[str, Any]:
    start = json.loads((directory / "start.json").read_text(encoding="utf-8"))
    end_path = directory / "end.json"
    end = json.loads(end_path.read_text(encoding="utf-8")) if end_path.exists() else None
    stdout = (directory / "stdout.raw").read_bytes() if (directory / "stdout.raw").exists() else b""
    stderr = (directory / "stderr.raw").read_bytes() if (directory / "stderr.raw").exists() else b""
    orphan = directory / "orphan.json"
    parsed = parse_cli_output(stdout)
    skipped = (directory / "skipped.json").exists()
    status = ("skipped" if skipped else "incomplete" if end is None else "timeout" if end.get("timed_out")
              else "failed" if end.get("exit_code") != 0 or parsed["is_error"] else "completed")
    return {
        "call_id": directory.name, **start,
        "ended_at": end.get("ended_at") if end else None,
        "exit_code": end.get("exit_code") if end else None,
        "status": status,
        # Not sent because the run had already hit the account's usage limit.
        "skipped_after_limit": skipped,
        "usage_limit": usage_limit_message(stdout, stderr) if status == "failed" else None,
        "wrapper_terminated": orphan.exists(),
        **{key: parsed[key] for key in ("usage", "models", "cost_usd", "cost_basis")},
    }


def _model_command(provider: str, schema: dict[str, Any], workdir: Path, model: str | None) -> tuple[list[str], Path | None]:
    if provider == "claude":
        command = ["claude", "-p", "--safe-mode", "--no-session-persistence", "--tools", "",
                   "--output-format", "json", "--json-schema", json.dumps(schema)]
        if model:
            command += ["--model", model]
        return command, None
    if provider == "codex":
        schema_path, output_path = workdir / "schema.json", workdir / "result.json"
        schema_path.write_text(json.dumps(schema))
        command = ["codex", "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules",
                   "--sandbox", "read-only", "--cd", str(workdir), "--skip-git-repo-check", "--json",
                   "--output-schema", str(schema_path), "--output-last-message", str(output_path), "-"]
        if model:
            command[2:2] = ["--model", model]
        return command, output_path
    raise ValueError("model provider must be claude or codex")


def run_model_cli(provider: str, prompt: str, schema: dict[str, Any], *, receipts: Path, phase: str,
                  timeout: float, model: str | None = None, label: str | None = None,
                  gate: Path | None = None, cache_ttl: str | None = None,
                  stable_prefix: bool = False) -> tuple[dict[str, Any], str]:
    """Run one structured-output model call, record its receipt, and return (result, call_id).

    With a gate, a call after the run has hit the account's usage limit is not sent; it leaves a
    skipped receipt and raises ModelUsageLimitError, as does the call that hits the limit.
    """
    if timeout <= 0:
        raise TimeoutError(f"{phase} model call has no time left")
    if cache_ttl not in {None, "5m", "1h"}:
        raise ValueError("cache_ttl must be 5m, 1h, or None (inherit)")
    if provider != "claude" and (cache_ttl is not None or stable_prefix):
        raise ValueError("cache TTL and stable prefix options require the Claude CLI")
    environment = os.environ.copy()
    if cache_ttl is not None:
        # Scope the override to this child; do not change the user's CLI settings.
        environment["CLAUDE_CODE_PROMPT_CACHE_TTL"] = cache_ttl
        environment.pop("FORCE_PROMPT_CACHING_5M", None)
    with tempfile.TemporaryDirectory(prefix="replica-model-call-") as temporary:
        workdir = Path(temporary)
        command, output_path = _model_command(provider, schema, workdir, model)
        if stable_prefix:
            command.append("--exclude-dynamic-system-prompt-sections")
        directory = new_call_dir(receipts)
        _write_json(directory / "start.json", {
            "phase": phase, "tool": provider, "label": label, "requested_model": model,
            "argv": command[1:], "started_at": time.time(),
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "prompt_bytes": len(prompt.encode()),
            "cache_configuration": {"ttl": cache_ttl, "stable_prefix": stable_prefix,
                                    "inherited_ttl": environment.get("CLAUDE_CODE_PROMPT_CACHE_TTL")
                                    if cache_ttl is None and provider == "claude" else None},
        })
        blocked = read_limit_gate(gate)
        if blocked is not None:
            _write_json(directory / "skipped.json", {"at": time.time(), "reason": "provider_usage_limit"})
            raise ModelUsageLimitError(f"{phase} model call not sent: the provider usage limit was reached earlier "
                                       f"in this run ({blocked.get('message', '')})")
        timed_out = False
        try:
            completed = subprocess.run(command, input=prompt.encode(), capture_output=True, cwd=workdir,
                                       timeout=timeout, check=False, env=environment)
            stdout, stderr, exit_code = completed.stdout, completed.stderr, completed.returncode
        except subprocess.TimeoutExpired as error:
            stdout, stderr, exit_code, timed_out = error.stdout or b"", error.stderr or b"", None, True
        except OSError as error:
            stdout, stderr, exit_code = b"", str(error).encode(), None
        (directory / "stdout.raw").write_bytes(stdout[:_RAW_LIMIT])
        (directory / "stderr.raw").write_bytes(stderr[:_RAW_LIMIT])
        _write_json(directory / "end.json", {"ended_at": time.time(), "exit_code": exit_code, "timed_out": timed_out})
        if timed_out:
            raise TimeoutError(f"{phase} model call exceeded {timeout:.0f}s")
        limit = usage_limit_message(stdout, stderr)
        if limit is not None:
            trip_limit_gate(gate, {"message": limit, "phase": phase, "call_id": directory.name})
            raise ModelUsageLimitError(f"{phase} model call hit the provider usage limit: {limit}")
        if exit_code != 0:
            raise RuntimeError(f"{phase} model call exited {exit_code}: {_error_text(stdout, stderr)}")
        if provider == "codex":
            result = json.loads(output_path.read_text()) if output_path and output_path.exists() else None
        else:
            envelope = json.loads(stdout)
            if not isinstance(envelope, dict) or envelope.get("is_error"):
                raise RuntimeError(f"{phase} model call reported an error: {_error_text(stdout, b'')}")
            result = envelope.get("structured_output")
            if result is None:
                result = json.loads(envelope["result"])
        if not isinstance(result, dict):
            raise RuntimeError(f"{phase} model call returned no structured object")
        return result, directory.name


_WRAPPER = '''#!{python}
# Metering wrapper generated by replica_mvp.model_calls; forwards everything to the real CLI.
import json, os, re, signal, subprocess, sys, threading, time, uuid
REAL, RECEIPTS, PHASE, TOOL, GATE = {real!r}, {receipts!r}, {phase!r}, {tool!r}, {gate!r}
LIMIT = re.compile({pattern!r}, re.IGNORECASE)
GUARD = (
    "import json,os,signal,sys,time\\n"
    "fd,pid,d=int(sys.argv[1]),int(sys.argv[2]),sys.argv[3]\\n"
    "if not os.read(fd,1):\\n"
    "    try:\\n"
    "        os.kill(pid,signal.SIGKILL); killed=True\\n"
    "    except ProcessLookupError:\\n"
    "        killed=False\\n"
    "    open(os.path.join(d,'orphan.json'),'w').write(json.dumps({{'child_killed':killed,'at':time.time()}}))\\n"
)
def write(name, value):
    temporary = os.path.join(call, name + ".tmp")
    with open(temporary, "w") as handle:
        json.dump(value, handle)
    os.replace(temporary, os.path.join(call, name))
call = os.path.join(RECEIPTS, "%d-%d-%s" % (time.time_ns(), os.getpid(), uuid.uuid4().hex[:8]))
os.makedirs(call)
write("start.json", {{"phase": PHASE, "tool": TOOL, "argv": sys.argv[1:], "cwd": os.getcwd(), "started_at": time.time()}})
if GATE and os.path.exists(GATE):
    # The run already hit the account's usage limit: answer as the CLI would, without sending the call.
    write("skipped.json", {{"at": time.time(), "reason": "provider_usage_limit"}})
    print(json.dumps({{"type": "result", "is_error": True, "api_error_status": 429,
                      "result": "replica-mvp: not sent; the provider usage limit was reached earlier in this run"}}))
    sys.exit(1)
child = subprocess.Popen([REAL] + sys.argv[1:], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
# If this wrapper is killed (for example by the caller's timeout), the guard ends the real CLI too.
read_end, write_end = os.pipe()
subprocess.Popen([sys.executable, "-c", GUARD, str(read_end), str(child.pid), call], pass_fds=(read_end,),
                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
os.close(read_end)
for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
    signal.signal(number, lambda received, frame: child.send_signal(received))
def tee(source, target, name):
    with open(os.path.join(call, name), "wb") as record:
        while True:
            chunk = os.read(source.fileno(), 65536)
            if not chunk:
                break
            record.write(chunk)
            record.flush()
            try:
                target.write(chunk)
                target.flush()
            except OSError:
                pass
threads = [threading.Thread(target=tee, args=(child.stdout, sys.stdout.buffer, "stdout.raw")),
           threading.Thread(target=tee, args=(child.stderr, sys.stderr.buffer, "stderr.raw"))]
for thread in threads:
    thread.start()
code = child.wait()
for thread in threads:
    thread.join()
write("end.json", {{"ended_at": time.time(), "exit_code": code}})
def limited():
    try:
        out = open(os.path.join(call, "stdout.raw"), "rb").read().decode("utf-8", "replace")
        err = open(os.path.join(call, "stderr.raw"), "rb").read().decode("utf-8", "replace")
    except OSError:
        return None
    for line in out.splitlines() or [out]:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and (event.get("api_error_status") == 429 or (
                event.get("is_error") and LIMIT.search(str(event.get("result", ""))))):
            return str(event.get("result") or "HTTP 429")[:300]
        if isinstance(event, dict) and event.get("type") in {{"turn.failed", "error"}}:
            detail = json.dumps(event.get("error") or event.get("message") or event)
            if LIMIT.search(detail):
                return detail[:300]
    found = [l for l in err.splitlines() if LIMIT.search(l)]
    return found[-1][:300] if found else None
if GATE:
    message = limited()
    if message:
        try:
            handle = os.open(GATE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            os.write(handle, json.dumps({{"kind": "provider_usage_limit", "detected_at": time.time(), "message": message,
                                          "phase": PHASE, "call_id": os.path.basename(call)}}).encode())
            os.close(handle)
        except FileExistsError:
            pass
os.write(write_end, b"x")
os.close(write_end)
if code < 0:
    signal.signal(-code, signal.SIG_DFL)
    os.kill(os.getpid(), -code)
sys.exit(code)
'''


def install_meter(bin_dir: Path, receipts: Path, phase: str, gate: Path | None = None) -> dict[str, str]:
    """Write PATH wrappers for installed model CLIs; returns {tool: real absolute path}.

    With a gate, a wrapped call that hits the account's usage limit records it there, and later
    wrapped calls are answered with a limit error without reaching the real CLI.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    receipts.mkdir(parents=True, exist_ok=True)
    installed = {}
    search = os.pathsep.join(p for p in os.environ.get("PATH", "").split(os.pathsep)
                             if p and Path(p).resolve() != bin_dir.resolve())
    for tool in METERED_TOOLS:
        # Resolve the real CLI before PATH changes so a wrapper never calls itself.
        real = shutil.which(tool, path=search)
        if real is None:
            continue
        wrapper = bin_dir / tool
        wrapper.write_text(_WRAPPER.format(python=sys.executable, real=str(Path(real).resolve()),
                                           receipts=str(receipts.resolve()), phase=phase, tool=tool,
                                           gate=str(gate.resolve()) if gate else "", pattern=_LIMIT_PATTERN))
        wrapper.chmod(0o755)
        installed[tool] = str(Path(real).resolve())
    return installed


def summarize_receipts(receipts: Path) -> dict[str, Any]:
    """Aggregate receipts per phase. Each call counts once; usage keys are summed separately."""
    return summarize_receipt_directories([receipts])


def summarize_receipt_directories(directories: list[Path]) -> dict[str, Any]:
    """Sum all registered segments; copied receipts retain their call ID and count once."""
    unique = {}
    for receipts in directories:
        for directory in sorted(receipts.iterdir()) if receipts.exists() else []:
            if (directory / "start.json").exists():
                call = read_receipt(directory)
                if call["call_id"] in unique and unique[call["call_id"]] != call:
                    raise ValueError("conflicting receipts for call " + call["call_id"])
                unique[call["call_id"]] = call
    calls = sorted(unique.values(), key=lambda call: (call["started_at"], call["call_id"]))
    phases: dict[str, dict[str, Any]] = {}
    for call in calls:
        phase = phases.setdefault(call["phase"], {
            "calls": 0, "completed": 0, "failed": 0, "timeout": 0, "incomplete": 0, "skipped": 0,
            "usage_limited": 0,
            "call_seconds": 0.0, "usage": {}, "calls_with_usage": 0, "models": [],
            "cli_list_estimate_usd": 0.0, "calls_with_estimate": 0,
        })
        # A skipped call was never sent: it is counted on its own, not as a call.
        phase["calls"] += call["status"] != "skipped"
        phase[call["status"]] += 1
        phase["usage_limited"] += call["usage_limit"] is not None
        if call["ended_at"] is not None:
            phase["call_seconds"] += max(0.0, call["ended_at"] - call["started_at"])
        if isinstance(call["usage"], dict):
            phase["calls_with_usage"] += 1
            for key, value in call["usage"].items():
                if type(value) is int:
                    phase["usage"][key] = phase["usage"].get(key, 0) + value
        phase["models"] = sorted(set(phase["models"]) | set(call["models"]))
        if call["cost_usd"] is not None:
            phase["cli_list_estimate_usd"] += call["cost_usd"]
            phase["calls_with_estimate"] += 1
    for phase in phases.values():
        phase["call_seconds"] = round(phase["call_seconds"], 3)
        phase["cli_list_estimate_usd"] = round(phase["cli_list_estimate_usd"], 6) if phase["calls_with_estimate"] else None
        phase["estimate_complete"] = phase["calls_with_estimate"] == phase["calls"]
    return {"calls": calls, "phases": phases}
