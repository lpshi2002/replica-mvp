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
    files = ("web_demo.py", "web_checkpoint.py", "model_calls.py", "bundle_runtime.py")
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
            and value.get("selected_cases") == identity["selected_cases"])
    for name, expected in value.get("evidence_sha256", {}).items():
        path = directory / name
        if (not path.resolve().is_relative_to(directory.resolve()) or path.is_symlink()
                or not path.is_file() or digest(path) != expected):
            raise ValueError("resume evidence changed: " + name)
    if isinstance(value.get("evidence_sha256"), dict) and artifact_hashes(directory) != value["evidence_sha256"]:
        raise ValueError("resume evidence file set changed")
    # An unverified checkpoint cannot supply reusable judgments.
    same = same and isinstance(value.get("evidence_sha256"), dict)
    return {**value, "source_sha256": digest(source)}, same
