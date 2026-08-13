import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from replica_mvp import build_project, evaluate_project, init_project


class ReplicaProjectTest(unittest.TestCase):
    def test_five_stage_project_runs_end_to_end(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "demo"
            init_project(
                root,
                name="demo",
                company="Public Risk AI",
                url="https://example.com",
                capability="공개 수치에서 위험 신호를 설명한다",
                evidence_level="public",
            )
            evidence = json.loads((root / "evidence.json").read_text(encoding="utf-8"))
            evidence["sources"][0]["excerpt"] = "공개 수치와 함께 위험 신호를 설명한다."
            (root / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
            spec = json.loads((root / "spec.json").read_text(encoding="utf-8"))
            spec["input_description"] = "수치가 포함된 한 문장"
            spec["output_description"] = "위험 신호와 근거 수치"
            spec["acceptance_criteria"] = ["입력 수치를 인용한다", "위험 여부를 설명한다"]
            (root / "spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            tests = json.loads((root / "tests.json").read_text(encoding="utf-8"))
            for index, case in enumerate(tests, start=1):
                case["input"] = f"부채비율 {index * 100}%"
                case["expected_behavior"] = "입력 수치를 근거로 위험을 설명한다"
            (root / "tests.json").write_text(json.dumps(tests, ensure_ascii=False), encoding="utf-8")

            replica_script = Path(tmp) / "replica.py"
            replica_script.write_text(
                "import sys\nprint('위험 신호: ' + sys.stdin.read().split('USER INPUT:')[-1].strip())\n",
                encoding="utf-8",
            )
            judge_script = Path(tmp) / "judge.py"
            judge_script.write_text(
                "import json\nprint(json.dumps({'pass': True, 'reason': '수치와 위험 설명을 포함함'}, ensure_ascii=False))\n",
                encoding="utf-8",
            )

            build_project(root)
            results = evaluate_project(
                root,
                replica_command=f"{sys.executable} {replica_script}",
                judge_command=f"{sys.executable} {judge_script}",
            )

            self.assertEqual(3, len(results))
            self.assertTrue(all(result["pass"] for result in results))
            outputs = (root / "replica_outputs.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(3, len(outputs))
            report = (root / "report.md").read_text(encoding="utf-8")
            self.assertIn("3/3 통과", report)
            self.assertIn("## 검토한 공개 주장", report)
            self.assertIn("## 평가 방법", report)
            self.assertIn("## 사례별 상세 결과", report)
            self.assertIn("부채비율 100%", report)
