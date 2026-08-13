from __future__ import annotations

import json
import re
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EVIDENCE_LEVELS = {
    "direct": ("직접 기준선", "직접 비교 범위에서 재현"),
    "public": ("공개 기준선", "공개된 기능 구현 가능"),
    "claim_only": ("주장 기준선", "공개 주장 기반 구현 가능"),
}

FIRST_PASS_SCOPES = {
    "official_surfaces": "first_pass/official-surfaces.json",
    "engineering_blog": "first_pass/engineering-blog.json",
    "discovered_names": "first_pass/discovered-names.json",
    "people_and_organizations": "first_pass/people-and-organizations.json",
    "supplementary_sources": "first_pass/supplementary-sources.json",
}
EXCLUSION_REASONS = (
    "outcome_metric",
    "non_technical",
    "no_ai_attribution",
    "internal_workflow",
)
DEFERRED_REASONS = (
    "no_company_attribution",
    "no_customer_delivery",
    "not_workflow",
)
CUSTOMER_DELIVERIES = ("public_product", "customer_deployment")
DEFERRED_DECISIONS = (
    "promoted_to_claim",
    "attached_to_claim",
    "excluded",
)
_RETIRED_FIRST_PASS_FIELDS = ("scores", "total", "selected", "disposition")


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path, expected: type) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"missing file: {path}") from None
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON in {path}: {error}") from None
    if not isinstance(value, expected):
        raise ValueError(f"{path} must contain a JSON {expected.__name__}")
    return value


def init_project(
    root: Path,
    *,
    name: str,
    company: str,
    url: str,
    capability: str,
    evidence_level: str = "claim_only",
) -> None:
    if evidence_level not in EVIDENCE_LEVELS:
        raise ValueError(f"unknown evidence level: {evidence_level}")
    root.mkdir(parents=True, exist_ok=True)
    managed = ("evidence.json", "spec.json", "tests.json")
    existing = [filename for filename in managed if (root / filename).exists()]
    if existing:
        raise ValueError(f"refusing to overwrite: {', '.join(existing)}")

    _write_json(
        root / "evidence.json",
        {
            "project": name,
            "company": company,
            "url": url,
            "capability": capability,
            "evidence_level": evidence_level,
            "sources": [
                {
                    "type": "claim",
                    "url": url,
                    "excerpt": "CHANGE_ME: 공개 자료에서 확인한 주장이나 동작",
                }
            ],
        },
    )
    _write_json(
        root / "spec.json",
        {
            "input_description": "CHANGE_ME: Replica가 받을 입력",
            "output_description": "CHANGE_ME: Replica가 만들어야 할 출력",
            "acceptance_criteria": [
                "CHANGE_ME: 정확성 기준",
                "CHANGE_ME: 핵심 작업 완결성 기준",
                "CHANGE_ME: 근거 제공 기준",
            ],
            "out_of_scope": ["원제품 내부 구현", "비공개 데이터", "원제품 전체 복제"],
        },
    )
    _write_json(
        root / "tests.json",
        [
            {
                "id": kind,
                "input": "CHANGE_ME",
                "expected_behavior": "CHANGE_ME",
                "reference_facts": [],
            }
            for kind in ("normal", "boundary", "insufficient-information")
        ],
    )


def _nonempty_strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{label} must be a non-empty list of strings")
    return value


def build_project(root: Path) -> dict[str, Any]:
    evidence = _read_json(root / "evidence.json", dict)
    spec = _read_json(root / "spec.json", dict)
    level = evidence.get("evidence_level")
    if level not in EVIDENCE_LEVELS:
        raise ValueError("evidence.json has an invalid evidence_level")
    sources = evidence.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("evidence.json needs at least one public source")
    criteria = _nonempty_strings(spec.get("acceptance_criteria"), "acceptance_criteria")

    source_text = "\n".join(
        f"- {source.get('url', 'unknown source')}: {source.get('excerpt', '')}"
        for source in sources
        if isinstance(source, dict)
    )
    prompt = f"""You reproduce only the publicly observable capability below.

Company: {evidence.get('company', '')}
Capability: {evidence.get('capability', '')}
Evidence level: {level}

Public evidence:
{source_text}

Input contract:
{spec.get('input_description', '')}

Output contract:
{spec.get('output_description', '')}

Acceptance criteria:
{chr(10).join(f'- {criterion}' for criterion in criteria)}

Do not claim access to private data or the original implementation. If the input is insufficient, say exactly what is missing. Return only the requested result."""
    replica = {
        "version": 1,
        "name": f"{evidence.get('company', 'Unknown')} — {evidence.get('capability', 'Replica')}",
        "evidence_level": level,
        "system_prompt": prompt,
    }
    _write_json(root / "replica.json", replica)
    return replica


def _run(command: str, prompt: str, timeout: int) -> str:
    argv = shlex.split(command)
    if not argv:
        raise ValueError("model command cannot be empty")
    try:
        completed = subprocess.run(
            argv,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"model command timed out after {timeout}s") from None
    if completed.returncode:
        detail = completed.stderr.strip() or f"exit code {completed.returncode}"
        raise RuntimeError(f"model command failed: {detail}")
    output = completed.stdout.strip()
    if not output:
        raise RuntimeError("model command returned no output")
    return output


def _judge_result(raw: str) -> tuple[bool, str]:
    text = raw.strip()
    if text.startswith("```") and text.endswith("```"):
        text = "\n".join(text.splitlines()[1:-1]).removeprefix("json").lstrip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"judge must return JSON: {error}") from None
    if not isinstance(result, dict) or not isinstance(result.get("pass"), bool):
        raise RuntimeError('judge JSON must contain boolean field "pass"')
    reason = result.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise RuntimeError('judge JSON must contain non-empty string field "reason"')
    return result["pass"], reason.strip()


def evaluate_project(
    root: Path,
    *,
    replica_command: str,
    judge_command: str,
    timeout: int = 120,
) -> list[dict[str, Any]]:
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    evidence = _read_json(root / "evidence.json", dict)
    spec = _read_json(root / "spec.json", dict)
    replica = _read_json(root / "replica.json", dict)
    tests = _read_json(root / "tests.json", list)
    if len(tests) < 3:
        raise ValueError("tests.json needs at least three independent cases")
    criteria = _nonempty_strings(spec.get("acceptance_criteria"), "acceptance_criteria")

    results: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    for index, case in enumerate(tests, start=1):
        if not isinstance(case, dict) or not isinstance(case.get("input"), str) or not case["input"].strip():
            raise ValueError(f"test case {index} needs a non-empty input")
        output = _run(
            replica_command,
            f"{replica.get('system_prompt', '')}\n\nUSER INPUT:\n{case['input']}",
            timeout,
        )
        outputs.append(
            {
                "case_id": case.get("id", f"case-{index}"),
                "input": case["input"],
                "replica_output": output,
            }
        )
        (root / "replica_outputs.jsonl").write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in outputs),
            encoding="utf-8",
        )
        judge_payload = {
            "evaluation_rule": "Would the same user accept this output for the stated public capability?",
            "evidence_level": evidence.get("evidence_level"),
            "capability": evidence.get("capability"),
            "acceptance_criteria": criteria,
            "test_input": case["input"],
            "expected_behavior": case.get("expected_behavior", ""),
            "reference_facts": case.get("reference_facts", []),
            "original_output": case.get("original_output"),
            "replica_output": output,
        }
        judge_prompt = (
            "Evaluate only the supplied evidence and acceptance criteria. "
            "Do not infer private product behavior. Return JSON only as "
            '{"pass": true|false, "reason": "one concrete sentence"}.\n\n'
            + json.dumps(judge_payload, ensure_ascii=False, indent=2)
        )
        passed, reason = _judge_result(_run(judge_command, judge_prompt, timeout))
        results.append(
            {
                "case_id": case.get("id", f"case-{index}"),
                "input": case["input"],
                "replica_output": output,
                "pass": passed,
                "reason": reason,
            }
        )

    (root / "results.jsonl").write_text(
        "".join(json.dumps(result, ensure_ascii=False) + "\n" for result in results),
        encoding="utf-8",
    )
    write_report(root)
    return results


def _read_results(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        raise ValueError(f"missing file: {path}") from None
    try:
        results = [json.loads(line) for line in lines if line.strip()]
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSONL in {path}: {error}") from None
    if not results:
        raise ValueError("results.jsonl is empty")
    return results


def write_report(root: Path) -> Path:
    evidence = _read_json(root / "evidence.json", dict)
    spec = _read_json(root / "spec.json", dict)
    tests = _read_json(root / "tests.json", list)
    results = _read_results(root / "results.jsonl")
    passed = sum(result.get("pass") is True for result in results)
    level = evidence.get("evidence_level")
    if level not in EVIDENCE_LEVELS:
        raise ValueError("evidence.json has an invalid evidence_level")
    level_label, success_label = EVIDENCE_LEVELS[level]
    verdict = success_label if passed == len(results) else ("부분 구현" if passed else "현재 Replica 미구현")
    sources = "\n\n".join(
        f"### 근거 {index}: {source.get('type', 'source')}\n\n"
        f"- 출처: [{source.get('url', 'unknown')}]({source.get('url', 'unknown')})\n"
        f"- 검토한 주장: {source.get('excerpt', '')}"
        for index, source in enumerate(evidence.get("sources", []), start=1)
        if isinstance(source, dict)
    )
    criteria = "\n".join(f"{index}. {item}" for index, item in enumerate(spec.get("acceptance_criteria", []), start=1))
    method_notes = "\n".join(f"- {item}" for item in evidence.get("evaluation_method", []))
    tests_by_id = {
        case.get("id", f"case-{index}"): case
        for index, case in enumerate(tests, start=1)
        if isinstance(case, dict)
    }
    case_sections = []
    for result in results:
        case_id = result.get("case_id", "unknown")
        case = tests_by_id.get(case_id, {})
        output = result.get("replica_output", "")
        output_text = (
            json.dumps(output, ensure_ascii=False, indent=2)
            if isinstance(output, (dict, list))
            else str(output)
        )
        reference_facts = "\n".join(f"- {fact}" for fact in case.get("reference_facts", [])) or "- 없음"
        case_sections.append(
            f"### `{case_id}` — {'PASS' if result.get('pass') else 'FAIL'}\n\n"
            f"- 기대 동작: {case.get('expected_behavior', '')}\n"
            f"- Judge 결론: {result.get('reason', '')}\n\n"
            f"#### 검토 입력\n\n```text\n{case.get('input', result.get('input', ''))}\n```\n\n"
            f"#### 참조 사실\n\n{reference_facts}\n\n"
            f"#### Replica 결과\n\n```json\n{output_text}\n```"
        )
    cases = "\n\n".join(case_sections)
    limitations = "\n".join(f"- {item}" for item in spec.get("out_of_scope", []))
    original_outputs = any(
        isinstance(case, dict) and case.get("original_output") not in (None, "")
        for case in tests
    )
    comparison_note = (
        "원제품 출력이 포함되어 직접 비교했다."
        if original_outputs
        else "원제품 출력은 확보하지 못했다. 따라서 공개 설명을 기준으로 기능 구현 가능성만 평가했다."
    )
    report = f"""# {evidence.get('project', 'Replica')} 결과

## 요약

- 대상 기업: {evidence.get('company', '')}
- 대상 기능: {evidence.get('capability', '')}
- 비교 근거: {level_label}
- 테스트 결과: {passed}/{len(results)} 통과
- 판정: **{verdict}**

이 평가는 `{evidence.get('capability', '')}`라는 공개 주장을 최소한의 텍스트 입출력 기능으로 재구성해 검토한 결과다. {comparison_note}

## 검토한 공개 주장

{sources or '- 기록된 공개 출처 없음'}

### 근거 한계

{evidence.get('evidence_limit', comparison_note)}

## 평가 방법

### 입력 계약

{spec.get('input_description', '')}

### 출력 계약

{spec.get('output_description', '')}

### 통과 기준

{criteria}

### 실행 방식

- 테스트 사례와 기대 동작, 참조 사실을 Replica 실행 전에 고정했다.
- 각 Replica 결과를 통과 기준, 기대 동작, 참조 사실에 대조해 Judge가 PASS 또는 FAIL로 판정했다.
- 전체 테스트가 끝난 뒤 통과 수를 집계했다.
{method_notes}

## 사례별 상세 결과

{cases}

## 결론

- 현재 Replica는 준비한 {len(results)}개 사례 중 {passed}개를 통과했다.
- 현재 근거 수준에서의 결론은 **{verdict}**이다.
- 이 결론이 지지하는 범위는 선택한 공개 기능과 명시된 테스트 계약 안에서의 구현 가능성이다.
- 이 결론은 원제품과 같은 모델, 정확도, UX, 보안, 통합 기능 또는 전체 계약 검토 성능을 입증하지 않는다.

## 확인하지 못한 범위

{limitations}
- 이 결과는 기업 전체, 비공개 데이터, 내부 구현의 복제를 입증하지 않는다.
"""
    path = root / "report.md"
    path.write_text(report, encoding="utf-8")
    return path


def _filled_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and "CHANGE_ME" not in value


def _normalized(text: str) -> str:
    return " ".join(text.split()).casefold()


def _validate_sources(sources: Any, label: str) -> str | None:
    if not isinstance(sources, list) or not sources:
        return f"{label}.sources must not be empty"
    for source in sources:
        if not isinstance(source, dict) or not _filled_text(source.get("url")) or not _filled_text(source.get("excerpt")):
            return f"{label} has an invalid source"
    return None


def _validate_customer_basis(candidate: dict[str, Any], label: str) -> str | None:
    """Require evidence that an external user receives the capability."""
    basis = candidate.get("customer_basis")
    if not isinstance(basis, dict):
        return f"{label}.customer_basis must be an object"
    if basis.get("delivery") not in CUSTOMER_DELIVERIES:
        return f"{label}.customer_basis.delivery must be one of {', '.join(CUSTOMER_DELIVERIES)}"
    for field in ("subject", "audience", "quote"):
        if not _filled_text(basis.get(field)):
            return f"{label}.customer_basis.{field} must be filled"

    sources = candidate["sources"]
    index = basis.get("source_index")
    error = _source_index(index, sources, f"{label}.customer_basis.source_index")
    if error:
        return error
    if _normalized(basis["subject"]) not in _normalized(basis["quote"]):
        return f"{label}.customer_basis.quote must contain the attributed subject {basis['subject']!r}"
    if _normalized(basis["quote"]) not in _normalized(sources[index - 1]["excerpt"]):
        return f"{label}.customer_basis.quote must appear in the excerpt of source {index}"
    return None


def _validate_ai_basis(candidate: dict[str, Any], label: str) -> str | None:
    """Require quoted, source-anchored evidence that the claim is about AI."""
    basis = candidate.get("ai_basis")
    if not isinstance(basis, dict):
        return f"{label}.ai_basis must be an object"
    for field in ("mechanism", "quote"):
        if not _filled_text(basis.get(field)):
            return f"{label}.ai_basis.{field} must be filled"

    term_groups = {}
    for field in ("signals", "work_signals"):
        terms = basis.get(field)
        if not isinstance(terms, list) or not terms or not all(_filled_text(term) for term in terms):
            return f"{label}.ai_basis.{field} must be a non-empty list of terms"
        term_groups[field] = terms

    sources = candidate["sources"]
    index = basis.get("source_index")
    error = _source_index(index, sources, f"{label}.ai_basis.source_index")
    if error:
        return error

    quote = _normalized(basis["quote"])
    for field, terms in term_groups.items():
        for term in terms:
            if _normalized(term) not in quote:
                return f"{label}.ai_basis.quote must contain the {field[:-1]} {term!r}"
    if quote not in _normalized(sources[index - 1]["excerpt"]):
        return f"{label}.ai_basis.quote must appear in the excerpt of source {index}"

    required_terms = [_normalized(term) for terms in term_groups.values() for term in terms]
    sentences = [_normalized(sentence) for sentence in re.split(r"(?<=[.!?])\s+", basis["quote"].strip())]
    if not any(all(term in sentence for term in required_terms) for sentence in sentences):
        return f"{label}.ai_basis.quote must directly connect the AI and claimed work in one sentence"
    return None


def _source_index(value: Any, sources: list[Any], label: str) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= len(sources):
        return f"{label} must be a 1-based index into sources"
    return None


def _validate_workflow(candidate: dict[str, Any], label: str) -> str | None:
    """Require one whole workflow with documented input, steps, and output."""
    workflow = candidate.get("workflow")
    if not isinstance(workflow, dict):
        return f"{label}.workflow must be an object"
    for field in ("input", "output"):
        if not _filled_text(workflow.get(field)):
            return f"{label}.workflow.{field} must be filled"

    steps = workflow.get("steps")
    if not isinstance(steps, list):
        return f"{label}.workflow.steps must be a list"
    sources = candidate["sources"]
    for position, step in enumerate(steps, start=1):
        if not isinstance(step, dict) or not _filled_text(step.get("step")):
            return f"{label}.workflow.steps {position} needs step text"
        error = _source_index(step.get("source_index"), sources, f"{label}.workflow.steps {position}.source_index")
        if error:
            return error
    return None


def _validate_replication_leads(candidate: dict[str, Any], label: str) -> str | None:
    leads = candidate.get("replication_leads")
    if not isinstance(leads, list):
        return f"{label}.replication_leads must be a list"
    sources = candidate["sources"]
    for position, lead in enumerate(leads, start=1):
        if not isinstance(lead, dict):
            return f"{label}.replication_leads {position} must be an object"
        for field in ("kind", "finding"):
            if not _filled_text(lead.get(field)):
                return f"{label}.replication_leads {position}.{field} must be filled"
        error = _source_index(
            lead.get("source_index"),
            sources,
            f"{label}.replication_leads {position}.source_index",
        )
        if error:
            return error
    return None


def _validate_exclusions(excluded: Any, label: str) -> str | None:
    if not isinstance(excluded, list):
        return f"{label}.excluded must be a list"
    for index, entry in enumerate(excluded, start=1):
        if not isinstance(entry, dict) or not _filled_text(entry.get("claim")):
            return f"{label}.excluded {index} needs claim text"
        if entry.get("reason") not in EXCLUSION_REASONS:
            return f"{label}.excluded {index}.reason must be one of {', '.join(EXCLUSION_REASONS)}"
    return None


def _validate_deferred(deferred: Any, label: str) -> str | None:
    if not isinstance(deferred, list):
        return f"{label}.deferred must be a list"
    ids: set[str] = set()
    for index, entry in enumerate(deferred, start=1):
        entry_label = f"{label}.deferred {index}"
        if not isinstance(entry, dict):
            return f"{entry_label} must be an object"
        for field in ("id", "claim", "url", "excerpt"):
            if not _filled_text(entry.get(field)):
                return f"{entry_label}.{field} must be filled"
        if entry["id"] in ids:
            return f"{entry_label}.id must be unique"
        ids.add(entry["id"])
        if entry.get("reason") not in DEFERRED_REASONS:
            return f"{entry_label}.reason must be one of {', '.join(DEFERRED_REASONS)}"
    return None


def _validate_checkpoint(path: Path, scope: str) -> tuple[dict[str, Any], str | None]:
    checkpoint = _read_json(path, dict)
    if checkpoint.get("schema_version") != 2:
        return checkpoint, f"{path}: schema_version must be 2"
    if checkpoint.get("scope") != scope:
        return checkpoint, f"{path}: scope must be {scope!r}"
    if checkpoint.get("status") != "complete":
        return checkpoint, f"{path}: status must be complete"
    if "chain_hints" in checkpoint:
        return checkpoint, f"{path}: chain_hints is retired; one claim must contain the whole workflow"

    assignment = checkpoint.get("assignment")
    if not isinstance(assignment, dict) or not isinstance(assignment.get("assigned"), list):
        return checkpoint, f"{path}: assignment.assigned must be a list"
    progress = checkpoint.get("progress")
    if not isinstance(progress, dict):
        return checkpoint, f"{path}: progress must be an object"
    if not isinstance(progress.get("completed"), list):
        return checkpoint, f"{path}: progress.completed must be a list"
    if progress.get("remaining") != []:
        return checkpoint, f"{path}: progress.remaining must be empty"
    if not isinstance(progress.get("discovered_names"), list):
        return checkpoint, f"{path}: progress.discovered_names must be a list"
    if not _filled_text(checkpoint.get("updated_at")):
        return checkpoint, f"{path}: updated_at must be set"

    claims = checkpoint.get("claims")
    if not isinstance(claims, list):
        return checkpoint, f"{path}: claims must be a list"
    claim_ids: set[str] = set()
    for index, candidate in enumerate(claims, start=1):
        label = f"claim {index}"
        if not isinstance(candidate, dict) or not _filled_text(candidate.get("id")) or not _filled_text(candidate.get("claim")):
            return checkpoint, f"{path}: {label} needs id and text"
        if candidate["id"] in claim_ids:
            return checkpoint, f"{path}: {label}.id must be unique"
        for field in _RETIRED_FIRST_PASS_FIELDS:
            if field in candidate:
                return checkpoint, f"{path}: {label}.{field} is retired; pass 1 no longer scores or selects"
        error = (
            _validate_sources(candidate.get("sources"), label)
            or _validate_customer_basis(candidate, label)
            or _validate_ai_basis(candidate, label)
            or _validate_workflow(candidate, label)
            or _validate_replication_leads(candidate, label)
        )
        if error:
            return checkpoint, f"{path}: {error}"
        claim_ids.add(candidate["id"])

    error = _validate_deferred(checkpoint.get("deferred"), "checkpoint")
    if error:
        return checkpoint, f"{path}: {error}"

    error = _validate_exclusions(checkpoint.get("excluded"), "checkpoint")
    if error:
        return checkpoint, f"{path}: {error}"
    return checkpoint, None


def _validate_first_pass_claim(claim: Any, index: int) -> str | None:
    label = f"claim {index}"
    if not isinstance(claim, dict):
        return f"{label} must be an object"
    if not _filled_text(claim.get("id")) or not _filled_text(claim.get("slug")):
        return f"{label} needs id and slug"
    first = claim.get("first_pass")
    if not isinstance(first, dict):
        return f"{label}.first_pass must be an object"
    for field in ("claim", "testable_claim", "routing"):
        if not _filled_text(first.get(field)):
            return f"{label}.first_pass.{field} must be filled"

    error = _validate_sources(first.get("sources"), f"{label}.first_pass")
    if error:
        return error

    if "replicable" in first:
        return f"{label}.first_pass.replicable belongs to second_pass"
    for field in _RETIRED_FIRST_PASS_FIELDS:
        if field in first:
            return f"{label}.first_pass.{field} is retired; pass 1 no longer scores or selects"

    merged_from = first.get("merged_from", [])
    if not isinstance(merged_from, list) or not all(_filled_text(item) for item in merged_from):
        return f"{label}.first_pass.merged_from must be a list of absorbed claims"

    first_label = f"{label}.first_pass"
    return (
        _validate_customer_basis(first, first_label)
        or _validate_ai_basis(first, first_label)
        or _validate_workflow(first, first_label)
        or _validate_replication_leads(first, first_label)
    )


def _validate_deferred_resolutions(
    resolutions: Any,
    deferred_ids: set[str],
    claim_ids: set[str],
) -> tuple[int, str | None]:
    if not isinstance(resolutions, list):
        return 0, "research.json deferred_resolutions must be a list"
    resolved: set[str] = set()
    excluded_count = 0
    for position, resolution in enumerate(resolutions, start=1):
        label = f"deferred_resolution {position}"
        if not isinstance(resolution, dict):
            return 0, f"{label} must be an object"
        deferred_id = resolution.get("deferred_id")
        if deferred_id not in deferred_ids:
            return 0, f"{label}.deferred_id must reference a checkpoint deferred item"
        if deferred_id in resolved:
            return 0, f"{label}.deferred_id must be unique"
        resolved.add(deferred_id)
        decision = resolution.get("decision")
        if decision not in DEFERRED_DECISIONS:
            return 0, f"{label}.decision must be one of {', '.join(DEFERRED_DECISIONS)}"
        if not _filled_text(resolution.get("rationale")):
            return 0, f"{label}.rationale must be filled"

        target_id = resolution.get("target_id")
        if decision in ("promoted_to_claim", "attached_to_claim"):
            if target_id not in claim_ids:
                return 0, f"{label}.target_id must reference a final claim"
        elif _filled_text(target_id):
            return 0, f"{label}.target_id must be empty when excluded"
        else:
            excluded_count += 1

    missing = deferred_ids - resolved
    if missing:
        return 0, f"deferred item {sorted(missing)[0]!r} is unresolved"
    return excluded_count, None


def finalize_first_pass(company_root: Path) -> dict[str, Any]:
    research_path = company_root / "research.json"
    research = _read_json(research_path, dict)
    if research.get("schema_version") != 2:
        raise ValueError("research.json schema_version must be 2")
    if "chains" in research:
        raise ValueError("research.json chains is retired; one claim must contain the whole workflow")
    checkpoints: dict[str, dict[str, Any]] = {}
    deferred_ids: set[str] = set()
    for scope, relative_path in FIRST_PASS_SCOPES.items():
        checkpoint, error = _validate_checkpoint(company_root / relative_path, scope)
        if error:
            raise ValueError(error)
        checkpoints[scope] = checkpoint
        for entry in checkpoint["deferred"]:
            if entry["id"] in deferred_ids:
                raise ValueError(f"deferred id {entry['id']!r} must be unique across checkpoints")
            deferred_ids.add(entry["id"])

    claims = research.get("claims")
    if not isinstance(claims, list):
        raise ValueError("research.json claims must be a list")
    ids: set[str] = set()
    slugs: set[str] = set()
    for index, claim in enumerate(claims, start=1):
        error = _validate_first_pass_claim(claim, index)
        if error:
            raise ValueError(error)
        claim_id = claim["id"]
        slug = claim["slug"]
        if claim_id in ids or slug in slugs:
            raise ValueError(f"claim {index} duplicates an id or slug")
        ids.add(claim_id)
        slugs.add(slug)
    deferred_excluded_count, error = _validate_deferred_resolutions(
        research.get("deferred_resolutions"),
        deferred_ids,
        ids,
    )
    if error:
        raise ValueError(error)

    workflow = research.get("workflow")
    if not isinstance(workflow, dict):
        raise ValueError("research.json workflow must be an object")
    pass_1 = workflow.get("pass_1")
    if not isinstance(pass_1, dict):
        raise ValueError("research.json workflow.pass_1 must be an object")
    pass_1["coverage"] = {
        scope: {
            "status": "complete",
            "checkpoint": path,
            "claim_count": len(checkpoints[scope]["claims"]),
            "deferred_count": len(checkpoints[scope]["deferred"]),
            "excluded_count": len(checkpoints[scope].get("excluded", [])),
            "updated_at": checkpoints[scope]["updated_at"],
        }
        for scope, path in FIRST_PASS_SCOPES.items()
    }
    pass_1["completed_at"] = datetime.now(timezone.utc).isoformat()
    workflow["status"] = "pass_1_complete"

    excluded_count = (
        sum(len(checkpoint.get("excluded", [])) for checkpoint in checkpoints.values())
        + deferred_excluded_count
    )
    pass_2 = workflow.get("pass_2")
    if isinstance(pass_2, dict):
        pass_2["handoff_count"] = len(claims)
        pass_2.pop("claim_count", None)
        pass_2.pop("selected_count", None)
    summary = research.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("research.json summary must be an object")
    summary.pop("selected_count", None)
    summary.pop("chain_count", None)
    summary.update(
        {
            "candidate_count": len(claims),
            "excluded_count": excluded_count,
            "deferred_count": len(deferred_ids),
            "resolved_deferred_count": len(deferred_ids),
            "next_step": "run_pass_2" if claims else "no_ai_claims",
        }
    )
    _write_json(research_path, research)
    return research
