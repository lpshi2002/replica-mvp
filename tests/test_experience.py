import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from replica_mvp.cli import main


def _profile() -> dict:
    return {
        "schema_version": "replica-experience/v1",
        "title": "Grounded digital mind",
        "description": "Ask questions against a supplied creator corpus.",
        "interaction": {
            "type": "question_answer",
            "question_field": "user_question",
        },
        "runtime_input": {
            "creator_corpus": [
                {
                    "source_id": "src-1",
                    "text": "Mira recommends one 25-minute task.",
                }
            ],
            "style_rules": ["Use a warm, concise tone."],
            "safety_rules": ["Never invent personal facts."],
            "fallback_text": "Not enough source information.",
            "conversation_history": [],
        },
        "examples": [],
        "comparison": {
            "evidence_level": "public",
            "summary": "Compared with the publicly documented capability.",
            "original_outputs": [],
        },
    }


def _write_replica_spec(root: Path, evidence_level: str = "public") -> Path:
    run_dir = root / "run"
    run_dir.mkdir(exist_ok=True)
    (run_dir / "replica-spec.json").write_text(
        json.dumps({"evidence_policy": {"level": evidence_level}}),
        encoding="utf-8",
    )
    return run_dir


def _original_observations() -> dict:
    return {
        "schema_version": "replica-original-observations/v1",
        "original_name": "Delphi",
        "observations": [
            {
                "question": "How should I start studying?",
                "output": "Choose one concrete task and begin there.",
                "source": "Recorded Delphi session delphi-session-001",
                "captured_at": "2026-08-11T12:00:00+09:00",
            }
        ],
    }


class ExperienceCliTest(unittest.TestCase):
    def test_question_experience_enables_the_model_adapter_only_by_flag(self):
        with (
            TemporaryDirectory() as tmp,
            patch(
                "replica_mvp.cli.experience_once",
                return_value="rendered",
            ) as experience,
            redirect_stdout(StringIO()),
        ):
            run_dir = Path(tmp) / "run"
            exit_code = main(
                [
                    "experience",
                    str(run_dir),
                    "--question",
                    "What should I do?",
                    "--use-model-adapter",
                ]
            )

        self.assertEqual(0, exit_code)
        experience.assert_called_once_with(
            run_dir,
            run_dir / "experience.json",
            "What should I do?",
            None,
            use_model_adapter=True,
        )

    def test_interactive_bundle_turns_share_one_state_directory(self):
        with (
            TemporaryDirectory() as tmp,
            patch("replica_mvp.cli.is_bundle_run", return_value=True),
            patch("replica_mvp.cli.experience_once", return_value="rendered") as experience,
            patch("builtins.input", side_effect=["first", "follow-up", EOFError]),
            redirect_stdout(StringIO()),
        ):
            self.assertEqual(0, main(["experience", str(Path(tmp) / "run")]))

        states = [call.kwargs["state_dir"] for call in experience.call_args_list]
        self.assertEqual(2, len(states))
        self.assertEqual(states[0], states[1])

    def test_text_replica_can_be_read_from_a_json_input_file(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = _write_replica_spec(root)
            (run_dir / "replica-spec.json").write_text(
                json.dumps(
                    {
                        "evidence_policy": {"level": "public"},
                        "output_contract": {
                            "type": "string",
                            "format": "text/plain",
                        },
                    }
                ),
                encoding="utf-8",
            )
            input_path = root / "document-request.json"
            input_value = {"topic": "MVP launch"}
            input_path.write_text(json.dumps(input_value), encoding="utf-8")
            output = StringIO()
            with (
                patch(
                    "replica_mvp.experience.run_built_replica",
                    return_value="Generated document body.",
                ) as execute,
                redirect_stdout(output),
            ):
                exit_code = main(
                    [
                        "experience",
                        str(run_dir),
                        "--input",
                        str(input_path),
                    ]
                )

        rendered = output.getvalue()
        self.assertEqual(0, exit_code)
        execute.assert_called_once_with(run_dir, input_value)
        self.assertIn("출력 형식: text/plain", rendered)
        self.assertIn("Generated document body.", rendered)

    def test_html_replica_writes_an_explicit_new_preview_file(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = _write_replica_spec(root)
            (run_dir / "replica-spec.json").write_text(
                json.dumps(
                    {
                        "evidence_policy": {"level": "public"},
                        "output_contract": {
                            "type": "string",
                            "format": "text/html",
                        },
                    }
                ),
                encoding="utf-8",
            )
            input_path = root / "site-request.json"
            input_value = {"headline": "Visible Replica"}
            input_path.write_text(json.dumps(input_value), encoding="utf-8")
            preview_path = root / "preview.html"
            html = "<!doctype html><h1>Visible Replica</h1>"
            output = StringIO()
            with (
                patch(
                    "replica_mvp.experience.run_built_replica",
                    return_value=html,
                ) as execute,
                redirect_stdout(output),
            ):
                exit_code = main(
                    [
                        "experience",
                        str(run_dir),
                        "--input",
                        str(input_path),
                        "--output",
                        str(preview_path),
                    ]
                )

            rendered = output.getvalue()
            self.assertEqual(0, exit_code)
            execute.assert_called_once_with(run_dir, input_value)
            self.assertEqual(html, preview_path.read_text(encoding="utf-8"))
            self.assertIn("출력 형식: text/html", rendered)
            self.assertIn(str(preview_path.resolve()), rendered)

            error = StringIO()
            with (
                patch(
                    "replica_mvp.experience.run_built_replica",
                    return_value="replacement",
                ),
                redirect_stderr(error),
            ):
                second_exit_code = main(
                    [
                        "experience",
                        str(run_dir),
                        "--input",
                        str(input_path),
                        "--output",
                        str(preview_path),
                    ]
                )

            self.assertEqual(2, second_exit_code)
            self.assertEqual(html, preview_path.read_text(encoding="utf-8"))
            self.assertIn("experience output already exists", error.getvalue())

    def test_html_preview_cannot_be_written_inside_the_published_run(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = _write_replica_spec(root)
            (run_dir / "replica-spec.json").write_text(
                json.dumps(
                    {
                        "evidence_policy": {"level": "public"},
                        "output_contract": {
                            "type": "string",
                            "format": "text/html",
                        },
                    }
                ),
                encoding="utf-8",
            )
            input_path = root / "site-request.json"
            input_path.write_text(json.dumps({"headline": "Demo"}), encoding="utf-8")
            preview_path = run_dir / "preview.html"
            error = StringIO()
            with (
                patch(
                    "replica_mvp.experience.run_built_replica",
                    return_value="<h1>Demo</h1>",
                ),
                redirect_stderr(error),
            ):
                exit_code = main(
                    [
                        "experience",
                        str(run_dir),
                        "--input",
                        str(input_path),
                        "--output",
                        str(preview_path),
                    ]
                )

        self.assertEqual(2, exit_code)
        self.assertFalse(preview_path.exists())
        self.assertIn("outside the published run", error.getvalue())

    def test_structured_replica_can_be_experienced_from_a_json_input_file(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = _write_replica_spec(root)
            (run_dir / "replica-spec.json").write_text(
                json.dumps(
                    {
                        "evidence_policy": {"level": "public"},
                        "output_contract": {
                            "type": "object",
                            "format": "lead-qualification",
                        },
                    }
                ),
                encoding="utf-8",
            )
            input_path = root / "lead.json"
            input_value = {
                "company_size": 120,
                "budget_confirmed": True,
            }
            input_path.write_text(json.dumps(input_value), encoding="utf-8")
            output = StringIO()
            with (
                patch(
                    "replica_mvp.experience.run_built_replica",
                    return_value={
                        "classification": "qualified",
                        "score": 82,
                    },
                ) as execute,
                redirect_stdout(output),
            ):
                exit_code = main(
                    [
                        "experience",
                        str(run_dir),
                        "--input",
                        str(input_path),
                    ]
                )

        rendered = output.getvalue()
        self.assertEqual(0, exit_code)
        execute.assert_called_once_with(run_dir, input_value)
        self.assertIn("출력 형식: lead-qualification", rendered)
        self.assertIn('"classification": "qualified"', rendered)
        self.assertIn('"score": 82', rendered)

    def test_public_replica_can_show_a_same_question_original_observation(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = _write_replica_spec(root)
            profile_path = root / "experience.json"
            profile_path.write_text(
                json.dumps(_profile(), ensure_ascii=False),
                encoding="utf-8",
            )
            observations_path = root / "original-observations.json"
            observations_path.write_text(
                json.dumps(_original_observations(), ensure_ascii=False),
                encoding="utf-8",
            )
            output = StringIO()
            with (
                patch(
                    "replica_mvp.experience.run_built_replica",
                    return_value={
                        "status": "answered",
                        "answer": "Start with one 25-minute task.",
                        "citations": ["src-1"],
                        "applied_rules": ["Use a warm, concise tone."],
                    },
                ),
                redirect_stdout(output),
            ):
                exit_code = main(
                    [
                        "experience",
                        str(run_dir),
                        "--profile",
                        str(profile_path),
                        "--question",
                        "How should I start studying?",
                        "--original-observations",
                        str(observations_path),
                    ]
                )

        rendered = output.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("근거 수준: public", rendered)
        self.assertIn("원본 직접 비교: 가능 (사용자 제공 관찰)", rendered)
        self.assertIn("원본 이름: Delphi", rendered)
        self.assertIn(
            "원본 출력: Choose one concrete task and begin there.",
            rendered,
        )
        self.assertIn(
            "원본 근거: Recorded Delphi session delphi-session-001",
            rendered,
        )

    def test_original_observation_must_match_the_exact_experience_question(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = _write_replica_spec(root)
            profile_path = root / "experience.json"
            profile_path.write_text(
                json.dumps(_profile(), ensure_ascii=False),
                encoding="utf-8",
            )
            observations_path = root / "original-observations.json"
            observations_path.write_text(
                json.dumps(_original_observations(), ensure_ascii=False),
                encoding="utf-8",
            )
            error = StringIO()
            with redirect_stderr(error):
                exit_code = main(
                    [
                        "experience",
                        str(run_dir),
                        "--profile",
                        str(profile_path),
                        "--question",
                        "What should I study?",
                        "--original-observations",
                        str(observations_path),
                    ]
                )

        self.assertEqual(2, exit_code)
        self.assertIn(
            "original observations have no output for this question",
            error.getvalue(),
        )

    def test_original_observation_requires_a_timezone_aware_timestamp(self):
        for captured_at in ("2026-08-11", "2026-08-11T12:00:00"):
            with self.subTest(captured_at=captured_at), TemporaryDirectory() as tmp:
                root = Path(tmp)
                run_dir = _write_replica_spec(root)
                profile_path = root / "experience.json"
                profile_path.write_text(
                    json.dumps(_profile(), ensure_ascii=False),
                    encoding="utf-8",
                )
                observations = _original_observations()
                observations["observations"][0]["captured_at"] = captured_at
                observations_path = root / "original-observations.json"
                observations_path.write_text(
                    json.dumps(observations, ensure_ascii=False),
                    encoding="utf-8",
                )
                error = StringIO()
                with redirect_stderr(error):
                    exit_code = main(
                        [
                            "experience",
                            str(run_dir),
                            "--profile",
                            str(profile_path),
                            "--question",
                            "How should I start studying?",
                            "--original-observations",
                            str(observations_path),
                        ]
                    )

                self.assertEqual(2, exit_code)
                self.assertIn("invalid original observations", error.getvalue())

    def test_run_uses_its_published_experience_profile_by_default(self):
        with TemporaryDirectory() as tmp:
            run_dir = _write_replica_spec(Path(tmp))
            (run_dir / "experience.json").write_text(
                json.dumps(_profile(), ensure_ascii=False),
                encoding="utf-8",
            )
            output = StringIO()
            with (
                patch(
                    "replica_mvp.experience.run_built_replica",
                    return_value={
                        "status": "answered",
                        "answer": "Start with one 25-minute task.",
                        "citations": ["src-1"],
                        "applied_rules": ["Use a warm, concise tone."],
                    },
                ) as execute,
                redirect_stdout(output),
            ):
                exit_code = main(
                    [
                        "experience",
                        str(run_dir),
                        "--question",
                        "How should I start studying?",
                    ]
                )

        self.assertEqual(0, exit_code)
        execute.assert_called_once()
        self.assertIn("답변: Start with one 25-minute task.", output.getvalue())

    def test_user_can_ask_one_question_and_read_the_replica_answer(self):
        with TemporaryDirectory() as tmp:
            run_dir = _write_replica_spec(Path(tmp))
            profile_path = Path(tmp) / "experience.json"
            profile_path.write_text(
                json.dumps(_profile(), ensure_ascii=False),
                encoding="utf-8",
            )
            output = StringIO()
            with (
                patch(
                    "replica_mvp.experience.run_built_replica",
                    return_value={
                        "status": "answered",
                        "answer": "Start with one 25-minute task.",
                        "citations": ["src-1"],
                        "applied_rules": ["Use a warm, concise tone."],
                    },
                ) as execute,
                redirect_stdout(output),
            ):
                exit_code = main(
                    [
                        "experience",
                        str(run_dir),
                        "--profile",
                        str(profile_path),
                        "--question",
                        "How should I start studying?",
                    ]
                )

        self.assertEqual(0, exit_code)
        execute.assert_called_once()
        self.assertEqual(
            "How should I start studying?",
            execute.call_args.args[1]["user_question"],
        )
        self.assertIn("Replica 체험: Grounded digital mind", output.getvalue())
        self.assertIn("질문: How should I start studying?", output.getvalue())
        self.assertIn("답변: Start with one 25-minute task.", output.getvalue())

    def test_result_shows_sources_rules_and_public_comparison_scope(self):
        with TemporaryDirectory() as tmp:
            run_dir = _write_replica_spec(Path(tmp))
            profile_path = Path(tmp) / "experience.json"
            profile_path.write_text(
                json.dumps(_profile(), ensure_ascii=False),
                encoding="utf-8",
            )
            output = StringIO()
            with (
                patch(
                    "replica_mvp.experience.run_built_replica",
                    return_value={
                        "status": "answered",
                        "answer": "Start with one 25-minute task.",
                        "citations": ["src-1"],
                        "applied_rules": ["Use a warm, concise tone."],
                    },
                ),
                redirect_stdout(output),
            ):
                exit_code = main(
                    [
                        "experience",
                        str(run_dir),
                        "--profile",
                        str(profile_path),
                        "--question",
                        "How should I start studying?",
                    ]
                )

        rendered = output.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("상태: answered", rendered)
        self.assertIn("근거 수준: public", rendered)
        self.assertIn("원본 직접 비교: 불가", rendered)
        self.assertIn(
            "비교 기준: Compared with the publicly documented capability.",
            rendered,
        )
        self.assertIn("- src-1: Mira recommends one 25-minute task.", rendered)
        self.assertIn("- Use a warm, concise tone.", rendered)

    def test_user_can_ask_questions_interactively_until_quit(self):
        with TemporaryDirectory() as tmp:
            run_dir = _write_replica_spec(Path(tmp))
            profile_path = Path(tmp) / "experience.json"
            profile_path.write_text(
                json.dumps(_profile(), ensure_ascii=False),
                encoding="utf-8",
            )
            output = StringIO()
            with (
                patch(
                    "replica_mvp.experience.run_built_replica",
                    return_value={
                        "status": "insufficient_information",
                        "answer": "Not enough source information.",
                        "citations": [],
                        "applied_rules": ["Never invent personal facts."],
                    },
                ) as execute,
                patch.object(
                    sys,
                    "stdin",
                    StringIO("What is Mira's favorite planet?\n/quit\n"),
                ),
                redirect_stdout(output),
            ):
                exit_code = main(
                    [
                        "experience",
                        str(run_dir),
                        "--profile",
                        str(profile_path),
                    ]
                )

        self.assertEqual(0, exit_code)
        execute.assert_called_once()
        self.assertEqual(
            "What is Mira's favorite planet?",
            execute.call_args.args[1]["user_question"],
        )
        self.assertIn("질문> ", output.getvalue())
        self.assertIn("상태: insufficient_information", output.getvalue())

    def test_direct_baseline_output_is_shown_for_the_same_question(self):
        profile = _profile()
        profile["comparison"] = {
            "evidence_level": "direct",
            "summary": "Same-input original product comparison.",
            "original_outputs": [
                {
                    "question": "How should I start studying?",
                    "output": "Choose a focused study task.",
                    "source": "Recorded original session 2026-08-11",
                }
            ],
        }
        with TemporaryDirectory() as tmp:
            run_dir = _write_replica_spec(Path(tmp), "direct")
            profile_path = Path(tmp) / "experience.json"
            profile_path.write_text(
                json.dumps(profile, ensure_ascii=False),
                encoding="utf-8",
            )
            output = StringIO()
            with (
                patch(
                    "replica_mvp.experience.run_built_replica",
                    return_value={
                        "status": "answered",
                        "answer": "Start with one 25-minute task.",
                        "citations": ["src-1"],
                        "applied_rules": ["Use a warm, concise tone."],
                    },
                ),
                redirect_stdout(output),
            ):
                exit_code = main(
                    [
                        "experience",
                        str(run_dir),
                        "--profile",
                        str(profile_path),
                        "--question",
                        "How should I start studying?",
                    ]
                )

        rendered = output.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("원본 직접 비교: 가능", rendered)
        self.assertIn("원본 출력: Choose a focused study task.", rendered)
        self.assertIn(
            "원본 근거: Recorded original session 2026-08-11",
            rendered,
        )

    def test_direct_comparison_without_original_output_is_rejected(self):
        profile = _profile()
        profile["comparison"] = {
            "evidence_level": "direct",
            "summary": "Same-input original product comparison.",
            "original_outputs": [],
        }
        with TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "experience.json"
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            error = StringIO()
            with redirect_stderr(error):
                exit_code = main(
                    [
                        "experience",
                        str(Path(tmp) / "run"),
                        "--profile",
                        str(profile_path),
                        "--question",
                        "How should I start studying?",
                    ]
                )

        self.assertEqual(2, exit_code)
        self.assertIn(
            "error: direct experience comparison requires original output",
            error.getvalue(),
        )

    def test_profile_evidence_must_match_the_built_replica(self):
        profile = _profile()
        profile["comparison"] = {
            "evidence_level": "direct",
            "summary": "Same-input original product comparison.",
            "original_outputs": [
                {
                    "question": "How should I start studying?",
                    "output": "Choose a focused study task.",
                    "source": "Recorded original session 2026-08-11",
                }
            ],
        }
        with TemporaryDirectory() as tmp:
            run_dir = _write_replica_spec(Path(tmp), "public")
            profile_path = Path(tmp) / "experience.json"
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            error = StringIO()
            with redirect_stderr(error):
                exit_code = main(
                    [
                        "experience",
                        str(run_dir),
                        "--profile",
                        str(profile_path),
                        "--question",
                        "How should I start studying?",
                    ]
                )

        self.assertEqual(2, exit_code)
        self.assertIn(
            "error: experience evidence level does not match built Replica",
            error.getvalue(),
        )

    def test_public_comparison_cannot_claim_original_outputs(self):
        profile = _profile()
        profile["comparison"]["original_outputs"] = [
            {
                "question": "How should I start studying?",
                "output": "An alleged original answer.",
                "source": "Unknown capture",
            }
        ]
        with TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "experience.json"
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            error = StringIO()
            with redirect_stderr(error):
                exit_code = main(
                    [
                        "experience",
                        str(Path(tmp) / "run"),
                        "--profile",
                        str(profile_path),
                        "--question",
                        "How should I start studying?",
                    ]
                )

        self.assertEqual(2, exit_code)
        self.assertIn(
            "error: original outputs require direct evidence",
            error.getvalue(),
        )

    def test_direct_comparison_rejects_a_question_without_original_output(self):
        profile = _profile()
        profile["comparison"] = {
            "evidence_level": "direct",
            "summary": "Same-input original product comparison.",
            "original_outputs": [
                {
                    "question": "How should I start studying?",
                    "output": "Choose a focused study task.",
                    "source": "Recorded original session 2026-08-11",
                }
            ],
        }
        with TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "experience.json"
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            error = StringIO()
            with redirect_stderr(error):
                exit_code = main(
                    [
                        "experience",
                        str(Path(tmp) / "run"),
                        "--profile",
                        str(profile_path),
                        "--question",
                        "What is Mira's favorite planet?",
                    ]
                )

        self.assertEqual(2, exit_code)
        self.assertIn(
            "error: direct comparison has no original output for this question",
            error.getvalue(),
        )

    def test_unknown_citation_is_rejected_instead_of_shown_without_source(self):
        with TemporaryDirectory() as tmp:
            run_dir = _write_replica_spec(Path(tmp))
            profile_path = Path(tmp) / "experience.json"
            profile_path.write_text(json.dumps(_profile()), encoding="utf-8")
            error = StringIO()
            with (
                patch(
                    "replica_mvp.experience.run_built_replica",
                    return_value={
                        "status": "answered",
                        "answer": "An unsupported answer.",
                        "citations": ["src-missing"],
                        "applied_rules": [],
                    },
                ),
                redirect_stderr(error),
            ):
                exit_code = main(
                    [
                        "experience",
                        str(run_dir),
                        "--profile",
                        str(profile_path),
                        "--question",
                        "How should I start studying?",
                    ]
                )

        self.assertEqual(2, exit_code)
        self.assertIn(
            "error: Replica returned an unknown citation: src-missing",
            error.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
