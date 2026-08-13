from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, BinaryIO, NoReturn


CHUNK_SIZE = 1024 * 1024


def _reject_constant(value: str) -> NoReturn:
    raise ValueError(f"non-standard JSON constant: {value}")


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=_reject_constant)
    except FileNotFoundError:
        raise ValueError(f"missing asset requests: {path}") from None
    except ValueError as error:
        raise ValueError(f"invalid asset requests: {error}") from None


def _copy_limited(source: BinaryIO, target: BinaryIO, maximum: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    while chunk := source.read(CHUNK_SIZE):
        total += len(chunk)
        if total > maximum:
            raise ValueError(f"asset exceeds {maximum} byte limit")
        digest.update(chunk)
        target.write(chunk)
    return digest.hexdigest(), total


def _validate_request(value: Any) -> list[dict[str, Any]]:
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "assets"}
        or value.get("schema_version") != "replica-asset-requests/v1"
        or not isinstance(value.get("assets"), list)
    ):
        raise ValueError("invalid asset request document")
    ids: list[str] = []
    for asset in value["assets"]:
        valid_fields = (
            {"id", "source", "media_type", "license", "provenance"},
            {"id", "source", "media_type", "license", "provenance", "expected_sha256"},
        )
        if not isinstance(asset, dict) or not any(set(asset) == fields for fields in valid_fields):
            raise ValueError("invalid asset request")
        asset_id = asset.get("id")
        source = asset.get("source")
        if (
            not isinstance(asset_id, str)
            or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", asset_id)
            or not isinstance(source, dict)
            or set(source) != {"type", "location"}
            or source.get("type") not in {"local", "url"}
            or not isinstance(source.get("location"), str)
            or not source["location"].strip()
            or not all(isinstance(asset.get(name), str) and asset[name].strip() for name in ("media_type", "license"))
            or asset.get("provenance") not in {"public", "synthetic"}
            or (
                "expected_sha256" in asset
                and (
                    not isinstance(asset["expected_sha256"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", asset["expected_sha256"])
                )
            )
        ):
            raise ValueError(f"invalid asset request: {asset_id!r}")
        if source["type"] == "url":
            parsed = urllib.parse.urlparse(source["location"])
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"unsupported asset URL: {source['location']}")
        ids.append(asset_id)
    if len(ids) != len(set(ids)):
        raise ValueError("asset ids must be unique")
    return value["assets"]


def materialize(request_path: Path, task_dir: Path, maximum: int, timeout: int) -> dict[str, Any]:
    request_path = request_path.resolve(strict=True)
    task_dir = task_dir.resolve()
    assets = _validate_request(_load(request_path))
    assets_dir = task_dir / "assets"
    manifest_path = task_dir / "assets.json"
    if assets_dir.exists() or manifest_path.exists():
        raise ValueError("asset output already exists")
    assets_dir.mkdir(parents=True)
    records: list[dict[str, Any]] = []
    try:
        for request in assets:
            source = request["source"]
            location = source["location"]
            if source["type"] == "local":
                source_path = Path(location)
                if not source_path.is_absolute():
                    source_path = request_path.parent / source_path
                source_path = source_path.resolve(strict=True)
                if not source_path.is_file():
                    raise ValueError(f"asset source is not a file: {location}")
                suffix = source_path.suffix.lower()
                opened = source_path.open("rb")
                source_record = {"type": "local", "location": location}
            else:
                parsed = urllib.parse.urlparse(location)
                suffix = Path(parsed.path).suffix.lower()
                opened = urllib.request.urlopen(
                    urllib.request.Request(location, headers={"User-Agent": "replica-mvp/0.1"}),
                    timeout=timeout,
                )
                final_url = urllib.parse.urlparse(opened.geturl())
                if final_url.scheme not in {"http", "https"}:
                    opened.close()
                    raise ValueError("asset URL redirected to an unsupported scheme")
                source_record = {"type": "url", "location": location, "resolved_url": opened.geturl()}
            if not suffix:
                suffix = mimetypes.guess_extension(request["media_type"]) or ".bin"
            destination = assets_dir / f"{request['id']}{suffix}"
            temporary_fd, temporary_name = tempfile.mkstemp(dir=assets_dir, prefix=".partial-")
            try:
                with opened, os.fdopen(temporary_fd, "wb") as target:
                    digest, size = _copy_limited(opened, target, maximum)
                if request.get("expected_sha256") not in {None, digest}:
                    raise ValueError(f"asset hash mismatch: {request['id']}")
                os.replace(temporary_name, destination)
            finally:
                if os.path.exists(temporary_name):
                    os.unlink(temporary_name)
            records.append(
                {
                    "id": request["id"],
                    "source": source_record,
                    "materialized_path": destination.relative_to(task_dir).as_posix(),
                    "media_type": request["media_type"],
                    "license": request["license"],
                    "provenance": request["provenance"],
                    "sha256": digest,
                    "size_bytes": size,
                }
            )
        manifest = {"schema_version": "replica-assets/v1", "assets": records}
        with manifest_path.open("x", encoding="utf-8") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
        return manifest
    except Exception:
        shutil.rmtree(assets_dir, ignore_errors=True)
        manifest_path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize public Replica input assets.")
    parser.add_argument("request", type=Path)
    parser.add_argument("--task-dir", required=True, type=Path)
    parser.add_argument("--max-bytes", type=int, default=50_000_000)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    if args.max_bytes <= 0 or args.timeout <= 0:
        parser.error("limits must be positive")
    try:
        result = materialize(args.request, args.task_dir, args.max_bytes, args.timeout)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
