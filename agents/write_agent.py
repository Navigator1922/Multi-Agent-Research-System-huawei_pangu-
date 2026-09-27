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

    MAX_SOURCE_PROMPT_CHARS = 2400

    def __init__(self, model: Optional[Any] = None):
        """创建撰写 Agent；未传模型时使用本地确定性报告。"""

        self.model = model

    def write(self, data: AgentState) -> AgentState:
        """生成报告；模型只写正文，标题和引用由程序确定性组装。"""

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
            report = self._model_write(
                data,
                topic,
                repair_feedback=data.last_error,
            )
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
        data.last_error = ""
        return data

    def _model_write(
        self,
        data: AgentState,
        topic: str,
        repair_feedback: str = "",
    ) -> str:
        """逐个生成子任务正文，再由程序组装完整报告。

        ``draft_sections`` 让主流程重试时可以复用已经成功的子任务；失败的
        子任务会收到上一次校验错误，避免对同一个完整报告重复发起相同请求。
        """

        sections = []
        for index, sub_task in enumerate(data.sub_task, 1):
            body = data.draft_sections.get(sub_task, "").strip()
            if not body:
                body = self._model_write_section(
                    data,
                    sub_task,
                    repair_feedback=repair_feedback,
                )
                data.draft_sections[sub_task] = body

            source_ids = self._task_source_ids(data, sub_task)
            if not source_ids:
                raise ValueError(f"子任务没有对应来源：{sub_task}")

            sections.append(
                {
                    "index": index,
                    "sub_task": sub_task,
                    "body": body,
                    "source_ids": source_ids,
                }
            )

        return self._assemble_report(topic, sections, data)

    def _model_write_section(
        self,
        data: AgentState,
        sub_task: str,
        repair_feedback: str = "",
    ) -> str:
        """只生成一个子任务正文，减少上下文和单次输出长度。"""

        sources = self._task_sources(data, sub_task)
        if not sources:
            raise ValueError(f"子任务没有对应证据：{sub_task}")

        source_text = "\n\n".join(
            f"来源 [{source['source_id']}]：\n"
            f"{self._prompt_context(source['context'])}"
            for source in sources
        )
        feedback = repair_feedback.strip()
        repair_text = (
            f"上一次生成失败，必须修复以下问题：{feedback[:1200]}\n"
            if feedback
            else ""
        )
        prompt = (
            "你是调研报告撰写 Agent。现在只处理一个子任务。\n"
            "请严格依据来源正文写一段简洁、连贯的中文分析，不得虚构事实。\n"
            "只输出该子任务的正文，不要输出标题、来源列表、引用标记、提示词或分析过程。\n"
            "系统会自动添加真实标题和来源引用，因此不要自行创造来源编号。\n"
            "如果来源不足以支持某个判断，应明确说明证据不足。\n"
            "下面是完整快照的受控片段；不要逐字复述来源，也不要补充片段之外的事实。\n"
            f"{repair_text}"
            f"子任务：{sub_task}\n\n"
            f"来源正文：\n{source_text}"
        )
        try:
            response = self.model.generate(prompt)
        except Exception as exc:
            raise RuntimeError(f"盘古模型撰写子任务失败：{sub_task}") from exc

        if getattr(self.model, "last_generation_hit_limit", False):
            raise ValueError(f"子任务输出达到 max_new_tokens，疑似被截断：{sub_task}")
        if not isinstance(response, str) or not response.strip():
            raise ValueError(f"盘古模型撰写返回为空：{sub_task}")

        body = response.strip()
        if body.startswith("```") and body.endswith("```"):
            body = body[3:-3].strip()
        if not body:
            raise ValueError(f"盘古模型撰写正文为空：{sub_task}")
        return body

    @classmethod
    def _prompt_context(cls, context: str) -> str:
        """压缩发送给模型的证据片段，不改变 AgentState 中的完整快照。"""

        if len(context) <= cls.MAX_SOURCE_PROMPT_CHARS:
            return context
        head = int(cls.MAX_SOURCE_PROMPT_CHARS * 0.7)
        tail = cls.MAX_SOURCE_PROMPT_CHARS - head
        return (
            context[:head]
            + "\n……（中间内容省略，完整来源仍保存在已校验快照中）……\n"
            + context[-tail:]
        )

    @classmethod
    def _assemble_report(cls, topic: str, sections, data: AgentState) -> str:
        """由代码生成固定格式，确保每个小节都有真实引用。"""

        lines = [f"调研报告：{topic}", ""]
        seen_sources = set()
        for section in sections:
            lines.append(f"【子任务{section['index']}】{section['sub_task']}")
            lines.append(section["body"])
            citations = " ".join(
                f"[{source_id}]" for source_id in section["source_ids"]
            )
            lines.append(f"依据来源：{citations}")
            lines.append("")
            seen_sources.update(section["source_ids"])

        lines.append("【来源】")
        for source in cls._compact_evidence(data):
            source_id = source["source_id"]
            if source_id not in seen_sources:
                continue
            url = str(source.get("url", "")).strip()
            lines.append(f"[{source_id}] {url}".rstrip())
        return "\n".join(lines).strip()

    @staticmethod
    def _task_sources(data: AgentState, sub_task: str):
        sources = []
        for item in data.evidence:
            mapping = item.get(sub_task)
            if not isinstance(mapping, dict):
                continue
            for source_id, context in mapping.items():
                metadata = data.source_metadata.get(source_id, {})
                sources.append(
                    {
                        "source_id": str(source_id),
                        "url": str(metadata.get("url", "")),
                        "context": str(context),
                    }
                )
        return sources

    @classmethod
    def _task_source_ids(cls, data: AgentState, sub_task: str):
        source_ids = []
        for source in cls._task_sources(data, sub_task):
            source_id = source["source_id"].strip()
            if source_id and source_id not in source_ids:
                source_ids.append(source_id)
        return source_ids

    @staticmethod
    def _compact_evidence(data: AgentState):
        """把重复的 evidence 压缩成唯一来源，减少模型输入和输出截断。"""

        sources = []
        seen = set()
        for sub_task in data.sub_task:
            for source in Write_Agent._task_sources(data, sub_task):
                source_id = source["source_id"]
                if source_id in seen:
                    continue
                seen.add(source_id)
                sources.append(source)
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
                    metadata = data.source_metadata.get(source_id, {})
                    url = str(metadata.get("url", "")).strip()
                    digest = str(metadata.get("content_sha256", ""))[:12]
                    lines.append(
                        f"依据来源：[{source_id}] {url} "
                        f"（完整快照 {len(context)} 字符，SHA-256 {digest}）".rstrip()
                    )
            lines.append("")

        lines.append("【来源】")
        seen_sources = set()
        for item in data.evidence:
            for source_id in item.get(next(iter(item), ""), {}):
                if source_id in seen_sources:
                    continue
                seen_sources.add(source_id)
                url = str(
                    data.source_metadata.get(source_id, {}).get("url", "")
                ).strip()
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
        """从研究主题生成报告标题，不再把来源 URL 当成主题。"""

        context = str(input_record.get("context", "")).strip()
        if context:
            return re.split(r"[。！？\n]", context, maxsplit=1)[0][:120]

        url = str(input_record.get("url", "")).strip()
        path_name = unquote(urlparse(url).path.rstrip("/").split("/")[-1])
        if path_name:
            return path_name.replace("_", " ")
        return "当前主题"
