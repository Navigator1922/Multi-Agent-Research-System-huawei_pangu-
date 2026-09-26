import json

try:
    from config.structure import AgentState
except ModuleNotFoundError:
    from ..config.structure import AgentState

class Write_Agent:
    def __init__(self):
        pass

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

        report = "\n".join(lines).strip()
        data.log.append(
            json.dumps({"type": "report", "content": report}, ensure_ascii=False)
        )
        data.log.append(f"WriteAgent: 报告已生成，长度 {len(report)}")
        data.current_agent = "AuditAgent"
        data.retry_count = 2
        return data

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
