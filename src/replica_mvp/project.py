from __future__ import annotations

import json
import shlex
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any


EVIDENCE_LEVELS = {
    "direct": ("직접 기준선", "직접 비교 범위에서 재현"),
    "public": ("공개 기준선", "공개된 기능 구현 가능"),
    "claim_only": ("주장 기준선", "공개 주장 기반 구현 가능"),
}


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


def _run(command: str | Sequence[str], prompt: str, timeout: int) -> str:
    argv = shlex.split(command) if isinstance(command, str) else list(command)
    if not argv or not all(isinstance(item, str) and item for item in argv):
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
    replica_command: str | Sequence[str],
    judge_command: str | Sequence[str],
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
    for index, case in enumerate(tests, start=1):
        if not isinstance(case, dict) or not isinstance(case.get("input"), str) or not case["input"].strip():
            raise ValueError(f"test case {index} needs a non-empty input")
        output = _run(
            replica_command,
            f"{replica.get('system_prompt', '')}\n\nUSER INPUT:\n{case['input']}",
            timeout,
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
