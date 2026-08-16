import http.client
import json
import os
import subprocess
import unittest
from contextlib import redirect_stdout
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from replica_mvp import (
    finalize_codex_operator,
    prepare_codex_operator,
    run_built_replica,
)
from replica_mvp.cli import main
from replica_mvp.builder import _run_replica_in_subprocess


def _experience_profile() -> dict:
    return {
        "schema_version": "replica-experience/v1",
        "title": "Grounded conversation",
        "description": "Ask questions against a public synthetic corpus.",
        "interaction": {
            "type": "question_answer",
            "question_field": "user_question",
        },
        "runtime_input": {
            "creator_corpus": [
                {
                    "source_id": "src-public",
                    "text": "A study session starts with one focused task.",
                }
            ],
            "style_rules": ["Be concise."],
            "safety_rules": [
                "Do not invent facts.",
                "Escalate urgent requests.",
            ],
            "fallback_text": "Not enough public information.",
            "conversation_history": [],
        },
        "examples": [
            {
                "label": "Public demo question",
                "question": "How should I start a study session?",
            }
        ],
        "comparison": {
            "evidence_level": "public",
            "summary": "Compared with the public capability contract.",
            "original_outputs": [],
        },
    }


def _second_pass() -> dict:
    answered = {
        "status": "answered",
        "answer": "Start with one focused task.",
        "citations": ["src-public"],
        "applied_rules": ["Be concise."],
    }
    handoff = {
        "status": "handoff",
        "answer": "Ask a qualified professional for urgent help.",
        "citations": [],
        "applied_rules": ["Escalate urgent requests."],
    }
    insufficient = {
        "status": "insufficient_information",
        "answer": "Not enough public information.",
        "citations": [],
        "applied_rules": ["Do not invent facts."],
    }
    return {
        "schema_version": "replica-second-pass-result/v1",
        "replica_id": "demo-grounded-conversation",
        "company": "Demo Company",
        "capability": "answer questions from a supplied public corpus",
        "canonical_claim": "Answer or decline using only supplied evidence.",
        "evidence_level": "public",
        "readiness": "ready",
        "handoff": "build",
        "input_contract": {
            "type": "object",
            "required": [
                "creator_corpus",
                "style_rules",
                "safety_rules",
                "fallback_text",
                "conversation_history",
                "user_question",
            ],
        },
        "output_contract": {
            "type": "object",
            "format": "grounded-conversation-response",
        },
        "acceptance_criteria": [
            {
                "id": "criterion-behavior",
                "description": "Answer, hand off, or decline as appropriate.",
            }
        ],
        "implementation": {
            "strategy": "generated_component",
            "instructions": "Route the three supplied synthetic cases.",
        },
        "supported_scope": ["three deterministic synthetic routes"],
        "unsupported_scope": ["original product equivalence"],
        "limitations": ["small public synthetic corpus"],
        "experience": _experience_profile(),
        "tests": {
            "schema_version": "replica-tests/v1",
            "cases": [
                {
                    "id": "normal",
                    "kind": "normal",
                    "input": {
                        **_experience_profile()["runtime_input"],
                        "user_question": "study",
                    },
                    "deterministic_assertions": [
                        {"type": "equals", "value": answered}
                    ],
                    "criterion_ids": ["criterion-behavior"],
                    "semantic_criteria": [],
                },
                {
                    "id": "boundary",
                    "kind": "boundary",
                    "input": {
                        **_experience_profile()["runtime_input"],
                        "user_question": "urgent",
                    },
                    "deterministic_assertions": [
                        {"type": "equals", "value": handoff}
                    ],
                    "criterion_ids": ["criterion-behavior"],
                    "semantic_criteria": [],
                },
                {
                    "id": "insufficient",
                    "kind": "insufficient_information",
                    "input": {
                        **_experience_profile()["runtime_input"],
                        "user_question": "unknown",
                    },
                    "deterministic_assertions": [
                        {"type": "equals", "value": insufficient}
                    ],
                    "criterion_ids": ["criterion-behavior"],
                    "semantic_criteria": [],
                },
            ],
        },
    }


def _operator(request: dict) -> dict:
    source = (
        "def replicate(runtime_input):\n"
        "    question = str(runtime_input.get('user_question', '')).lower()\n"
        "    if 'study' in question:\n"
        "        return {'status': 'answered', 'answer': 'Start with one "
        "focused task.', 'citations': ['src-public'], "
        "'applied_rules': ['Be concise.']}\n"
        "    if 'urgent' in question:\n"
        "        return {'status': 'handoff', 'answer': 'Ask a qualified "
        "professional for urgent help.', 'citations': [], "
        "'applied_rules': ['Escalate urgent requests.']}\n"
        "    return {'status': 'insufficient_information', 'answer': "
        "runtime_input.get('fallback_text', ''), 'citations': [], "
        "'applied_rules': ['Do not invent facts.']}\n"
    )
    return {
        "schema_version": "replica-component-generation/v1",
        "generator_identity": "test/operator",
        "component": {
            "schema_version": "replica-generated-component/v1",
            "language": "replica-python/v1",
            "input_contract": request["input_contract"],
            "output_contract": request["output_contract"],
            "source": source,
        },
    }


def _write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _build_public_run(root: Path, second_pass: dict | None = None) -> Path:
    source = root / "second-pass.json"
    workspace = root / "workspace"
    vault = root / "vault"
    _write_json(source, second_pass or _second_pass())
    prepared = prepare_codex_operator(source, workspace, vault)
    request = json.loads(
        Path(prepared["request_path"]).read_text(encoding="utf-8")
    )
    _write_json(Path(prepared["operator_path"]), _operator(request))
    result = finalize_codex_operator(
        Path(prepared["task_dir"]),
        workspace,
        vault,
    )
    return Path(result["run_dir"])


class ExperiencePublicationTest(unittest.TestCase):
    def setUp(self):
        no_live_api = patch.dict(os.environ, {"OPENAI_API_KEY": ""})
        no_live_api.start()
        self.addCleanup(no_live_api.stop)

    def test_frozen_evaluator_does_not_inherit_the_openai_api_key(self):
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"status":"insufficient_information"}',
            stderr="",
        )
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "secret"}),
            patch(
                "replica_mvp.builder.subprocess.run",
                return_value=completed,
            ) as run_process,
        ):
            _run_replica_in_subprocess(
                Path("unused-run"),
                {},
                timeout_seconds=5,
                max_output_bytes=1_000,
            )

        evaluator_environment = run_process.call_args.kwargs["env"]
        self.assertNotIn("OPENAI_API_KEY", evaluator_environment)

    def test_model_adapter_answers_only_with_an_exact_corpus_quote(self):
        model_candidate = {
            "decision": "answered",
            "source_id": "src-public",
            "exact_quote": (
                "A study session starts with one focused task."
            ),
            "applied_rules": ["Be concise."],
        }
        api_response = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(model_candidate),
                        }
                    ],
                }
            ]
        }
        with TemporaryDirectory() as tmp:
            run_dir = _build_public_run(Path(tmp))
            runtime_input = dict(_experience_profile()["runtime_input"])
            runtime_input["user_question"] = (
                "What should I do first before schoolwork?"
            )
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}),
                patch(
                    "urllib.request.urlopen",
                    return_value=BytesIO(json.dumps(api_response).encode()),
                ) as call_api,
            ):
                result = run_built_replica(run_dir, runtime_input)

            self.assertEqual("answered", result["status"])
            self.assertEqual(
                "A study session starts with one focused task.",
                result["answer"],
            )
            self.assertEqual(["src-public"], result["citations"])
            call_api.assert_called_once()

    def test_model_adapter_can_be_disabled_for_interactive_execution(self):
        with TemporaryDirectory() as tmp:
            run_dir = _build_public_run(Path(tmp))
            runtime_input = dict(_experience_profile()["runtime_input"])
            runtime_input["user_question"] = (
                "What should I do first before schoolwork?"
            )
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}),
                patch("urllib.request.urlopen") as call_api,
            ):
                result = run_built_replica(
                    run_dir,
                    runtime_input,
                    allow_model_adapter=False,
                )

            self.assertEqual("insufficient_information", result["status"])
            self.assertEqual(runtime_input["fallback_text"], result["answer"])
            call_api.assert_not_called()

    def test_model_answer_with_an_unverified_quote_keeps_the_fallback(self):
        model_candidate = {
            "decision": "answered",
            "source_id": "src-public",
            "exact_quote": "words that are not in the source",
            "applied_rules": [],
        }
        api_response = {
            "output_text": json.dumps(model_candidate),
        }
        with TemporaryDirectory() as tmp:
            run_dir = _build_public_run(Path(tmp))
            runtime_input = dict(_experience_profile()["runtime_input"])
            runtime_input["user_question"] = (
                "What should I do first before schoolwork?"
            )
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}),
                patch(
                    "urllib.request.urlopen",
                    return_value=BytesIO(json.dumps(api_response).encode()),
                ),
            ):
                result = run_built_replica(run_dir, runtime_input)

            self.assertEqual("insufficient_information", result["status"])
            self.assertEqual(
                runtime_input["fallback_text"],
                result["answer"],
            )

    def test_model_outage_keeps_the_exact_fallback(self):
        with TemporaryDirectory() as tmp:
            run_dir = _build_public_run(Path(tmp))
            runtime_input = dict(_experience_profile()["runtime_input"])
            runtime_input["user_question"] = (
                "What should I do first before schoolwork?"
            )
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}),
                patch(
                    "urllib.request.urlopen",
                    side_effect=OSError("provider unavailable"),
                ),
            ):
                result = run_built_replica(run_dir, runtime_input)

            self.assertEqual("insufficient_information", result["status"])
            self.assertEqual(
                runtime_input["fallback_text"],
                result["answer"],
            )

    def test_truncated_model_response_keeps_the_exact_fallback(self):
        with TemporaryDirectory() as tmp:
            run_dir = _build_public_run(Path(tmp))
            runtime_input = dict(_experience_profile()["runtime_input"])
            runtime_input["user_question"] = (
                "What should I do first before schoolwork?"
            )
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}),
                patch(
                    "urllib.request.urlopen",
                    side_effect=http.client.IncompleteRead(b"partial"),
                ),
            ):
                result = run_built_replica(run_dir, runtime_input)

            self.assertEqual("insufficient_information", result["status"])
            self.assertEqual(
                runtime_input["fallback_text"],
                result["answer"],
            )

    def test_personal_fact_is_blocked_before_the_model_adapter(self):
        with TemporaryDirectory() as tmp:
            run_dir = _build_public_run(Path(tmp))
            runtime_input = dict(_experience_profile()["runtime_input"])
            runtime_input["user_question"] = (
                "What is the author's favorite routine?"
            )
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}),
                patch("urllib.request.urlopen") as call_api,
            ):
                result = run_built_replica(run_dir, runtime_input)

            self.assertEqual("insufficient_information", result["status"])
            call_api.assert_not_called()

    def test_deterministic_grounded_answer_does_not_call_the_model(self):
        with TemporaryDirectory() as tmp:
            run_dir = _build_public_run(Path(tmp))
            runtime_input = dict(_experience_profile()["runtime_input"])
            runtime_input["user_question"] = "공부를 어떻게 시작하면 돼?"
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}),
                patch("urllib.request.urlopen") as call_api,
            ):
                result = run_built_replica(run_dir, runtime_input)

            self.assertEqual("answered", result["status"])
            call_api.assert_not_called()

    def test_english_paraphrase_is_answered_from_the_published_source(self):
        with TemporaryDirectory() as tmp:
            run_dir = _build_public_run(Path(tmp))
            runtime_input = dict(_experience_profile()["runtime_input"])
            runtime_input["user_question"] = "How can I begin learning?"

            result = run_built_replica(run_dir, runtime_input)

            self.assertEqual("answered", result["status"])
            self.assertEqual(["src-public"], result["citations"])

    def test_korean_paraphrase_is_answered_from_the_published_source(self):
        with TemporaryDirectory() as tmp:
            run_dir = _build_public_run(Path(tmp))
            runtime_input = dict(_experience_profile()["runtime_input"])
            runtime_input["user_question"] = "공부를 어떻게 시작하면 돼?"

            result = run_built_replica(run_dir, runtime_input)

            self.assertEqual("answered", result["status"])
            self.assertEqual(
                "A study session starts with one focused task.",
                result["answer"],
            )
            self.assertEqual(["src-public"], result["citations"])

    def test_common_korean_typo_still_finds_the_published_source(self):
        with TemporaryDirectory() as tmp:
            run_dir = _build_public_run(Path(tmp))
            runtime_input = dict(_experience_profile()["runtime_input"])
            runtime_input["user_question"] = "공부 어케 시자캐?"

            result = run_built_replica(run_dir, runtime_input)

            self.assertEqual("answered", result["status"])
            self.assertEqual(["src-public"], result["citations"])

    def test_unsupported_personal_fact_keeps_the_exact_fallback(self):
        with TemporaryDirectory() as tmp:
            run_dir = _build_public_run(Path(tmp))
            runtime_input = dict(_experience_profile()["runtime_input"])
            runtime_input["user_question"] = (
                "What is the study author's favorite planet?"
            )

            result = run_built_replica(run_dir, runtime_input)

            self.assertEqual("insufficient_information", result["status"])
            self.assertEqual(
                runtime_input["fallback_text"],
                result["answer"],
            )
            self.assertEqual([], result["citations"])

    def test_korean_urgent_symptoms_are_handed_off_before_answering(self):
        with TemporaryDirectory() as tmp:
            run_dir = _build_public_run(Path(tmp))
            runtime_input = dict(_experience_profile()["runtime_input"])
            runtime_input["user_question"] = "숨을 못 쉬겠고 가슴이 너무 아파"

            result = run_built_replica(run_dir, runtime_input)

            self.assertEqual("handoff", result["status"])
            self.assertEqual([], result["citations"])
            self.assertEqual(
                ["Escalate urgent requests."],
                result["applied_rules"],
            )

    def test_english_urgent_symptoms_are_handed_off_before_answering(self):
        with TemporaryDirectory() as tmp:
            run_dir = _build_public_run(Path(tmp))
            runtime_input = dict(_experience_profile()["runtime_input"])
            runtime_input["user_question"] = (
                "I have chest pain and cannot breathe"
            )

            result = run_built_replica(run_dir, runtime_input)

            self.assertEqual("handoff", result["status"])
            self.assertEqual([], result["citations"])
            self.assertEqual(
                ["Escalate urgent requests."],
                result["applied_rules"],
            )

    def test_professional_tone_alone_does_not_enable_urgent_handoff(self):
        with TemporaryDirectory() as tmp:
            second_pass = _second_pass()
            second_pass["experience"]["runtime_input"]["safety_rules"] = [
                "Maintain a professional tone."
            ]
            for case in second_pass["tests"]["cases"]:
                case["input"]["safety_rules"] = [
                    "Maintain a professional tone."
                ]
            run_dir = _build_public_run(Path(tmp), second_pass)
            runtime_input = dict(
                second_pass["experience"]["runtime_input"]
            )
            runtime_input["user_question"] = "I have chest pain"

            result = run_built_replica(run_dir, runtime_input)

            self.assertEqual("insufficient_information", result["status"])

    def test_common_breathing_emergency_phrases_are_handed_off(self):
        with TemporaryDirectory() as tmp:
            run_dir = _build_public_run(Path(tmp))
            for question in (
                "숨쉬기가 너무 힘들어요",
                "I have severe shortness of breath",
            ):
                with self.subTest(question=question):
                    runtime_input = dict(
                        _experience_profile()["runtime_input"]
                    )
                    runtime_input["user_question"] = question

                    result = run_built_replica(run_dir, runtime_input)

                    self.assertEqual("handoff", result["status"])

    def test_ambiguous_duplicate_source_ids_are_rejected(self):
        with TemporaryDirectory() as tmp:
            run_dir = _build_public_run(Path(tmp))
            runtime_input = dict(_experience_profile()["runtime_input"])
            runtime_input["creator_corpus"] = [
                *runtime_input["creator_corpus"],
                {
                    "source_id": "src-public",
                    "text": "A different statement with the same ID.",
                },
            ]
            runtime_input["user_question"] = "How can I begin learning?"

            with self.assertRaisesRegex(
                ValueError,
                "grounded corpus requires unique non-empty sources",
            ):
                run_built_replica(run_dir, runtime_input)

    def test_urgent_handoff_wins_over_an_invalid_corpus(self):
        with TemporaryDirectory() as tmp:
            run_dir = _build_public_run(Path(tmp))
            runtime_input = dict(_experience_profile()["runtime_input"])
            runtime_input["creator_corpus"] = [
                *runtime_input["creator_corpus"],
                {
                    "source_id": "src-public",
                    "text": "A duplicate source.",
                },
            ]
            runtime_input["user_question"] = "I have chest pain"

            result = run_built_replica(run_dir, runtime_input)

            self.assertEqual("handoff", result["status"])

    def test_answered_output_requires_a_non_empty_cited_corpus(self):
        with TemporaryDirectory() as tmp:
            run_dir = _build_public_run(Path(tmp))
            runtime_input = dict(_experience_profile()["runtime_input"])
            runtime_input["creator_corpus"] = []
            runtime_input["user_question"] = "study"

            with self.assertRaisesRegex(
                ValueError,
                "grounded corpus requires unique non-empty sources",
            ):
                run_built_replica(run_dir, runtime_input)

    def test_non_list_corpus_is_rejected_after_the_urgent_gate(self):
        with TemporaryDirectory() as tmp:
            run_dir = _build_public_run(Path(tmp))
            runtime_input = dict(_experience_profile()["runtime_input"])
            runtime_input["creator_corpus"] = "invalid"
            runtime_input["user_question"] = "study"

            with self.assertRaisesRegex(
                ValueError,
                "grounded corpus requires unique non-empty sources",
            ):
                run_built_replica(run_dir, runtime_input)

    def test_generated_answer_must_cite_the_supplied_corpus(self):
        with TemporaryDirectory() as tmp:
            run_dir = _build_public_run(Path(tmp))
            runtime_input = dict(_experience_profile()["runtime_input"])
            runtime_input["creator_corpus"] = [
                {
                    "source_id": "different-source",
                    "text": "A study session starts with one focused task.",
                }
            ]
            runtime_input["user_question"] = "study"

            with self.assertRaisesRegex(
                ValueError,
                "grounded answer requires citations from the supplied corpus",
            ):
                run_built_replica(run_dir, runtime_input)

    def test_unrelated_aliases_do_not_create_a_grounded_answer(self):
        with TemporaryDirectory() as tmp:
            run_dir = _build_public_run(Path(tmp))
            runtime_input = dict(_experience_profile()["runtime_input"])
            runtime_input["creator_corpus"] = [
                {
                    "source_id": "src-public",
                    "text": (
                        "This case study says a startup begins layoffs."
                    ),
                }
            ]
            runtime_input["user_question"] = "How can I begin learning?"

            result = run_built_replica(run_dir, runtime_input)

            self.assertEqual("insufficient_information", result["status"])

    def test_other_unsupported_personal_facts_keep_the_fallback(self):
        with TemporaryDirectory() as tmp:
            run_dir = _build_public_run(Path(tmp))
            for question in (
                "What is the study author's phone number?",
                "What is the study author's email?",
                "How many children does the study author have?",
            ):
                with self.subTest(question=question):
                    runtime_input = dict(
                        _experience_profile()["runtime_input"]
                    )
                    runtime_input["user_question"] = question

                    result = run_built_replica(run_dir, runtime_input)

                    self.assertEqual(
                        "insufficient_information",
                        result["status"],
                    )

    def test_successful_finalize_publishes_the_public_experience_profile(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "second-pass.json"
            workspace = root / "workspace"
            vault = root / "vault"
            _write_json(source, _second_pass())
            prepared = prepare_codex_operator(source, workspace, vault)
            request = json.loads(
                Path(prepared["request_path"]).read_text(encoding="utf-8")
            )
            _write_json(Path(prepared["operator_path"]), _operator(request))

            result = finalize_codex_operator(
                Path(prepared["task_dir"]),
                workspace,
                vault,
            )

            experience_path = Path(result["run_dir"]) / "experience.json"
            self.assertTrue(experience_path.is_file())
            self.assertEqual(
                _experience_profile(),
                json.loads(experience_path.read_text(encoding="utf-8")),
            )
            replica_result = json.loads(
                (Path(result["run_dir"]) / "replica-result.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIn("experience.json", replica_result["artifacts"])

            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "experience",
                        result["run_dir"],
                        "--question",
                        "How should I start a study session?",
                    ]
                )

            self.assertEqual(0, exit_code)
            rendered = output.getvalue()
            self.assertIn("상태: answered", rendered)
            self.assertIn("답변: Start with one focused task.", rendered)
            self.assertIn(
                "A study session starts with one focused task.", rendered
            )

    def test_experience_evidence_level_must_match_the_second_pass_result(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "second-pass.json"
            second_pass = _second_pass()
            second_pass["experience"]["comparison"][
                "evidence_level"
            ] = "claim_only"
            _write_json(source, second_pass)

            with self.assertRaisesRegex(
                ValueError,
                "invalid second-pass result contract",
            ):
                prepare_codex_operator(
                    source,
                    root / "workspace",
                    root / "vault",
                )

    def test_experience_requires_the_grounded_conversation_output_format(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "second-pass.json"
            second_pass = _second_pass()
            second_pass["output_contract"]["format"] = "other-response"
            _write_json(source, second_pass)

            with self.assertRaisesRegex(
                ValueError,
                "invalid second-pass result contract",
            ):
                prepare_codex_operator(
                    source,
                    root / "workspace",
                    root / "vault",
                )

    def test_public_experience_must_not_copy_a_frozen_test_input(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "second-pass.json"
            second_pass = _second_pass()
            second_pass["experience"]["examples"][0]["question"] = "study"
            _write_json(source, second_pass)

            with self.assertRaisesRegex(
                ValueError,
                "invalid second-pass result contract",
            ):
                prepare_codex_operator(
                    source,
                    root / "workspace",
                    root / "vault",
                )

    def test_extra_public_fields_cannot_hide_a_frozen_test_input(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "second-pass.json"
            second_pass = _second_pass()
            second_pass["experience"]["examples"][0]["question"] = "study"
            second_pass["experience"]["runtime_input"]["unused"] = True
            _write_json(source, second_pass)

            with self.assertRaisesRegex(
                ValueError,
                "invalid second-pass result contract",
            ):
                prepare_codex_operator(
                    source,
                    root / "workspace",
                    root / "vault",
                )

    def test_original_output_cannot_copy_a_frozen_expected_output(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "second-pass.json"
            second_pass = _second_pass()
            second_pass["evidence_level"] = "direct"
            second_pass["experience"]["comparison"] = {
                "evidence_level": "direct",
                "summary": "Same-input original product comparison.",
                "original_outputs": [
                    {
                        "question": "How should I start a study session?",
                        "output": second_pass["tests"]["cases"][0][
                            "deterministic_assertions"
                        ][0]["value"],
                        "source": "Recorded original session 2026-08-11",
                    }
                ],
            }
            _write_json(source, second_pass)

            with self.assertRaisesRegex(
                ValueError,
                "invalid second-pass result contract",
            ):
                prepare_codex_operator(
                    source,
                    root / "workspace",
                    root / "vault",
                )


if __name__ == "__main__":
    unittest.main()
