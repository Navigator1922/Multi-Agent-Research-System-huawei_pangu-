import json
from typing import Any, Optional

try:
    from config.structure import AgentState
except ModuleNotFoundError:
    from ..config.structure import AgentState

class Write_Agent:
    def __init__(self, model: Optional[Any] = None):
        """创建撰写 Agent；未传模型时使用本地模板生成报告。"""

        self.model = model

    def write(self,data:AgentState)->AgentState:
        if not isinstance(data, AgentState):
            raise TypeError("write 需要 AgentState")
        if not data.sub_task:
            raise ValueError("没有可撰写的子任务")
        if not data.evidence:
            raise ValueError("没有证据，不能生成报告")

        data.overall_steps += 1
        input_record = self._input_record(data) or {}
        topic = str(input_record.get("context", "当前主题"))
        if self.model is not None:
            report = self._model_write(data, topic)
        else:
            report = ""
        if not report:
            report = self._local_write(data, input_record, topic)
        report = self._append_missing_citations(report, data)

        data.log.append(
            json.dumps({"type": "report", "content": report}, ensure_ascii=False)
        )
        data.log.append(f"WriteAgent: 报告已生成，长度 {len(report)}")
        data.current_agent = "AuditAgent"
        data.retry_count = 2
        return data

    def _model_write(self, data: AgentState, topic: str) -> str:
        """调用盘古模型根据主题、子任务和证据生成报告正文。"""

        prompt = (
            "你是一个严谨的调研报告撰写 Agent。请根据主题、子任务和证据生成中文报告。"
            "报告必须覆盖每个子任务，只能使用给出的证据，不得虚构事实。"
            "每使用一个来源，都必须在相关内容后保留 [source_id] 格式的引用。"
            "只输出报告正文，不要输出分析过程。\n\n"
            f"主题：{topic}\n"
            f"子任务：{json.dumps(data.sub_task, ensure_ascii=False)}\n"
            f"证据：{json.dumps(data.evidence, ensure_ascii=False)}"
        )
        try:
            response = self.model.generate(prompt)
        except Exception:
            return ""
        return response.strip() if isinstance(response, str) else ""

    def _local_write(self, data: AgentState, input_record: dict, topic: str) -> str:
        """在未启用模型时，根据现有证据生成确定性的本地报告。"""

        lines = [f"调研报告：{topic}", "", "研究内容与证据："]

        for index, sub_task in enumerate(data.sub_task, 1):
            lines.append(f"{index}. {sub_task}")
            matched = [item for item in data.evidence if sub_task in item]
            if not matched:
                lines.append("   未找到对应证据。")
                continue
            for item in matched:
                for source_id, context in item[sub_task].items():
                    lines.append(f"   {context} [{source_id}]")

        lines.append("")
        lines.append("来源：")
        seen_sources = set()
        for item in data.evidence:
            for source_id in item.get(next(iter(item), ""), {}):
                if source_id in seen_sources:
                    continue
                seen_sources.add(source_id)
                url = str(input_record.get("url", "")).strip()
                lines.append(f"[{source_id}] {url}".rstrip())

        return "\n".join(lines).strip()

    @staticmethod
    def _append_missing_citations(report: str, data: AgentState) -> str:
        """为模型遗漏的来源引用补上原始证据，保证审核可追溯。"""

        additions = []
        for item in data.evidence:
            for sub_task, sources in item.items():
                for source_id, context in sources.items():
                    if f"[{source_id}]" not in report:
                        additions.append(f"\n{sub_task}：{context} [{source_id}]")
        return report + "".join(additions)

    def calculate(self,data:AgentState)->float:
        if not isinstance(data, AgentState):
            raise TypeError("calculate 需要 AgentState")
        report = self._latest_report(data)
        if not data.sub_task or not report:
            return 0.0

        covered = 0
        for sub_task in data.sub_task:
            for item in data.evidence:
                if sub_task not in item:
                    continue
                source_ids = item[sub_task].keys()
                if any(f"[{source_id}]" in report for source_id in source_ids):
                    covered += 1
                break
        return round(covered / len(data.sub_task), 4)

    @staticmethod
    def _input_record(data: AgentState):
        """从状态日志中提取主题和来源信息，供报告生成使用。

        返回原始输入字典；如果日志中没有合法的输入记录，则返回 ``None``。
        """

        for item in data.log:
            try:
                record = json.loads(item)
            except (TypeError, json.JSONDecodeError):
                # 只跳过普通文本日志，不影响后续记录的查找。
                continue
            if isinstance(record, dict) and record.get("type") == "input":
                return record
        return None

    @staticmethod
    def _latest_report(data: AgentState) -> str:
        """从状态日志中提取最后生成的报告正文。

        撰写结果保存在日志中的 ``type=report`` JSON 记录里，
        因此审核或计算覆盖率时都通过这个函数读取。
        """

        report = ""
        for item in data.log:
            try:
                record = json.loads(item)
            except (TypeError, json.JSONDecodeError):
                # 普通文本日志不包含报告内容。
                continue
            if isinstance(record, dict) and record.get("type") == "report":
                report = str(record.get("content", ""))
        return report
