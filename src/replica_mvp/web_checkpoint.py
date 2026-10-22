"""Immutable evaluation checkpoints and version-aware continuation of a web demo."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluator_version() -> str:
    root = Path(__file__).parent
    files = ("web_demo.py", "web_checkpoint.py", "web_contract.py", "web_inputs.py", "web_evaluation.py",
             "model_calls.py", "bundle_runtime.py", "company_app.py")
    if (root / "web_actions.py").exists():
        files += ("web_actions.py",)
    return hashlib.sha256("".join(digest(root / name) for name in files).encode()).hexdigest()


def artifact_hashes(directory: Path) -> dict[str, str]:
    # Only evidence is retained across a continuation, never a live server process.
    return {p.relative_to(directory).as_posix(): digest(p)
            for p in sorted((directory / "cases").rglob("*")) if p.is_file() and not p.is_symlink()}


def write_checkpoint(directory: Path, state: dict[str, Any]) -> None:
    value = {**state, "evidence_sha256": artifact_hashes(directory)}
    temporary = directory / "checkpoint.tmp"
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    temporary.replace(directory / "checkpoint.json")


def load_checkpoint(directory: Path, identity: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Reuse verdicts only under the same evaluator/settings and verified evidence.

    Legacy results retain drawn inputs but are rerun under the corrected observer.
    A changed evaluator is a new observation, not a relabeling of the old result.
    """
    checkpoint = directory / "checkpoint.json"
    source = checkpoint if checkpoint.exists() else directory / "demo-result.json"
    value = json.loads(source.read_text(encoding="utf-8"))
    if any(p.is_symlink() for p in (directory / "cases").rglob("*")):
        raise ValueError("resume evidence must not contain symlinks")
    for key in ("plan_sha256", "candidate_manifest_sha256"):
        if value.get(key) != identity[key]:
            raise ValueError(f"resume {key} differs from the current frozen input")
    same = (value.get("evaluator_version") == identity["evaluator_version"]
            and value.get("model_configuration") == identity["model_configuration"]
            and value.get("selected_cases") == identity["selected_cases"]
            and value.get("scope_sha256") == identity.get("scope_sha256"))
    # An interrupted input write has saved parameters, but has not committed bytes
    # or started the app. Ignore only those unsealed input files; the next attempt
    # deterministically renders the saved parameters, never draws fresh values.
    ran = {c["case_id"] for c in value.get("cases", [])
           if c.get("workspace") or c.get("events") or c.get("execution_status") == "completed"}
    preparing = [f"cases/{cid}/inputs/" for cid, info in value.get("instances", {}).items()
                 if isinstance(info, dict) and info.get("input_state") == "preparing"
                 and "input_files" not in info and cid not in ran]
    def committed(hashes):
        return {name: digest for name, digest in hashes.items()
                if not any(name.startswith(prefix) for prefix in preparing)}
    for name, expected in committed(value.get("evidence_sha256", {})).items():
        path = directory / name
        if (not path.resolve().is_relative_to(directory.resolve()) or path.is_symlink()
                or not path.is_file() or digest(path) != expected):
            raise ValueError("resume evidence changed: " + name)
    if isinstance(value.get("evidence_sha256"), dict) and committed(artifact_hashes(directory)) != committed(value["evidence_sha256"]):
        raise ValueError("resume evidence file set changed")
    # An unverified checkpoint cannot supply reusable judgments.
    same = same and isinstance(value.get("evidence_sha256"), dict)
    return {**value, "source_sha256": digest(source)}, same


def load_input_cases(directory: Path, identity: dict[str, Any], cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Share only drawn inputs in a controlled comparison, never completed evidence.

    The source must describe the same plan and candidate and pass the usual
    artifact integrity checks. Missing inputs are an error, not an invitation
    to silently generate a different comparison case.
    """
    source, _ = load_checkpoint(directory, identity)
    instances = dict(source.get("instances", {}))
    for case in source.get("cases", []):
        if case.get("instance"):
            instances.setdefault(case["case_id"], case["instance"])
    required = {c["id"] for c in cases if c.get("variation") and c["id"] in identity["selected_cases"]}
    available = {cid for cid, value in instances.items()
                 if isinstance(value, dict) and isinstance(value.get("steps"), list) and value["steps"]}
    if required - available:
        raise ValueError("comparison source lacks drawn inputs: " + ", ".join(sorted(required - available)))
    return {"instances": instances, "cases": source.get("cases", []), "source_sha256": source["source_sha256"]}
