import json
import tempfile
import time
import unittest
from pathlib import Path

try:
    from main import run_pipeline
except ModuleNotFoundError:
    from openpangu_qa.main import run_pipeline


class PipelineTestCase(unittest.TestCase):
    def setUp(self):
        self.sources = [
            {
                "source_id": "source_001",
                "title": "人工智能教育应用",
                "url": "https://example.test/education",
                "quote": "人工智能支持个性化学习和智能辅导。",
            },
            {
                "source_id": "source_002",
                "title": "人工智能风险",
                "url": "https://example.test/risk",
                "quote": "人工智能应用需要关注隐私保护和数据安全。",
            },
        ]

    def test_normal_pipeline(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_pipeline(
                {
                    "context": "人工智能在教育中的应用",
                    "sources": self.sources,
                    "log_path": str(Path(directory) / "normal.jsonl"),
                }
            )

            self.assertEqual(result.status, "Completed")
            self.assertEqual(result.overall_steps, 4)
            self.assertEqual(result.total_retries, 0)
            self.assertEqual(result.task_completion_rate, 1.0)
            self.assertEqual(result.coverage_rate, 1.0)
            self.assertTrue(result.audit_result["passed"])
            self.assertEqual(len(result.messages), 4)
            self._assert_jsonl(result.log_path)

    def test_retrieval_failure_retries_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_pipeline(
                {
                    "context": "人工智能在教育中的应用",
                    "sources": self.sources,
                    "force_retrieval_failure": True,
                    "log_path": str(Path(directory) / "failure.jsonl"),
                }
            )

            self.assertEqual(result.status, "Error")
            self.assertEqual(result.total_retries, 2)
            self.assertEqual(result.overall_steps, 4)
            self.assertEqual(result.task_completion_rate, 0.0)
            self.assertEqual(result.coverage_rate, 0.0)
            records = self._assert_jsonl(result.log_path)
            retrieve_starts = [
                item
                for item in records
                if item.get("event") == "agent_attempt"
                and item.get("agent") == "RetrieveAgent"
            ]
            self.assertEqual(len(retrieve_starts), 3)

    def test_agent_timeout_retries_twice(self):
        class SlowModel:
            def generate(self, prompt, **kwargs):
                time.sleep(0.05)
                return '{"sub_tasks":["背景", "方法", "风险"]}'

        with tempfile.TemporaryDirectory() as directory:
            result = run_pipeline(
                {
                    "context": "超时测试",
                    "sources": [{"source_id": "s1", "quote": "超时测试资料"}],
                    "timeout_seconds": 0.01,
                    "log_path": str(Path(directory) / "timeout.jsonl"),
                },
                model=SlowModel(),
            )

            self.assertEqual(result.status, "Error")
            self.assertEqual(result.total_retries, 2)
            self.assertEqual(result.overall_steps, 3)
            self.assertIn("超过 0.01 秒未完成", result.final_report)
            self._assert_jsonl(result.log_path)

    def _assert_jsonl(self, path):
        records = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
        ]
        self.assertTrue(records)
        return records


if __name__ == "__main__":
    unittest.main()
