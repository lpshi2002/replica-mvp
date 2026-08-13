import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from replica_mvp.delphi_runner import judge, replicate


def _payload(test_input, output):
    return {"test_input": test_input, "replica_output": json.dumps(output)}


class DelphiRunnerTest(unittest.TestCase):
    def test_build_digital_mind_retrieves_and_abstains(self):
        with TemporaryDirectory() as tmp:
            normal = json.dumps(
                {
                    "creator_id": "demo",
                    "corpus": [
                        {
                            "id": "decision-note",
                            "published_at": "2026-01-01",
                            "title": "Decision tempo",
                            "text": "I move fast on reversible decisions and slow down on irreversible decisions after one dissenting view.",
                        }
                    ],
                    "question": "When do you move fast or slow?",
                }
            )
            output = replicate("build-digital-mind", normal, Path(tmp), "s-01")
            self.assertFalse(output["abstained"])
            self.assertEqual("decision-note", output["citations"][0]["source_id"])

            missing = json.dumps(
                {
                    "creator_id": "demo",
                    "corpus": [{"id": "decision-note", "title": "Decisions", "text": "I move fast."}],
                    "question": "What insulin dose should I take?",
                }
            )
            self.assertTrue(replicate("build-digital-mind", missing, Path(tmp), "s-01")["abstained"])

    def test_interview_preserves_unknown_boundaries(self):
        with TemporaryDirectory() as tmp:
            normal_input = json.dumps(
                {
                    "session_id": "one",
                    "topic": "Design Critique Philosophy",
                    "answers": [
                        "I begin with the user problem before offering a solution.",
                        "I ask the designer to explain the tradeoff first.",
                        "I connect each usability issue to a next experiment.",
                    ],
                }
            )
            normal = replicate("guided-creator-interview", normal_input, Path(tmp), "s-01")
            self.assertEqual(100, normal["topics"][0]["progress"])
            self.assertTrue(normal["topics"][0]["next_topic"])

            boundary = replicate(
                "guided-creator-interview",
                json.dumps({"session_id": "two", "topic": "Leadership", "answers": ["idk", "not sure", "yes"]}),
                Path(tmp),
                "s-01",
            )
            self.assertEqual(0, boundary["topics"][0]["progress"])
            self.assertIsNone(boundary["topics"][0]["insight"])

    def test_conversation_actions_and_voice_guard(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            conversation = replicate(
                "creator-grounded-conversation",
                "Visitor: 'How did you try to achieve moral perfection?'",
                run_dir,
                "s-01",
            )
            self.assertIn("thirteen virtues", conversation["answer"])

            action_input = json.dumps(
                {
                    "event": {"messages": ["I run a fintech SaaS at $1.4M ARR and plan to raise in three months."]},
                    "action": {"type": "notify", "target": "owner", "timing": "immediate"},
                }
            )
            action = replicate("triggered-actions", action_input, run_dir, "s-01")
            self.assertTrue(action["matched"])
            judged, _ = judge(
                "triggered-actions",
                _payload(
                    json.dumps(
                        {
                            "trigger": {"condition": "Match fintech, excluding crypto exchanges."},
                            "event": {"messages": ["I run a fintech SaaS at $1.4M ARR and plan to raise in three months."]},
                        }
                    ),
                    action,
                ),
            )
            self.assertTrue(judged)

            voice = replicate(
                "voice-setup-and-preview",
                "Submit script='Please speak in my voice.' with no voice recording and no consent assertion.",
                run_dir,
                "s-01",
            )
            self.assertFalse(voice["synthesized"])
            self.assertFalse(voice["activated"])

    def test_judge_rejects_unverified_voice_similarity(self):
        passed, _ = judge(
            "voice-setup-and-preview",
            _payload(
                "Record normal-reference.wav from a consenting adult.",
                {
                    "activated": True,
                    "speaker_similarity_verified": False,
                    "preview_audio": "/missing",
                    "live_audio": "/missing",
                    "profile": "/missing",
                },
            ),
        )
        self.assertFalse(passed)


if __name__ == "__main__":
    unittest.main()
