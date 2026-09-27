import re
import unittest
from unittest.mock import patch

import main
from agents.plan_agent import Plan_Agent
from agents.retrieve_agent import Retrieve_Agent
from agents.write_agent import Write_Agent
from config.structure import ContextInput


SOURCE_ID = "wiki_generative_ai"
SOURCE_URL = "https://zh.wikipedia.org/wiki/%E7%94%9F%E6%88%90%E5%BC%8F%E4%BA%BA%E5%B7%A5%E6% 智慧"


def build_state():
    data = ContextInput(
        context="生成式人工智能的技术基础、应用与风险",
        source_id=SOURCE_ID,
        url="https://zh.wikipedia.org/wiki/%E7%94%9F%E6%88%90%E5%BC%8F%E4%BA%BA%E5%B7%A5%E6%99%BA%E6%85%A7",
        source_ids=[SOURCE_ID],
    )
    state = Plan_Agent().Planning(data)
    return Retrieve_Agent().retrieve(state)


class FakeModel:
    def __init__(self):
        self.calls = []
        self.last_generation_hit_limit = False

    def generate(self, prompt):
        self.calls.append(prompt)
        self.last_generation_hit_limit = False
        match = re.search(r"子任务：(.+?)\n\n", prompt)
        task = match.group(1) if match else "当前子任务"
        return f"围绕“{task}”的证据分析。"


class OneTruncatedSectionModel(FakeModel):
    def generate(self, prompt):
        self.calls.append(prompt)
        self.last_generation_hit_limit = len(self.calls) == 2
        match = re.search(r"子任务：(.+?)\n\n", prompt)
        task = match.group(1) if match else "当前子任务"
        return "未完成的正文" if self.last_generation_hit_limit else f"完成“{task}”的证据分析。"


class PipelineRetryModel(FakeModel):
    def generate(self, prompt):
        self.calls.append(prompt)
        self.last_generation_hit_limit = len(self.calls) == 3
        if "规划 Agent" in prompt:
            return '{"sub_tasks":["任务A","任务B","任务C"]}'
        if "单 Agent 基线系统" in prompt:
            self.last_generation_hit_limit = False
            return "基线正文"
        match = re.search(r"子任务：(.+?)\n\n", prompt)
        task = match.group(1) if match else "当前子任务"
        return f"完成“{task}”的证据分析。"


class ModelWriteTests(unittest.TestCase):
    def test_sections_are_generated_independently_and_citations_are_assembled(self):
        state = build_state()
        model = FakeModel()
        writer = Write_Agent(model=model)

        writer.write(state)
        report = writer._latest_report(state)

        self.assertEqual(len(model.calls), len(state.sub_task))
        self.assertEqual(writer.calculate(state), 1.0)
        for sub_task in state.sub_task:
            section = writer._task_section(report, sub_task, state.sub_task)
            self.assertIn(f"[{SOURCE_ID}]", section)
        self.assertNotIn("引用必须写成", report)

    def test_retry_reuses_completed_sections_and_includes_failure_feedback(self):
        state = build_state()
        model = OneTruncatedSectionModel()
        writer = Write_Agent(model=model)

        with self.assertRaises(ValueError):
            writer.write(state)

        self.assertEqual(len(state.draft_sections), 1)
        state.last_error = "WriteAgent: 子任务输出达到 max_new_tokens，疑似被截断"
        writer.write(state)

        self.assertEqual(len(model.calls), 4)
        self.assertIn("上一次生成失败", model.calls[2])
        self.assertEqual(writer.calculate(state), 1.0)

    def test_pipeline_retry_repairs_only_the_failed_model_section(self):
        model = PipelineRetryModel()
        with patch.object(main, "load_model_from_environment", return_value=model):
            result = main.run_pipeline("data/normal_input.json")

        self.assertNotIn("任务未正常完成", result.final_report)
        self.assertEqual(result.total_retries, 1)
        self.assertEqual(result.coverage_rate, 1.0)
        self.assertEqual(result.baseline_comparison["status"], "Completed")
        self.assertEqual(len(model.calls), 6)
        self.assertIn("上一次生成失败", model.calls[3])


if __name__ == "__main__":
    unittest.main()
