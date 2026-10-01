from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


PROFILE_FIELDS = {
    "schema_version",
    "title",
    "description",
    "interaction",
    "runtime_input",
    "examples",
    "comparison",
}


def run_built_replica(
    run_dir: Path,
    runtime_input: dict[str, Any],
    *,
    allow_model_adapter: bool = False,
    state_dir: Path | None = None,
) -> Any:
    from .builder import run_built_replica as execute

    return execute(run_dir, runtime_input, **_run_options(allow_model_adapter, state_dir))


def _run_options(use_model_adapter: bool, state_dir: Path | None) -> dict[str, Any]:
    options: dict[str, Any] = {}
    if use_model_adapter:
        options["allow_model_adapter"] = True
    if state_dir is not None:
        options["state_dir"] = state_dir
    return options


def is_bundle_run(run_dir: Path) -> bool:
    """A published implementation bundle can keep runtime state across calls."""
    return (run_dir / "replica.json").is_file() and _read_json_object(
        run_dir / "replica.json", "Replica"
    ).get("schema_version") == "replica-bundle/v1"


def validate_experience_profile(value: Any) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or set(value) != PROFILE_FIELDS
        or value.get("schema_version") != "replica-experience/v1"
        or not isinstance(value.get("title"), str)
        or not value["title"].strip()
        or not isinstance(value.get("description"), str)
        or not value["description"].strip()
        or not isinstance(value.get("runtime_input"), dict)
        or not isinstance(value.get("interaction"), dict)
        or set(value["interaction"]) != {"type", "question_field"}
        or value["interaction"].get("type") != "question_answer"
        or not isinstance(value["interaction"].get("question_field"), str)
        or not value["interaction"]["question_field"].strip()
        or not isinstance(value.get("examples"), list)
        or not all(
            isinstance(item, dict)
            and set(item) == {"label", "question"}
            and isinstance(item.get("label"), str)
            and bool(item["label"].strip())
            and isinstance(item.get("question"), str)
            and bool(item["question"].strip())
            for item in value.get("examples", [])
        )
        or not isinstance(value.get("comparison"), dict)
        or set(value["comparison"])
        != {"evidence_level", "summary", "original_outputs"}
        or value["comparison"].get("evidence_level")
        not in {"direct", "public", "claim_only"}
        or not isinstance(value["comparison"].get("summary"), str)
        or not value["comparison"]["summary"].strip()
        or not isinstance(value["comparison"].get("original_outputs"), list)
    ):
        raise ValueError("invalid experience profile")
    original_outputs = value["comparison"]["original_outputs"]
    if not all(
        isinstance(item, dict)
        and isinstance(item.get("question"), str)
        and bool(item["question"].strip())
        and "output" in item
        and isinstance(item.get("source"), str)
        and bool(item["source"].strip())
        for item in original_outputs
    ):
        raise ValueError("invalid experience profile")
    if (
        value["comparison"]["evidence_level"] == "direct"
        and not original_outputs
    ):
        raise ValueError("direct experience comparison requires original output")
    if (
        value["comparison"]["evidence_level"] != "direct"
        and original_outputs
    ):
        raise ValueError("original outputs require direct evidence")
    return value


def _read_profile(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise ValueError("experience profile is not valid JSON") from None
    return validate_experience_profile(value)


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise ValueError(f"{label} is not valid JSON") from None
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _read_original_observations(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise ValueError("original observations are not valid JSON") from None
    observations = value.get("observations") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or set(value)
        != {"schema_version", "original_name", "observations"}
        or value.get("schema_version")
        != "replica-original-observations/v1"
        or not isinstance(value.get("original_name"), str)
        or not value["original_name"].strip()
        or not isinstance(observations, list)
        or not observations
        or not all(
            isinstance(item, dict)
            and set(item)
            == {"question", "output", "source", "captured_at"}
            and isinstance(item.get("question"), str)
            and bool(item["question"].strip())
            and isinstance(item.get("source"), str)
            and bool(item["source"].strip())
            and isinstance(item.get("captured_at"), str)
            and bool(item["captured_at"].strip())
            for item in observations or []
        )
        or len({item["question"] for item in observations or []})
        != len(observations or [])
    ):
        raise ValueError("invalid original observations")
    try:
        for item in observations:
            captured_at = item["captured_at"]
            parsed = datetime.fromisoformat(captured_at)
            if (
                "T" not in captured_at
                or parsed.tzinfo is None
                or parsed.utcoffset() is None
            ):
                raise ValueError
    except ValueError:
        raise ValueError("invalid original observations") from None
    return value


def _validate_run_evidence_level(
    run_dir: Path,
    profile: dict[str, Any],
) -> None:
    spec_path = run_dir / "replica-spec.json"
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise ValueError("built Replica has an invalid evidence policy") from None
    evidence_policy = spec.get("evidence_policy") if isinstance(spec, dict) else None
    run_level = (
        evidence_policy.get("level")
        if isinstance(evidence_policy, dict)
        else None
    )
    if run_level not in {"direct", "public", "claim_only"}:
        raise ValueError("built Replica has an invalid evidence policy")
    if profile["comparison"]["evidence_level"] != run_level:
        raise ValueError(
            "experience evidence level does not match built Replica"
        )


def _source_texts(profile: dict[str, Any]) -> dict[str, str]:
    sources: dict[str, str] = {}
    corpus = profile["runtime_input"].get("creator_corpus", [])
    if not isinstance(corpus, list):
        return sources
    for item in corpus:
        if not isinstance(item, dict):
            continue
        source_id = item.get("source_id")
        text = item.get("text")
        if isinstance(source_id, str) and isinstance(text, str):
            sources[source_id] = text
    return sources


def _matching_original(
    profile: dict[str, Any],
    question: str,
) -> dict[str, Any] | None:
    for item in profile["comparison"]["original_outputs"]:
        if item["question"] == question:
            return item
    return None


def experience_once(
    run_dir: Path,
    profile_path: Path,
    question: str,
    original_observations_path: Path | None = None,
    *,
    use_model_adapter: bool = False,
    state_dir: Path | None = None,
) -> str:
    profile = _read_profile(profile_path)
    if not question.strip():
        raise ValueError("experience question must not be empty")
    observed_original: dict[str, Any] | None = None
    observation_record: dict[str, Any] | None = None
    if original_observations_path is not None:
        observation_record = _read_original_observations(
            original_observations_path
        )
        observed_original = next(
            (
                item
                for item in observation_record["observations"]
                if item["question"] == question
            ),
            None,
        )
        if observed_original is None:
            raise ValueError(
                "original observations have no output for this question"
            )
    profile_original = _matching_original(profile, question)
    original = observed_original or profile_original
    if profile["comparison"]["evidence_level"] == "direct" and original is None:
        raise ValueError(
            "direct comparison has no original output for this question"
        )
    _validate_run_evidence_level(run_dir, profile)
    runtime_input = deepcopy(profile["runtime_input"])
    runtime_input[profile["interaction"]["question_field"]] = question
    result = run_built_replica(run_dir, runtime_input, **_run_options(use_model_adapter, state_dir))
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("status"), str)
        or not isinstance(result.get("answer"), str)
        or not isinstance(result.get("citations"), list)
        or not all(isinstance(item, str) for item in result["citations"])
        or not isinstance(result.get("applied_rules"), list)
        or not all(isinstance(item, str) for item in result["applied_rules"])
    ):
        raise ValueError("Replica experience output has no text answer")
    comparison = profile["comparison"]
    sources = _source_texts(profile)
    unknown_citations = [
        source_id
        for source_id in result["citations"]
        if source_id not in sources
    ]
    if unknown_citations:
        raise ValueError(
            f"Replica returned an unknown citation: {unknown_citations[0]}"
        )
    lines = [
        f"Replica 체험: {profile['title']}",
        f"질문: {question}",
        f"근거 수준: {comparison['evidence_level']}",
        "원본 직접 비교: "
        + (
            "가능 (사용자 제공 관찰)"
            if observed_original is not None
            else ("가능" if original else "불가")
        ),
        f"비교 기준: {comparison['summary']}",
    ]
    if original is not None:
        original_output = original["output"]
        rendered_original = (
            original_output
            if isinstance(original_output, str)
            else json.dumps(original_output, ensure_ascii=False, sort_keys=True)
        )
        lines.extend(
            [
                *(
                    [f"원본 이름: {observation_record['original_name']}"]
                    if observed_original is not None
                    else []
                ),
                f"원본 출력: {rendered_original}",
                f"원본 근거: {original['source']}",
                *(
                    [f"관찰 시각: {original['captured_at']}"]
                    if observed_original is not None
                    else []
                ),
            ]
        )
    lines.extend(
        [
            f"상태: {result['status']}",
            f"답변: {result['answer']}",
            "출처:",
        ]
    )
    if result["citations"]:
        for source_id in result["citations"]:
            lines.append(f"- {source_id}: {sources[source_id]}")
    else:
        lines.append("- 없음")
    lines.append("적용 규칙:")
    if result["applied_rules"]:
        lines.extend(f"- {rule}" for rule in result["applied_rules"])
    else:
        lines.append("- 없음")
    return "\n".join(lines)


def experience_input_once(
    run_dir: Path,
    input_path: Path,
    output_path: Path | None = None,
    *,
    use_model_adapter: bool = False,
    state_dir: Path | None = None,
) -> str:
    runtime_input = _read_json_object(input_path, "experience input")
    replica_spec = _read_json_object(
        run_dir / "replica-spec.json",
        "Replica spec",
    )
    output_contract = replica_spec.get("output_contract")
    if isinstance(output_contract, str) and output_contract.strip() and is_bundle_run(run_dir):
        # An implementation bundle always answers in JSON; its contract is a researched description.
        output_contract = {"type": "json", "format": "application/json"}
    if (
        not isinstance(output_contract, dict)
        or not isinstance(output_contract.get("type"), str)
        or not isinstance(output_contract.get("format"), str)
    ):
        raise ValueError("Replica spec has no output contract")
    output_format = output_contract["format"]
    resolved_output: Path | None = None
    if output_format == "text/html":
        if output_path is None:
            raise ValueError("HTML experience requires --output PREVIEW.html")
        resolved_output = output_path.resolve()
        resolved_run = run_dir.resolve()
        if (
            resolved_output == resolved_run
            or resolved_run in resolved_output.parents
        ):
            raise ValueError(
                "HTML experience output must be outside the published run"
            )
    elif output_path is not None:
        raise ValueError("--output is supported only for HTML experience")
    result = run_built_replica(run_dir, runtime_input, **_run_options(use_model_adapter, state_dir))
    lines = [
        "Replica 체험",
        f"출력 형식: {output_format}",
    ]
    if output_format == "text/html":
        if not isinstance(result, str):
            raise ValueError("HTML Replica did not return text")
        assert resolved_output is not None
        try:
            with resolved_output.open("x", encoding="utf-8") as stream:
                stream.write(result)
        except FileExistsError:
            raise ValueError(
                f"experience output already exists: {resolved_output}"
            ) from None
        lines.append(f"HTML 미리보기: {resolved_output}")
    elif isinstance(result, str):
        lines.extend(["결과:", result])
    else:
        lines.extend(
            [
                "결과:",
                json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                ),
            ]
        )
    return "\n".join(lines)
