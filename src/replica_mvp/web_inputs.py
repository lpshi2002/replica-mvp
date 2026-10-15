"""Frozen upload sources and the exact input bytes used by each browser case."""
from __future__ import annotations

import hashlib
import csv
import io
import re
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .bundle_runtime import safe_relative


TEXT_INPUT_LIMIT = 20_000


class InputVariationError(ValueError):
    """This draw cannot be used; preserve its rejection rather than drawing until it passes."""


def file_bytes(root: Path, name: str, expected: str | None = None) -> bytes:
    path = root / name
    if (not safe_relative(name) or not path.resolve().is_relative_to(root.resolve())
            or any(root.joinpath(*Path(name).parts[:i]).is_symlink() for i in range(1, len(Path(name).parts) + 1))):
        raise ValueError("upload path must stay inside its directory without symlinks")
    data = path.read_bytes()
    if expected is not None and hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("upload hash mismatch: " + name)
    return data


def validate_uploads(case: dict, plan_dir: Path, *, for_execution: bool) -> None:
    uploads = case.get("uploads", [])
    if not isinstance(uploads, list):
        raise ValueError("uploads must be a list")
    seen = set()
    for upload in uploads:
        if not isinstance(upload, dict) or not safe_relative(upload.get("path")) or upload["path"] in seen:
            raise ValueError("uploads need unique relative paths")
        seen.add(upload["path"])
        digest = upload.get("sha256")
        if (for_execution or digest is not None) and (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("new upload execution requires a frozen sha256; legacy results remain readable")
        if "vary" in upload and type(upload["vary"]) is not bool:
            raise ValueError("upload vary must be a boolean")
        if upload.get("vary") and not case.get("variation"):
            raise ValueError("a varying upload needs a frozen variation rule")
        file_bytes(plan_dir, upload["path"], digest)
    if any(u.get("vary") for u in uploads):
        for expectation in case["expectations"]:
            if expectation.get("upload_relation") not in {"literal", "derived", "none"}:
                raise ValueError("varying-upload expectations need upload_relation: literal, derived or none")


def sealed_uploads(case: dict, directory: Path, records: list[dict]) -> dict[str, Path]:
    expected = {u["path"]: u for u in case.get("uploads", [])}
    if not isinstance(records, list) or len(records) != len(expected):
        raise ValueError("sealed input file set does not match the frozen case")
    found = {}
    for record in records:
        name = record.get("upload_path")
        if name not in expected or name in found or record.get("source_sha256") != expected[name].get("sha256"):
            raise ValueError("sealed input source binding changed")
        path = record.get("path")
        prefix = f"cases/{case['id']}/inputs/"
        if not isinstance(path, str) or not path.startswith(prefix):
            raise ValueError("sealed input is not in this case's inputs directory")
        digest = record.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("sealed input needs its final sha256")
        varied = bool(expected[name].get("vary"))
        unchanged = digest == record["source_sha256"]
        if (varied and unchanged) or (not varied and not unchanged):
            raise ValueError("sealed input violates the frozen fixed/vary rule")
        data = file_bytes(directory, path, digest)
        if len(data) != record.get("bytes"):
            raise ValueError("sealed input byte length changed")
        found[name] = directory / path
    return found


def seal_inputs(case: dict, plan_dir: Path, directory: Path, info: dict,
                *, contents: dict[str, bytes] | None = None) -> None:
    if "input_files" in info:
        sealed_uploads(case, directory, info["input_files"])
        return
    records = []
    for upload in case.get("uploads", []):
        name = upload["path"]
        source = file_bytes(plan_dir, name, upload["sha256"])
        if upload.get("vary") and (name not in (contents or {}) or contents[name] == source):
            raise InputVariationError("varying input must have changed bytes; original fallback is forbidden")
        data = (contents or {}).get(name, source)
        if not upload.get("vary") and data != source:
            raise InputVariationError("fixed upload contents must remain unchanged")
        relative = f"cases/{case['id']}/inputs/{name}"
        destination = directory / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        # A partial write may be completed only from the same saved parameters.
        if destination.exists() and destination.read_bytes() != data:
            raise ValueError("existing input bytes differ from the saved draw")
        destination.write_bytes(data)
        records.append({"upload_path": name, "path": relative, "source_sha256": upload["sha256"],
                        "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    info["input_files"] = records


def restore_inputs(cases: list[dict], instances: dict, previous_cases: list[dict], source: Path,
                   destination: Path | None = None, *, require_all: bool = False) -> None:
    """Validate first; a second call copies only input files, never browser state or verdicts."""
    prior = {c["case_id"]: c for c in previous_cases}
    for case in cases:
        if not case.get("uploads"):
            continue
        info = instances.get(case["id"], {})
        records = info.get("input_files")
        ran = prior.get(case["id"], {})
        if records is None:
            if require_all or ran.get("workspace") or ran.get("events") or ran.get("execution_status") == "completed":
                raise ValueError("previous upload case lacks sealed inputs; regeneration is forbidden")
            continue
        sealed_uploads(case, source, records)
        if destination is not None:
            for record in records:
                target = destination / record["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(file_bytes(source, record["path"], record["sha256"]))
            sealed_uploads(case, destination, records)


def input_context(case: dict, directory: Path, records: list[dict]) -> list[dict]:
    paths = sealed_uploads(case, directory, records)
    context = []
    for record in records:
        path = paths[record["upload_path"]]
        item = {**record, "content_status": "unavailable", "content": None,
                "content_error": "Input content is not a supported UTF-8 TXT/CSV of at most 20KB."}
        data = file_bytes(directory, record["path"], record["sha256"])
        if path.suffix.lower() in {".txt", ".csv"} and len(data) <= TEXT_INPUT_LIMIT:
            try:
                content = data.decode("utf-8")
                if "\x00" not in content:
                    item.update(content_status="complete", content=content)
                    item.pop("content_error")
            except UnicodeDecodeError:
                pass
        context.append(item)
    return context


def _csv_rows(content: str) -> list[list[str]]:
    try:
        rows = list(csv.reader(io.StringIO(content, newline=""), strict=True))
    except csv.Error as error:
        raise InputVariationError(f"invalid CSV: {error}") from error
    if len(rows) < 2 or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
        raise InputVariationError("CSV must have a header and rectangular data rows")
    return rows


def variation_sources(case: dict, plan_dir: Path) -> list[dict]:
    sources = []
    for upload in case.get("uploads", []):
        if not upload.get("vary"):
            continue
        path = upload["path"]
        data = file_bytes(plan_dir, path, upload["sha256"])
        if Path(path).suffix.lower() not in {".txt", ".csv"} or len(data) > TEXT_INPUT_LIMIT:
            raise InputVariationError("upload variation supports only UTF-8 TXT/CSV up to 20KB")
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise InputVariationError("varying upload is not valid UTF-8") from error
        if "\x00" in content:
            raise InputVariationError("varying upload contains binary NUL bytes")
        if Path(path).suffix.lower() == ".csv":
            _csv_rows(content)
        sources.append({"path": path, "sha256": upload["sha256"], "content": content})
    return sources


def _number(value: str) -> bool:
    try:
        return bool(value.strip()) and Decimal(value).is_finite()
    except InvalidOperation:
        return False


def replacement_function(replacements: list[dict]):
    if not isinstance(replacements, list) or not replacements:
        raise InputVariationError("varying uploads require non-empty replacements")
    values = {}
    for item in replacements:
        if not isinstance(item, dict):
            raise InputVariationError("replacement must contain from and to")
        old, new = item.get("from"), item.get("to")
        if not isinstance(old, str) or not old.strip() or not isinstance(new, str) or not new.strip() or old == new:
            raise InputVariationError("replacement needs non-empty, different from and to values")
        if "\x00" in old or "\x00" in new:
            raise InputVariationError("replacement cannot contain binary NUL bytes")
        try:
            old.encode("utf-8")
            new.encode("utf-8")
        except UnicodeError as error:
            raise InputVariationError("replacement must be valid UTF-8 text") from error
        if any(old in key or key in old for key in values):
            raise InputVariationError("duplicate or overlapping replacement keys")
        values[old] = new
    pattern = re.compile("|".join(re.escape(key) for key in values))

    def swap(value: str) -> str:
        def replace(match):
            old = match.group()
            # Reject partial words/numbers rather than silently changing only some occurrences.
            left = value[match.start() - 1:match.start()] if match.start() else ""
            right = value[match.end():match.end() + 1]
            if ((old[0].isalnum() and left and (left.isalnum() or left == "_" or (_number(old) and left in ".+-")))
                    or (old[-1].isalnum() and right and (right.isalnum() or right == "_" or (_number(old) and right == ".")))):
                raise InputVariationError("replacement would change a partial word or number")
            return values[old]
        return pattern.sub(replace, value)  # one pass: replacements never modify other replacements
    return swap


def upload_instance(case: dict, answer: dict) -> dict:
    """The frozen wording owns the workflow; a model supplies literal substitutions only."""
    swap = replacement_function(answer.get("replacements"))
    changed = deepcopy(case)
    changed["goal"] = swap(case["goal"])
    for key in ("steps", "facts"):
        changed[key] = [swap(value) for value in case.get(key, [])]
    for expectation in changed["expectations"]:
        if expectation["upload_relation"] == "derived":
            continue  # Retain the criterion; no model-generated arithmetic is treated as verified.
        expectation["description"] = swap(expectation["description"])
        if expectation.get("precondition"):
            expectation["precondition"] = swap(expectation["precondition"])
        if (expectation.get("check") or {}).get("text"):
            expectation["check"]["text"] = swap(expectation["check"]["text"])
    return changed


def render_uploads(case: dict, answer: dict, plan_dir: Path) -> dict[str, bytes]:
    replacements = answer.get("replacements")
    swap = replacement_function(replacements)
    sources = variation_sources(case, plan_dir)
    available = "\n".join([case["goal"], *case["steps"], *case.get("facts", []),
                            *[s["content"] for s in sources],
                            *[e["description"] for e in case["expectations"]],
                            *[(e.get("check") or {}).get("text", "") for e in case["expectations"]]])
    if any(item["from"] not in available for item in replacements):
        raise InputVariationError("replacement key does not occur in the frozen case or its varying files")
    rendered = {}
    for source in sources:
        content = source["content"]
        if Path(source["path"]).suffix.lower() == ".csv":
            rows = _csv_rows(content)
            if any(swap(header) != header for header in rows[0]):
                raise InputVariationError("CSV variation must preserve headers")
            transformed = [rows[0]]
            for row in rows[1:]:
                new = [swap(value) for value in row]
                if any(_number(old) and not _number(value) for old, value in zip(row, new)):
                    raise InputVariationError("CSV variation must preserve numeric cell types")
                transformed.append(new)
            if transformed == rows:
                raise InputVariationError("varying CSV content did not change")
            buffer = io.StringIO(newline="")
            csv.writer(buffer).writerows(transformed)
            changed = buffer.getvalue()
            if _csv_rows(changed) != transformed:
                raise InputVariationError("CSV variation did not preserve its structure")
        else:
            changed = swap(content)
            if changed == content:
                raise InputVariationError("varying TXT content did not change")
        data = changed.encode("utf-8")
        if len(data) > TEXT_INPUT_LIMIT:
            raise InputVariationError("varied upload exceeds 20KB")
        rendered[source["path"]] = data
    # Shared literal substitutions cannot silently disagree with a fixed text attachment.
    for upload in case.get("uploads", []):
        if not upload.get("vary") and Path(upload["path"]).suffix.lower() in {".txt", ".csv"}:
            data = file_bytes(plan_dir, upload["path"], upload["sha256"])
            try:
                fixed = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if any(item["from"] in fixed for item in replacements):
                raise InputVariationError("replacement conflicts with a fixed upload")
    return rendered
