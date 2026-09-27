import json
import unittest
from pathlib import Path

from main import run_pipeline
from config.structure import ContextInput
from utils.data_loader import loader
from utils.source_store import SourceDataError, load_manifest, load_sources


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


class DataPipelineTests(unittest.TestCase):
    def test_manifest_and_snapshots_are_complete_and_consistent(self):
        manifest = load_manifest(DATA_DIR)
        self.assertEqual(manifest["schema_version"], 2)
        self.assertNotIn("context_limit_characters", manifest)

        records = load_sources(
            [entry["source_id"] for entry in manifest["sources"]],
            DATA_DIR,
        )
        self.assertEqual(len(records), 5)
        for entry in manifest["sources"]:
            record = records[entry["source_id"]]
            self.assertFalse(entry["truncated"])
            self.assertEqual(entry["original_characters"], entry["stored_characters"])
            self.assertEqual(entry["stored_characters"], len(record.context))
            self.assertEqual(entry["content_sha256"], record.content_sha256)
            self.assertGreater(len(record.context), 3000)

    def test_normal_input_contains_topic_and_source_selection_only(self):
        payload = json.loads(
            (DATA_DIR / "normal_input.json").read_text(encoding="utf-8")
        )
        manifest = load_manifest(DATA_DIR)
        self.assertEqual(payload["context"], manifest["topic"])
        self.assertEqual(len(payload["source_ids"]), 5)
        self.assertLess(len(payload["context"]), 200)
        self.assertNotIn("context_limit_characters", payload)
        self.assertEqual(loader(payload).source_ids, payload["source_ids"])

    def test_retrieval_fails_for_unknown_source(self):
        payload = json.loads(
            (DATA_DIR / "retrieval_failure.json").read_text(encoding="utf-8")
        )
        with self.assertRaises(SourceDataError):
            load_sources(payload["source_ids"], DATA_DIR)

        result = run_pipeline(DATA_DIR / "retrieval_failure.json")
        self.assertEqual(result.total_retries, 2)
        self.assertEqual(result.coverage_rate, 0.0)
        self.assertIn("wiki_missing_source", result.final_report)

    def test_normal_pipeline_uses_verified_sources(self):
        result = run_pipeline(DATA_DIR / "normal_input.json")
        self.assertNotIn("任务未正常完成", result.final_report)
        self.assertEqual(result.coverage_rate, 1.0)
        self.assertIn("wiki_generative_ai", result.final_report)
        self.assertIn("wiki_ai_regulation", result.final_report)

    def test_legacy_context_input_falls_back_to_primary_source(self):
        result = run_pipeline(
            ContextInput(
                context="生成式人工智能的技术基础、应用与风险",
                source_id="wiki_generative_ai",
                url="https://zh.wikipedia.org/wiki/%E7%94%9F%E6%88%90%E5%BC%8F%E4%BA%BA%E5%B7%A5%E6%99%BA%E6%85%A7",
            )
        )
        self.assertEqual(result.coverage_rate, 1.0)
        self.assertNotIn("任务未正常完成", result.final_report)


if __name__ == "__main__":
    unittest.main()
