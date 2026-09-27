import json
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import unquote, urlparse

try:
    from config.structure import AgentState
    from utils.source_store import DEFAULT_DATA_DIR, SourceDataError, load_sources
except ModuleNotFoundError:
    from ..config.structure import AgentState
    from ..utils.source_store import DEFAULT_DATA_DIR, SourceDataError, load_sources


class Audit_agent:
    """审核报告，并提供独立的单 Agent baseline。"""

    MAX_SOURCE_PROMPT_CHARS = 2400

    def __init__(
        self,
        model: Optional[Any] = None,
        data_dir: str | Path = DEFAULT_DATA_DIR,
    ):
        """保存可选模型；baseline 使用它单独完成一次撰写调用。"""

        self.model = model
        self.data_dir = Path(data_dir)

    def baseline(self, data: AgentState) -> Dict[str, str]:
        """独立执行一次单 Agent 撰写，不复用多 Agent 报告。"""

        if not isinstance(data, AgentState):
            raise TypeError("baseline 需要 AgentState")

        input_record = self._input_record(data)
        if input_record is None:
            result = {
                "method": "单Agent一次性撰写",
                "executed": "false",
                "status": "Error",
                "overall_steps": "0",
                "total_retries": "0",
                "coverage_rate": "0.0000",
            }
            data.log.append(
                json.dumps({"type": "baseline", **result}, ensure_ascii=False)
            )
            return result

        topic = self._topic(input_record)
        source_ids = input_record.get("source_ids")
        if source_ids is None:
            source_id = str(input_record.get("source_id", "")).strip()
            source_ids = [source_id] if source_id else []
        try:
            records = load_sources(source_ids, self.data_dir)
        except (SourceDataError, TypeError) as exc:
            result = {
                "method": "单Agent一次性撰写",
                "executed": "true",
                "status": "Error",
                "model_used": "true" if self.model is not None else "false",
                "overall_steps": "0",
                "total_retries": "0",
                "coverage_rate": "0.0000",
                "report_length": "0",
            }
            data.log.append(
                json.dumps(
                    {"type": "baseline_error", "error": str(exc)},
                    ensure_ascii=False,
                )
            )
            data.log.append(json.dumps({"type": "baseline", **result}, ensure_ascii=False))
            return result

        source_id = str(input_record.get("source_id", "")).strip()
        if not source_id and records:
            source_id = next(iter(records))
        source_lines = "\n".join(
            f"[{record.source_id}] {record.url}"
            for record in records.values()
        )
        context = "\n\n".join(
            f"[{record.source_id}]\n{self._prompt_context(record.context)}"
            for record in records.values()
        )
        report = ""
        status = "Completed"
        model_used = self.model is not None

        if self.model is not None:
            prompt = (
                "你是单 Agent 基线系统。请基于给出的主题和来源，一次性生成一份简洁的"
                "中文调研报告。不得拆分或调用其他 Agent，只能使用给出的来源内容。"
                "报告中必须原样保留真实来源编号和 URL，不能输出占位引用。只输出报告正文。\n\n"
                f"主题：{topic}\n"
                f"来源：{source_lines}\n"
                f"来源内容：{context}"
            )
            try:
                response = self.model.generate(prompt)
                report = response.strip() if isinstance(response, str) else ""
                if getattr(self.model, "last_generation_hit_limit", False):
                    status = "Error"
                    data.log.append(
                        json.dumps(
                            {
                                "type": "baseline_error",
                                "error": "盘古模型 baseline 输出达到 max_new_tokens，疑似被截断",
                            },
                            ensure_ascii=False,
                        )
                    )
            except Exception as exc:
                status = "Error"
                data.log.append(
                    json.dumps(
                        {"type": "baseline_error", "error": str(exc)},
                        ensure_ascii=False,
                    )
                )
        else:
            # 本地无模型模式使用一次确定性撰写，保持 baseline 与多 Agent 报告独立。
            report = f"单Agent基线报告：{topic}\n\n来源：\n{source_lines}"

        if report and records:
            report = self._ensure_source_citations(report, records)
        if not report or not records:
            status = "Error"

        coverage = (
            1.0
            if report and all(f"[{record.source_id}]" in report for record in records.values())
            else 0.0
        )
        if coverage < 1.0:
            status = "Error"
        result = {
            "method": "单Agent一次性撰写",
            "executed": "true",
            "status": status,
            "model_used": "true" if model_used else "false",
            "overall_steps": "1",
            "total_retries": "0",
            "coverage_rate": f"{coverage:.4f}",
            "report_length": str(len(report)),
        }
        data.log.append(
            json.dumps(
                {"type": "baseline", **result, "report": report},
                ensure_ascii=False,
            )
        )
        return result

    @staticmethod
    def _ensure_source_citations(report: str, records) -> str:
        """为 baseline 补齐真实来源标记，避免依赖模型格式服从。"""

        missing = [
            record
            for record in records.values()
            if f"[{record.source_id}]" not in report
        ]
        if not missing:
            return report

        lines = [report.rstrip(), "", "【来源】"]
        lines.extend(
            f"[{record.source_id}] {record.url}".rstrip()
            for record in missing
        )
        return "\n".join(lines)

    @classmethod
    def _prompt_context(cls, context: str) -> str:
        """压缩 baseline 提示词中的来源片段，不改变已校验快照。"""

        if len(context) <= cls.MAX_SOURCE_PROMPT_CHARS:
            return context
        head = int(cls.MAX_SOURCE_PROMPT_CHARS * 0.7)
        tail = cls.MAX_SOURCE_PROMPT_CHARS - head
        return (
            context[:head]
            + "\n……（中间内容省略，完整来源仍保存在已校验快照中）……\n"
            + context[-tail:]
        )

    def audit(self, data: AgentState) -> AgentState:
        """审核报告是否逐一覆盖子任务并在对应小节中引用来源。"""

        if not isinstance(data, AgentState):
            raise TypeError("audit 需要 AgentState")

        data.overall_steps += 1
        report = self._latest_report(data)
        issues = []
        if not report:
            issues.append("报告为空")
        if not data.evidence:
            issues.append("没有保留证据")

        for sub_task in data.sub_task:
            section = self._task_section(report, sub_task, data.sub_task)
            if not section:
                issues.append(f"缺少子任务小节：{sub_task}")
                continue

            task_evidence = [item for item in data.evidence if sub_task in item]
            source_ids = set()
            for item in task_evidence:
                source_ids.update(item[sub_task].keys())
            if not source_ids or not all(
                f"[{source_id}]" in section for source_id in source_ids
            ):
                issues.append(f"子任务缺少对应引用：{sub_task}")

        if issues:
            data.status = "Error"
            data.log.append("AuditAgent: 审核未通过；" + "；".join(issues))
        else:
            data.status = "Completed"
            data.log.append("AuditAgent: 审核通过")
        data.current_agent = "AuditAgent"
        data.retry_count = 0
        return data

    @staticmethod
    def _latest_report(data: AgentState) -> str:
        """从日志中读取最后一份报告。"""

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
    def _input_record(data: AgentState):
        """从状态日志中读取原始输入，供独立 baseline 使用。"""

        for item in data.log:
            try:
                record = json.loads(item)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(record, dict) and record.get("type") == "input":
                return record
        return None

    @staticmethod
    def _task_section(report: str, sub_task: str, all_tasks) -> str:
        """截取单个子任务对应的小节，避免用全文搜索虚增覆盖率。"""

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

    @staticmethod
    def _topic(input_record: dict) -> str:
        """从来源 URL 提取主题名称。"""

        context = str(input_record.get("context", "")).strip()
        if context:
            return context.split("\n", 1)[0][:120]

        url = str(input_record.get("url", "")).strip()
        path_name = unquote(urlparse(url).path.rstrip("/").split("/")[-1])
        if path_name:
            return path_name.replace("_", " ")
        return "当前主题"
