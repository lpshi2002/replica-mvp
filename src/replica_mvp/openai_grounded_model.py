from __future__ import annotations

import http.client
import json
import os
import urllib.request
from typing import Any, Mapping


_API_URL = "https://api.openai.com/v1/responses"
_DEFAULT_MODEL = "gpt-5.6-luna"
_MAX_PROMPT_BYTES = 50_000
_MAX_RESPONSE_BYTES = 256_000


def _response_text(response: Mapping[str, Any]) -> str:
    output_text = response.get("output_text")
    if isinstance(output_text, str):
        return output_text
    output = response.get("output")
    if not isinstance(output, list):
        raise ValueError("OpenAI response has no output text")
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if (
                isinstance(part, dict)
                and part.get("type") == "output_text"
                and isinstance(part.get("text"), str)
            ):
                return part["text"]
    raise ValueError("OpenAI response has no output text")


def request_grounded_candidate(
    question: str,
    corpus: list[dict[str, str]],
    style_rules: list[str],
    safety_rules: list[str],
) -> dict[str, Any] | None:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    model = os.environ.get("REPLICA_MVP_OPENAI_MODEL", _DEFAULT_MODEL).strip()
    if not model:
        model = _DEFAULT_MODEL
    evidence_input = json.dumps(
        {
            "question": question,
            "creator_corpus": corpus,
            "style_rules": style_rules,
            "safety_rules": safety_rules,
        },
        ensure_ascii=False,
        allow_nan=False,
    )
    if len(evidence_input.encode("utf-8")) > _MAX_PROMPT_BYTES:
        return None
    schema = {
        "type": "object",
        "properties": {
            "decision": {
                "type": "string",
                "enum": ["answered", "insufficient_information"],
            },
            "source_id": {"type": "string"},
            "exact_quote": {"type": "string"},
            "applied_rules": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": [
            "decision",
            "source_id",
            "exact_quote",
            "applied_rules",
        ],
        "additionalProperties": False,
    }
    payload = {
        "model": model,
        "store": False,
        "reasoning": {"effort": "low"},
        "instructions": (
            "Answer only from creator_corpus. If the evidence is insufficient, "
            "return insufficient_information with empty source_id, exact_quote, "
            "and applied_rules. For an answer, cite one source_id "
            "and copy the smallest complete supporting sentence into "
            "exact_quote. Never use "
            "conversation history or outside knowledge as factual evidence."
        ),
        "input": evidence_input,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "grounded_replica_candidate",
                "strict": True,
                "schema": schema,
            }
        },
        "max_output_tokens": 400,
    }
    request = urllib.request.Request(
        _API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            raw_response = response.read(_MAX_RESPONSE_BYTES + 1)
        if len(raw_response) > _MAX_RESPONSE_BYTES:
            return None
        response_value = json.loads(raw_response.decode("utf-8"))
        if not isinstance(response_value, dict):
            return None
        candidate = json.loads(_response_text(response_value))
        return candidate if isinstance(candidate, dict) else None
    except (
        OSError,
        TimeoutError,
        TypeError,
        UnicodeError,
        ValueError,
        http.client.HTTPException,
    ):
        return None
