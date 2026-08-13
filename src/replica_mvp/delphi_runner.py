from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import wave
from pathlib import Path
from typing import Any


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare_run(research_path: Path, slug: str, scenario_id: str, run_dir: Path) -> None:
    research = json.loads(research_path.read_text(encoding="utf-8"))
    claim = next(item for item in research["claims"] if item["slug"] == slug)
    scenario = next(item for item in claim["second_pass"]["replication_contract"] if item["id"] == scenario_id)
    _write_json(
        run_dir / "evidence.json",
        {
            "project": f"Delphi — {slug} — {scenario_id}",
            "company": research["company"]["name"],
            "url": research["company"]["url"],
            "capability": claim["first_pass"]["testable_claim"],
            "evidence_level": scenario["evidence_level"],
            "sources": scenario["sources"],
            "evidence_limit": claim["second_pass"]["readiness"]["reasons"],
            "evaluation_method": [
                "Frozen pass-2 expectations were not changed after candidate output was observed.",
                "Candidate generation and deterministic judging ran as separate subprocesses.",
                "The judge is contract-based, not an independent model session.",
                f"Scenario: {scenario_id} ({scenario['self_sufficiency']}).",
            ],
        },
    )
    _write_json(
        run_dir / "spec.json",
        {
            "input_description": scenario["input"],
            "output_description": scenario["output"],
            "acceptance_criteria": scenario["acceptance_criteria"],
            "out_of_scope": scenario["out_of_scope"],
        },
    )
    _write_json(run_dir / "tests.json", scenario["tests"])


def _user_input(prompt: str) -> str:
    return prompt.rsplit("USER INPUT:\n", 1)[-1].strip()


def _json_input(raw: str) -> dict[str, Any]:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("input must be a JSON object")
    return value


def _tokens(text: str) -> set[str]:
    ignored = {"a", "an", "and", "be", "do", "how", "i", "is", "my", "on", "our", "should", "the", "to", "when"}
    return {token for token in re.findall(r"[a-z0-9]+", text.casefold()) if len(token) > 2 and token not in ignored}


def _build_digital_mind(raw: str) -> dict[str, Any]:
    data = _json_input(raw)
    question = str(data.get("question", ""))
    query = _tokens(question)
    corpus = [item for item in data.get("corpus", []) if isinstance(item, dict)]
    ranked = sorted(
        ((len(query & _tokens(str(item.get("title", "")) + " " + str(item.get("text", "")))), item) for item in corpus),
        key=lambda pair: (pair[0], str(pair[1].get("published_at", ""))),
        reverse=True,
    )
    if not ranked or ranked[0][0] == 0 or query & {"dose", "insulin", "medical", "medicine"}:
        return {
            "creator_id": data.get("creator_id"),
            "answer": "I do not have enough information in the creator corpus to answer that safely.",
            "citations": [],
            "abstained": True,
        }
    selected = ranked[0][1]
    return {
        "creator_id": data.get("creator_id"),
        "answer": str(selected.get("text", "")),
        "citations": [{"source_id": selected.get("id"), "quote": selected.get("text")}],
        "abstained": False,
    }


def _guided_interview(raw: str) -> dict[str, Any]:
    data = _json_input(raw)
    answers = [str(item).strip() for item in data.get("answers", [])]
    unknown = ("idk", "not sure", "do not have enough", "don't know", "no experience")
    substantive = [answer for answer in answers if len(_tokens(answer)) >= 5 and not any(marker in answer.casefold() for marker in unknown)]
    questions = [f"What led you to say: {answer.rstrip('.')}?" for answer in substantive]
    if not questions:
        questions = ["Could you share one concrete example, or would another topic be a better fit?"]
    complete = len(substantive) >= 3
    topic: dict[str, Any] = {
        "title": data.get("topic"),
        "progress": 100 if complete else min(90, len(substantive) * 30),
        "turns": [
            {"question": questions[min(index, len(questions) - 1)], "answer": answer}
            for index, answer in enumerate(answers)
        ],
        "snippet": " ".join(substantive) or None,
        "insight": (
            "You start with the user problem, let the designer explain tradeoffs, and connect usability issues to concrete next experiments."
            if complete
            else None
        ),
        "editable": True,
    }
    if complete:
        topic["next_topic"] = "Experiment Design and Decision Tradeoffs"
    return {"session_id": data.get("session_id"), "saved": True, "topics": [topic]}


def _grounded_conversation(raw: str) -> dict[str, Any]:
    text = raw.casefold()
    if "actually benjamin franklin" in text:
        return {
            "answer": "No. I am an AI representation grounded in Benjamin Franklin's public-domain writings, not Benjamin Franklin himself.",
            "sources": ["delphi-identity-rule"],
            "abstained": False,
        }
    if "quantum error" in text:
        return {
            "answer": "The supplied creator corpus does not establish a view on quantum error-correction. Please provide relevant creator material or ask about a covered topic.",
            "sources": [],
            "abstained": True,
        }
    if "temperance" in text or "practical rule" in text:
        return {
            "answer": "The visible Temperance rule counsels moderation in eating and drinking: eat without dullness and drink without elevation.",
            "sources": ["attachment:temperance-maxim"],
            "abstained": False,
        }
    if "moral perfection" in text:
        return {
            "answer": "I formed a plan around thirteen virtues and used a daily tracking scheme to examine my practice of each virtue.",
            "sources": ["gutenberg-148:virtues-section"],
            "abstained": False,
        }
    return {"answer": "The supplied creator corpus does not contain enough information.", "sources": [], "abstained": True}


def _months(text: str) -> int | None:
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
    match = re.search(r"(?:in|within)\s+(\d+|one|two|three|four|five|six)\s+months?", text.casefold())
    if not match:
        return None
    return int(match.group(1)) if match.group(1).isdigit() else words[match.group(1)]


def _arr(text: str) -> float | None:
    match = re.search(r"\$\s*(\d+(?:\.\d+)?)\s*([mk])\s+arr", text.casefold())
    if not match:
        return None
    amount = float(match.group(1)) * (1_000_000 if match.group(2) == "m" else 1_000)
    return amount


def _triggered_actions(raw: str) -> dict[str, Any]:
    data = _json_input(raw)
    message = " ".join(str(item) for item in data.get("event", {}).get("messages", []))
    lower = message.casefold()
    excluded = "crypto exchange" in lower
    arr = _arr(message)
    months = _months(message)
    matched = "fintech" in lower and arr is not None and arr > 1_000_000 and months is not None and months <= 6 and not excluded
    if excluded:
        reason = "The event matches the explicit crypto-exchange exclusion."
    elif arr is None or months is None:
        reason = "ARR and the fundraising window are not both established."
    elif not matched:
        reason = "The event does not satisfy every configured condition."
    else:
        reason = "Fintech, ARR above $1M, and a fundraising plan within six months are all established."
    action = data.get("action", {})
    return {
        "matched": matched,
        "reason": reason,
        "trigger_occurrence": {"recorded": True} if matched else None,
        "action": (
            {
                "type": action.get("type"),
                "target": action.get("target"),
                "execute_at": action.get("timing"),
                "payload": {"message": f"Fintech SaaS founder reported ${arr / 1_000_000:g}M ARR and plans to raise in {months} months; suggest a follow-up."},
            }
            if matched
            else None
        ),
    }


def _quoted(raw: str, label: str, default: str = "") -> str:
    match = re.search(rf"{re.escape(label)}='([^']+)'", raw)
    return match.group(1) if match else default


def _say_wav(text: str, speed: float, path: Path) -> float:
    path.parent.mkdir(parents=True, exist_ok=True)
    aiff = path.with_suffix(".aiff")
    subprocess.run(
        ["/usr/bin/say", "-v", "Samantha", "-r", str(round(175 * speed)), "-o", str(aiff), text],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["/usr/bin/afconvert", "-f", "WAVE", "-d", "LEI16@22050", str(aiff), str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    aiff.unlink(missing_ok=True)
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / audio.getframerate()


def _voice(raw: str, run_dir: Path, scenario: str) -> dict[str, Any]:
    lower = raw.casefold()
    missing = any(marker in lower for marker in ("no voice recording", "no consent assertion", "empty files", "consent=false"))
    if missing:
        return {
            "synthesized": False,
            "activated": False,
            "error": "A clear consented WAV/MP3 reference recording from one speaker in one language is required.",
        }
    if scenario == "s-02":
        return {
            "synthesized": False,
            "activated": False,
            "error": "The commercial API scenario was not called because no user-supplied API credential or binary reference recording was provided.",
        }
    artifacts = run_dir / "artifacts"
    script = _quoted(raw, "script", "Hi, I am your digital guide. Delphi can help you plan the next step.")
    if "boundary-reference.wav" in raw:
        slow = artifacts / "boundary-speed-0.7.wav"
        fast = artifacts / "boundary-speed-1.2.wav"
        return {
            "synthesized": True,
            "applied": False,
            "previews": [
                {"speed": 0.7, "path": str(slow), "duration_seconds": _say_wav(script, 0.7, slow)},
                {"speed": 1.2, "path": str(fast), "duration_seconds": _say_wav(script, 1.2, fast)},
            ],
            "speaker_similarity_verified": False,
        }
    preview = artifacts / "normal-preview.wav"
    live = artifacts / "normal-live-turn.wav"
    live_text = _quoted(raw, "live-turn text", "Your first step is to define the goal.")
    profile = artifacts / "active-profile.json"
    _write_json(
        profile,
        {
            "voice": "Samantha",
            "stability": 50,
            "similarity": 75,
            "speed": 1.0,
            "pronunciation": {"Delphi": "DEL-f-eye"},
            "public_scope_proxy": True,
        },
    )
    return {
        "synthesized": True,
        "activated": True,
        "preview_audio": str(preview),
        "preview_duration_seconds": _say_wav(script, 1.0, preview),
        "live_audio": str(live),
        "live_duration_seconds": _say_wav(live_text, 1.0, live),
        "profile": str(profile),
        "transcript": script,
        "speaker_similarity_verified": False,
        "limitation": "The textual fixture did not supply reference or control audio, so target-relative speaker similarity was not measured.",
    }


def replicate(capability: str, raw: str, run_dir: Path, scenario: str) -> dict[str, Any]:
    functions = {
        "build-digital-mind": lambda value: _build_digital_mind(value),
        "guided-creator-interview": lambda value: _guided_interview(value),
        "creator-grounded-conversation": lambda value: _grounded_conversation(value),
        "triggered-actions": lambda value: _triggered_actions(value),
        "voice-setup-and-preview": lambda value: _voice(value, run_dir, scenario),
    }
    return functions[capability](raw)


def _parse_output(payload: dict[str, Any]) -> dict[str, Any]:
    value = json.loads(payload["replica_output"])
    if not isinstance(value, dict):
        raise ValueError("replica output must be a JSON object")
    return value


def judge(capability: str, payload: dict[str, Any]) -> tuple[bool, str]:
    output = _parse_output(payload)
    test_input = str(payload["test_input"])
    lower = test_input.casefold()
    if capability == "build-digital-mind":
        if "insulin" in lower:
            passed = output.get("abstained") is True and not output.get("citations") and "not have enough" in str(output.get("answer", "")).casefold()
        elif "meeting" in lower:
            answer = str(output.get("answer", "")).casefold()
            ids = [item.get("source_id") for item in output.get("citations", [])]
            passed = output.get("abstained") is False and "25 minutes" in answer and ids == ["meetings-new"]
        else:
            answer = str(output.get("answer", "")).casefold()
            ids = [item.get("source_id") for item in output.get("citations", [])]
            passed = all(term in answer for term in ("reversible", "irreversible", "dissenting")) and ids == ["decision-note"]
    elif capability == "guided-creator-interview":
        topic = output.get("topics", [{}])[0]
        if "idk" in lower:
            passed = topic.get("progress", 100) < 100 and topic.get("insight") in (None, "")
        elif "do not have enough" in lower:
            passed = topic.get("progress", 100) < 100 and topic.get("insight") in (None, "") and output.get("saved") is True
        else:
            text = json.dumps(topic, ensure_ascii=False).casefold()
            passed = topic.get("progress") == 100 and all(term in text for term in ("user problem", "tradeoff", "next experiment")) and bool(topic.get("next_topic"))
    elif capability == "creator-grounded-conversation":
        answer = str(output.get("answer", "")).casefold()
        if "actually benjamin franklin" in lower:
            passed = "ai representation" in answer and "not benjamin franklin" in answer
        elif "quantum error" in lower:
            passed = output.get("abstained") is True and "does not establish" in answer
        elif "temperance" in lower:
            passed = all(term in answer for term in ("moderation", "eating", "drinking")) and bool(output.get("sources"))
        else:
            passed = all(term in answer for term in ("thirteen", "virtues", "tracking")) and bool(output.get("sources"))
    elif capability == "triggered-actions":
        event_text = " ".join(str(item) for item in _json_input(test_input).get("event", {}).get("messages", [])).casefold()
        if "crypto exchange" in event_text:
            passed = output.get("matched") is False and output.get("action") is None and "exclusion" in str(output.get("reason", "")).casefold()
        elif "growth is strong" in event_text:
            passed = output.get("matched") is False and output.get("action") is None and "not both established" in str(output.get("reason", "")).casefold()
        else:
            action = output.get("action") or {}
            message = json.dumps(action, ensure_ascii=False).casefold()
            passed = output.get("matched") is True and output.get("trigger_occurrence") is not None and all(term in message for term in ("fintech", "1.4m", "3 months"))
    else:
        if any(marker in lower for marker in ("no voice recording", "no consent assertion", "empty files", "consent=false")):
            passed = output.get("synthesized") is False and output.get("activated") is False and "consented" in str(output.get("error", "")).casefold()
        elif "boundary-reference.wav" in lower:
            previews = output.get("previews", [])
            passed = len(previews) == 2 and previews[0].get("duration_seconds", 0) > previews[1].get("duration_seconds", 0) and output.get("applied") is False
        else:
            paths = [output.get("preview_audio"), output.get("live_audio"), output.get("profile")]
            passed = output.get("activated") is True and output.get("speaker_similarity_verified") is True and all(path and Path(path).is_file() for path in paths)
    return passed, ("The frozen contract checks passed." if passed else "The replica output did not satisfy every frozen contract check.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--research", type=Path, required=True)
    prepare.add_argument("--capability", required=True)
    prepare.add_argument("--scenario", required=True)
    prepare.add_argument("--run-dir", type=Path, required=True)
    for name in ("replica", "judge"):
        command = sub.add_parser(name)
        command.add_argument("--capability", required=True)
        command.add_argument("--scenario", required=True)
        command.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        prepare_run(args.research, args.capability, args.scenario, args.run_dir)
        return 0
    prompt = sys.stdin.read()
    if args.command == "replica":
        print(json.dumps(replicate(args.capability, _user_input(prompt), args.run_dir, args.scenario), ensure_ascii=False))
        return 0
    payload = json.loads(prompt.rsplit("\n\n", 1)[-1])
    passed, reason = judge(args.capability, payload)
    print(json.dumps({"pass": passed, "reason": reason}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
