from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn


def _reject_nonstandard_constant(value: str) -> NoReturn:
    raise ValueError(f"non-standard JSON constant: {value}")


def receive_second_pass(source: Path, workspace: Path) -> dict[str, Any]:
    source_bytes = source.read_bytes()
    try:
        payload = json.loads(
            source_bytes.decode("utf-8-sig"),
            parse_constant=_reject_nonstandard_constant,
        )
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError(f"invalid JSON in {source}: {error}") from None
    if not isinstance(payload, dict):
        raise ValueError(f"{source} must contain a JSON object")

    digest = hashlib.sha256(source_bytes).hexdigest()
    intake_dir = workspace / "intakes" / digest
    intake_path = intake_dir / "intake.json"
    if intake_path.exists():
        return json.loads(intake_path.read_text(encoding="utf-8"))

    intake_dir.mkdir(parents=True, exist_ok=True)
    (intake_dir / "source.json").write_bytes(source_bytes)

    result = {
        "schema_version": "replica-intake/v1",
        "status": "AWAITING_CONTRACT_VALIDATION",
        "sha256": digest,
        "source_name": source.name,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    intake_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result
