from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

try:
    from config.structure import AgentState, add_message, record_event
except ModuleNotFoundError:  # Supports package execution from the parent folder.
    from ..config.structure import AgentState, add_message, record_event


class Write_Agent:
    def __init__(self, model: Optional[Any] = None):
        self.model = model

    def write(self, data: AgentState) -> AgentState:
        if not isinstance(data, AgentState):
            raise TypeError("Write_Agent.write 需要 AgentState")
        if not data.sub_task:
            raise ValueError("没有可撰写的子任务")
        if not data.evidence:
            raise ValueError("没有证据，不能生成报告")

        data.overall_steps += 1
        record_event(data, "agent_start", agent="WriteAgent")
        if self.model is not None:
            report = self._model_write(data)
        else:
            report = self._local_write(data)
        if not report.strip():
            raise RuntimeError("WriterAgent 返回了空报告")

        data.report = report.strip()
        data.coverage_rate = self.calculate(data)
        data.current_agent = "AuditAgent"
        data.status = "Running"
        data.retry_count = data.max_retries + 1
        record_event(
            data,
            "report_created",
            report_length=len(data.report),
            coverage_rate=data.coverage_rate,
        )
        add_message(
            data,
            sender="WriteAgent",
            receiver="AuditAgent",
            message_type="result",
            payload={
                "report": data.report,
                "coverage_rate": data.coverage_rate,
            },
            evidence=data.evidence,
        )
        return data

    def calculate(self, data: AgentState) -> float:
        """Return the fraction of sub-tasks represented with valid citations."""

        if not data.sub_task:
            return 0.0
        valid_source_ids = {
            str(item.get("source_id"))
            for item in data.evidence
            if item.get("source_id")
        }
        cited_tasks = set()
        for evidence in data.evidence:
            task_id = str(evidence.get("task_id") or "")
            source_id = str(evidence.get("source_id") or "")
            if task_id and source_id in valid_source_ids and f"[{source_id}]" in data.report:
                cited_tasks.add(task_id)
        return round(min(1.0, len(cited_tasks) / len(data.sub_task)), 4)

    def _local_write(self, data: AgentState) -> str:
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for evidence in data.evidence:
            grouped[str(evidence.get("task_id"))].append(evidence)

        topic = data.input_data.context if data.input_data else "调研主题"
        sections = [f"# {topic}调研报告", ""]
        sections.append("## 一、研究范围")
        sections.append(
            "本文围绕研究主题拆分为多个子任务，并根据本次运行检索到的公开资料整理结果。"
        )
        sections.append("")

        for index, sub_task in enumerate(data.sub_task, 1):
            task_id = f"subtask_{index:03d}"
            sections.append(f"## {index + 1}、{sub_task}")
            evidence_items = grouped.get(task_id, [])
            if not evidence_items:
                sections.append("本部分未检索到可用证据，暂不作事实性结论。")
            else:
                sections.append("根据检索证据，本部分可归纳为：")
                for item in evidence_items:
                    source_id = item.get("source_id", "unknown")
                    title = item.get("title", "未命名资料")
                    quote = str(item.get("quote", "")).replace("\n", " ").strip()
                    url = item.get("url") or "未提供链接"
                    sections.append(
                        f"- {quote} [{source_id}]（{title}，{url}）"
                    )
            sections.append("")

        sections.append("## 结论")
        sections.append(
            "本报告的结论仅基于列出的检索证据，审核阶段将继续检查子任务覆盖情况和引用有效性。"
        )
        return "\n".join(sections)

    def _model_write(self, data: AgentState) -> str:
        topic = data.input_data.context if data.input_data else "调研主题"
        evidence_text = "\n".join(
            f"[{item.get('source_id')}] {item.get('title')}: {item.get('quote')}"
            for item in data.evidence
        )
        prompt = (
            "请根据主题、子任务和证据撰写中文调研报告。每个事实性结论必须引用对应的"
            "[source_id]，不要编造资料中没有的信息。\n"
            f"主题：{topic}\n子任务：{data.sub_task}\n证据：\n{evidence_text}"
        )
        response = self.model.generate(prompt)
        return response if isinstance(response, str) else ""
