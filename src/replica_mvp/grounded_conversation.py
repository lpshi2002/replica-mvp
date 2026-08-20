from __future__ import annotations

import re
import unicodedata
from typing import Any, Mapping

from .openai_grounded_model import request_grounded_candidate


_CONCEPT_ALIASES = {
    "begin": ("start", "begin", "first", "시작", "시자", "처음", "첫"),
    "focus": ("focus", "focused", "집중"),
    "study": ("study", "studi", "learn", "공부", "학습"),
    "task": ("task", "과제"),
}
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "can",
    "how",
    "i",
    "is",
    "me",
    "one",
    "should",
    "the",
    "to",
    "what",
    "with",
}
_PERSONAL_FACT_MARKERS = (
    "birthday",
    "children",
    "email",
    "favorite",
    "home address",
    "phone number",
    "salary",
    "spouse",
    "주소",
    "생일",
    "연봉",
    "배우자",
    "좋아하는",
)
_URGENT_MARKERS = (
    "cannotbreathe",
    "cantbreathe",
    "chestpain",
    "killmyself",
    "overdose",
    "shortnessofbreath",
    "suicide",
    "가슴이너무아",
    "가슴통증",
    "과다복용",
    "숨을못",
    "숨이안",
    "숨쉬기가너무힘",
    "숨쉬기가힘",
    "숨쉬기힘",
    "자살",
    "죽고싶",
    "호흡곤란",
)


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"[0-9a-z가-힣]+", normalized))


def _stem_english(token: str) -> str:
    if token.endswith("ing") and len(token) > 5:
        return token[:-3]
    if token.endswith("s") and len(token) > 4:
        return token[:-1]
    return token


def _features(value: str) -> set[str]:
    normalized = _normalize(value)
    compact = normalized.replace(" ", "")
    tokens = normalized.split()
    english_tokens = {
        _stem_english(token)
        for token in tokens
        if token.isascii()
    }
    features: set[str] = set()
    for concept, aliases in _CONCEPT_ALIASES.items():
        matched_aliases = [
            alias
            for alias in aliases
            if (
                _stem_english(alias) in english_tokens
                if alias.isascii()
                else alias in compact
            )
        ]
        if (
            concept == "study"
            and matched_aliases == ["study"]
            and "case study" in normalized
        ):
            continue
        if matched_aliases:
            features.add(f"concept:{concept}")
    for token in tokens:
        if token in _STOP_WORDS or len(token) < 3:
            continue
        if any(
            (
                _stem_english(alias) == _stem_english(token)
                if alias.isascii() and token.isascii()
                else alias in token
            )
            for aliases in _CONCEPT_ALIASES.values()
            for alias in aliases
        ):
            continue
        features.add(f"token:{_stem_english(token)}")
    return features


def _applied_grounding_rules(runtime_input: Mapping[str, Any]) -> list[str]:
    applied: list[str] = []
    for rule in runtime_input.get("style_rules", []):
        if isinstance(rule, str) and any(
            marker in rule.casefold() for marker in ("concise", "간결")
        ):
            applied.append(rule)
    for rule in runtime_input.get("safety_rules", []):
        if isinstance(rule, str) and any(
            marker in rule.casefold()
            for marker in ("invent", "근거", "지어내", "사실")
        ):
            applied.append(rule)
    return list(dict.fromkeys(applied))


def _unsupported_personal_fact(
    question: str,
    corpus: list[Any],
) -> bool:
    normalized_question = _normalize(question)
    corpus_text = " ".join(
        _normalize(item.get("text", ""))
        for item in corpus
        if isinstance(item, dict) and isinstance(item.get("text"), str)
    )

    def contains(value: str, marker: str) -> bool:
        if marker.isascii():
            pattern = re.escape(marker).replace(r"\ ", r"\s+")
            return bool(
                re.search(
                    rf"(?<![0-9a-z]){pattern}(?![0-9a-z])",
                    value,
                )
            )
        return marker in value.replace(" ", "")

    return any(
        contains(normalized_question, marker)
        and not contains(corpus_text, marker)
        for marker in _PERSONAL_FACT_MARKERS
    )


def _urgent_rule(runtime_input: Mapping[str, Any]) -> str | None:
    for rule in runtime_input.get("safety_rules", []):
        if not isinstance(rule, str):
            continue
        normalized_rule = rule.casefold()
        has_urgent_condition = any(
            marker in normalized_rule
            for marker in ("emergency", "symptom", "urgent", "긴급", "응급", "증상")
        )
        has_handoff_action = any(
            marker in normalized_rule
            for marker in (
                "call",
                "contact",
                "escalate",
                "handoff",
                "help",
                "seek",
                "도움",
                "연락",
                "요청",
                "이관",
            )
        )
        if has_urgent_condition and has_handoff_action:
            return rule
    return None


def _is_urgent(question: str) -> bool:
    compact = _normalize(question).replace(" ", "")
    return any(marker in compact for marker in _URGENT_MARKERS)


def _validate_corpus(corpus: list[Any]) -> None:
    source_ids: list[str] = []
    for item in corpus:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("source_id"), str)
            or not item["source_id"].strip()
            or not isinstance(item.get("text"), str)
            or not item["text"].strip()
        ):
            raise ValueError(
                "grounded corpus requires unique non-empty sources"
            )
        source_ids.append(item["source_id"])
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("grounded corpus requires unique non-empty sources")


def _model_grounded_answer(
    question: str,
    corpus: list[dict[str, str]],
    runtime_input: Mapping[str, Any],
) -> dict[str, Any] | None:
    style_rules = [
        rule
        for rule in runtime_input.get("style_rules", [])
        if isinstance(rule, str)
    ]
    safety_rules = [
        rule
        for rule in runtime_input.get("safety_rules", [])
        if isinstance(rule, str)
    ]
    candidate = request_grounded_candidate(
        question,
        corpus,
        style_rules,
        safety_rules,
    )
    if (
        not isinstance(candidate, dict)
        or set(candidate)
        != {
            "decision",
            "source_id",
            "exact_quote",
            "applied_rules",
        }
        or candidate.get("decision") != "answered"
        or not isinstance(candidate.get("source_id"), str)
        or not isinstance(candidate.get("exact_quote"), str)
        or not candidate["exact_quote"]
        or not isinstance(candidate.get("applied_rules"), list)
        or not all(isinstance(rule, str) for rule in candidate["applied_rules"])
    ):
        return None
    sources = {item["source_id"]: item["text"] for item in corpus}
    source_id = candidate["source_id"]
    if (
        source_id not in sources
        or candidate["exact_quote"] not in sources[source_id]
        or not set(candidate["applied_rules"]).issubset(
            {*style_rules, *safety_rules}
        )
    ):
        return None
    return {
        "status": "answered",
        "answer": candidate["exact_quote"],
        "citations": [source_id],
        "applied_rules": list(dict.fromkeys(candidate["applied_rules"])),
    }


def preflight_grounded_response(
    runtime_input: Mapping[str, Any],
    experience: Mapping[str, Any],
) -> dict[str, Any] | None:
    interaction = experience.get("interaction")
    if not isinstance(interaction, dict):
        return None
    question_field = interaction.get("question_field")
    question = (
        runtime_input.get(question_field)
        if isinstance(question_field, str)
        else None
    )
    if not isinstance(question, str):
        return None
    urgent_rule = _urgent_rule(runtime_input)
    if urgent_rule is not None and _is_urgent(question):
        korean = bool(re.search(r"[가-힣]", question))
        answer = (
            "긴급한 증상일 수 있습니다. 즉시 지역 응급 서비스나 자격을 "
            "갖춘 의료 전문가에게 도움을 요청하세요."
            if korean
            else "This may be urgent. Contact local emergency services or a "
            "qualified medical professional now."
        )
        return {
            "status": "handoff",
            "answer": answer,
            "citations": [],
            "applied_rules": [urgent_rule],
        }
    if runtime_input.get("creator_corpus") == []:
        fallback = runtime_input.get("fallback_text")
        if isinstance(fallback, str):
            return {
                "status": "insufficient_information",
                "answer": fallback,
                "citations": [],
                "applied_rules": _applied_grounding_rules(runtime_input),
            }
    return None


def strengthen_grounded_response(
    runtime_input: Mapping[str, Any],
    output: Any,
    experience: Mapping[str, Any],
    *,
    allow_model_adapter: bool = False,
) -> Any:
    preflight = preflight_grounded_response(runtime_input, experience)
    if preflight is not None:
        return preflight
    if not isinstance(output, dict):
        return output
    interaction = experience.get("interaction")
    if not isinstance(interaction, dict):
        return output
    question_field = interaction.get("question_field")
    question = (
        runtime_input.get(question_field)
        if isinstance(question_field, str)
        else None
    )
    corpus = runtime_input.get("creator_corpus")
    if not isinstance(question, str):
        return output
    if not isinstance(corpus, list):
        raise ValueError("grounded corpus requires unique non-empty sources")
    _validate_corpus(corpus)
    if _unsupported_personal_fact(question, corpus):
        fallback = runtime_input.get("fallback_text")
        if not isinstance(fallback, str):
            return output
        return {
            "status": "insufficient_information",
            "answer": fallback,
            "citations": [],
            "applied_rules": _applied_grounding_rules(runtime_input),
        }
    if output.get("status") == "answered":
        source_ids = {item["source_id"] for item in corpus}
        citations = output.get("citations")
        if (
            not isinstance(citations, list)
            or not citations
            or not all(
                isinstance(source_id, str) and source_id in source_ids
                for source_id in citations
            )
        ):
            raise ValueError(
                "grounded answer requires citations from the supplied corpus"
            )
    if output.get("status") != "insufficient_information":
        return output
    question_features = _features(question)
    best_source: tuple[int, str, str] | None = None
    for item in corpus:
        if not isinstance(item, dict):
            continue
        source_id = item.get("source_id")
        text = item.get("text")
        if not isinstance(source_id, str) or not isinstance(text, str):
            continue
        score = len(question_features & _features(text))
        if score >= 2 and (best_source is None or score > best_source[0]):
            best_source = (score, source_id, text)
    if best_source is None:
        if allow_model_adapter:
            return _model_grounded_answer(
                question,
                corpus,
                runtime_input,
            ) or output
        return output
    _, source_id, source_text = best_source
    return {
        "status": "answered",
        "answer": source_text,
        "citations": [source_id],
        "applied_rules": _applied_grounding_rules(runtime_input),
    }
