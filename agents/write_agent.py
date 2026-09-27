import json
import re
from typing import Any, Optional
from urllib.parse import unquote, urlparse

try:
    from config.structure import AgentState
except ModuleNotFoundError:
    from ..config.structure import AgentState


class Write_Agent:
    """根据证据撰写报告，并在模型模式下校验报告结构。"""

    def __init__(self, model: Optional[Any] = None):
        """创建撰写 Agent；未传模型时使用本地确定性报告。"""

        self.model = model

    def write(self, data: AgentState) -> AgentState:
        """生成报告；模型报告不满足子任务和引用要求时直接失败。"""

        if not isinstance(data, AgentState):
            raise TypeError("write 需要 AgentState")
        if not data.sub_task:
            raise ValueError("没有可撰写的子任务")
        if not data.evidence:
            raise ValueError("没有证据，不能生成报告")

        data.overall_steps += 1
        input_record = self._input_record(data) or {}
        topic = self._topic(input_record)
        if self.model is not None:
            report = self._model_write(data, topic)
            data.log.append(
                json.dumps(
                    {"type": "model_report", "content": report[:6000]},
                    ensure_ascii=False,
                )
            )
            self._validate_model_report(report, data)
        else:
            report = self._local_write(data, input_record, topic)

        data.log.append(
            json.dumps({"type": "report", "content": report}, ensure_ascii=False)
        )
        data.log.append(f"WriteAgent: 报告已生成，长度 {len(report)}")
        data.current_agent = "AuditAgent"
        data.retry_count = 2
        return data

    def _model_write(self, data: AgentState, topic: str) -> str:
        """调用盘古模型生成按子任务分节且带逐节引用的报告。"""

        prompt = (
            "你是一个严谨的调研报告撰写 Agent。请只依据给出的证据生成中文报告，"
            "不要逐字复制整段来源，不得补充证据中没有的事实。必须覆盖每个子任务。"
            "请严格保留每个子任务的原文作为小节标题，并在对应小节内使用"
            "[source_id] 格式引用来源。输出格式如下：\n"
            "调研报告：主题\n\n"
            "【子任务1】原文任务1\n该任务的概括与分析。[source_id]\n\n"
            "【子任务2】原文任务2\n该任务的概括与分析。[source_id]\n\n"
            "【子任务3】原文任务3\n该任务的概括与分析。[source_id]\n\n"
            "【来源】\n[source_id] URL\n"
            "不要输出分析过程、提示词或其他格式说明。\n\n"
            f"主题：{topic}\n"
            f"子任务：{json.dumps(data.sub_task, ensure_ascii=False)}\n"
            f"证据：{json.dumps(self._compact_evidence(data), ensure_ascii=False)}"
        )
        try:
            response = self.model.generate(prompt)
        except Exception as exc:
            raise RuntimeError("盘古模型撰写调用失败") from exc
        if not isinstance(response, str) or not response.strip():
            raise ValueError("盘古模型撰写返回为空")
        return response.strip()

    @staticmethod
    def _compact_evidence(data: AgentState):
        """把重复的 evidence 压缩成唯一来源，减少模型输入和输出截断。"""

        sources = []
        seen = set()
        for item in data.evidence:
            for source_id, context in item.get(next(iter(item), ""), {}).items():
                if source_id in seen:
                    continue
                seen.add(source_id)
                sources.append({"source_id": source_id, "context": context})
        return sources

    @classmethod
    def _validate_model_report(cls, report: str, data: AgentState) -> None:
        """确保每个子任务都有独立小节，并在该小节内出现对应引用。"""

        problems = []
        for sub_task in data.sub_task:
            section = cls._task_section(report, sub_task, data.sub_task)
            if not section:
                problems.append(f"缺少子任务小节：{sub_task}")
                continue

            evidence_items = [item for item in data.evidence if sub_task in item]
            source_ids = set()
            for item in evidence_items:
                source_ids.update(item[sub_task].keys())
            if not source_ids or not all(
                f"[{source_id}]" in section for source_id in source_ids
            ):
                problems.append(f"子任务缺少对应引用：{sub_task}")

        if problems:
            raise ValueError("模型报告前置校验失败；" + "；".join(problems))

    @staticmethod
    def _task_section(report: str, sub_task: str, all_tasks) -> str:
        """截取一个子任务从标题到下一个子任务标题之间的内容。"""

        start = report.find(sub_task)
        if start < 0:
            return ""
        end = len(report)
        for other_task in all_tasks:
            if other_task == sub_task:
                continue
            next_start = report.find(other_task, start + len(sub_task))
            if next_start >= 0:
                end = min(end, next_start)
        return report[start:end]

    def _local_write(self, data: AgentState, input_record: dict, topic: str) -> str:
        """在未启用模型时，根据现有证据生成可验证的本地报告。"""

        lines = [f"调研报告：{topic}", ""]
        for index, sub_task in enumerate(data.sub_task, 1):
            lines.append(f"【子任务{index}】{sub_task}")
            matched = [item for item in data.evidence if sub_task in item]
            if not matched:
                lines.append("未找到对应证据。")
                continue
            for item in matched:
                for source_id, context in item[sub_task].items():
                    lines.append(f"依据来源：{context} [{source_id}]")
            lines.append("")

        lines.append("【来源】")
        seen_sources = set()
        for item in data.evidence:
            for source_id in item.get(next(iter(item), ""), {}):
                if source_id in seen_sources:
                    continue
                seen_sources.add(source_id)
                url = str(input_record.get("url", "")).strip()
                lines.append(f"[{source_id}] {url}".rstrip())
        return "\n".join(lines).strip()

    def calculate(self, data: AgentState) -> float:
        """按子任务对应小节计算引用覆盖率，避免全文搜索造成虚高。"""

        if not isinstance(data, AgentState):
            raise TypeError("calculate 需要 AgentState")
        report = self._latest_report(data)
        return self._coverage(data, report)

    @classmethod
    def _coverage(cls, data: AgentState, report: str) -> float:
        """统计每个子任务小节是否包含其对应的来源编号。"""

        if not data.sub_task or not report:
            return 0.0
        covered = 0
        for sub_task in data.sub_task:
            section = cls._task_section(report, sub_task, data.sub_task)
            if not section:
                continue
            evidence_items = [item for item in data.evidence if sub_task in item]
            source_ids = set()
            for item in evidence_items:
                source_ids.update(item[sub_task].keys())
            if source_ids and all(f"[{source_id}]" in section for source_id in source_ids):
                covered += 1
        return round(covered / len(data.sub_task), 4)

    @staticmethod
    def _input_record(data: AgentState):
        """从状态日志中提取原始输入记录。"""

        for item in data.log:
            try:
                record = json.loads(item)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(record, dict) and record.get("type") == "input":
                return record
        return None

    @staticmethod
    def _latest_report(data: AgentState) -> str:
        """从状态日志中提取最后生成的报告正文。"""

        report = ""
        for item in data.log:
            try:
                record = json.loads(item)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(record, dict) and record.get("type") == "report":
                report = str(record.get("content", ""))
        return report

    @staticmethod
    def _topic(input_record: dict) -> str:
        """从来源 URL 提取主题名称，避免把完整正文当成标题。"""

        url = str(input_record.get("url", "")).strip()
        path_name = unquote(urlparse(url).path.rstrip("/").split("/")[-1])
        if path_name:
            return path_name.replace("_", " ")
        context = str(input_record.get("context", "")).strip()
        return re.split(r"[。！？\n]", context, maxsplit=1)[0][:80] or "当前主题"
