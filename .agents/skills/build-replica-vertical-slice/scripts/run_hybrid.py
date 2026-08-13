from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn


def _reject_constant(value: str) -> NoReturn:
    raise ValueError(f"non-standard JSON constant: {value}")


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=_reject_constant)
    except FileNotFoundError:
        raise ValueError(f"missing JSON file: {path}") from None
    except ValueError as error:
        raise ValueError(f"invalid JSON in {path}: {error}") from None


def execute(implementation: Path, envelope: dict[str, Any], timeout: int, maximum: int) -> Any:
    environment = {
        name: os.environ[name]
        for name in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "WINDIR")
        if name in os.environ
    }
    environment.update({"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    try:
        completed = subprocess.run(
            [sys.executable, "-I", str(implementation)],
            input=json.dumps(envelope, ensure_ascii=False, allow_nan=False),
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=timeout,
            check=False,
            cwd=implementation.parent,
            env=environment,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"hybrid implementation exceeded {timeout}s") from None
    if completed.returncode:
        detail = completed.stderr.strip() or f"exit code {completed.returncode}"
        raise RuntimeError(f"hybrid implementation failed: {detail}")
    encoded = completed.stdout.encode("utf-8")
    if len(encoded) > maximum:
        raise RuntimeError(f"hybrid output exceeds {maximum} bytes")
    try:
        return json.loads(completed.stdout, parse_constant=_reject_constant)
    except ValueError as error:
        raise RuntimeError(f"hybrid implementation returned invalid JSON: {error}") from None


def run(task_dir: Path, attempt: int, input_path: Path, timeout: int, maximum: int) -> Any:
    task_dir = task_dir.resolve(strict=True)
    implementation = task_dir / "attempts" / f"attempt-{attempt:02d}" / "implementation" / "replica.py"
    if not implementation.is_file():
        raise ValueError(f"missing implementation: {implementation}")
    runtime_input = _load(input_path.resolve(strict=True))
    if not isinstance(runtime_input, dict):
        raise ValueError("runtime input must be a JSON object")
    manifest_path = task_dir / "assets.json"
    manifest = _load(manifest_path)
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != "replica-assets/v1"
        or not isinstance(manifest.get("assets"), list)
    ):
        raise ValueError("invalid assets manifest")
    output_dir = task_dir / "attempts" / f"attempt-{attempt:02d}" / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    envelope = {
        "schema_version": "replica-hybrid-request/v1",
        "input": runtime_input,
        "assets": manifest["assets"],
        "assets_dir": str((task_dir / "assets").resolve()),
        "output_dir": str(output_dir.resolve()),
    }
    return execute(implementation, envelope, timeout, maximum)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one claim-specific hybrid Replica candidate.")
    parser.add_argument("task_dir", type=Path)
    parser.add_argument("--attempt", type=int, choices=(1, 2, 3), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-output-bytes", type=int, default=10_000_000)
    args = parser.parse_args()
    if args.timeout <= 0 or args.max_output_bytes <= 0:
        parser.error("limits must be positive")
    try:
        result = run(args.task_dir, args.attempt, args.input, args.timeout, args.max_output_bytes)
    except (OSError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
