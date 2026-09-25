from __future__ import annotations

import re
from typing import Any, Dict, List

try:
    from config.structure import AgentState, add_message, record_event
except ModuleNotFoundError:  # Supports package execution from the parent folder.
    from ..config.structure import AgentState, add_message, record_event


class Audit_agent:
    def __init__(self):
        pass

    def baseline(self, data: AgentState) -> Dict[str, str]:
        """Return a transparent one-pass baseline for comparison."""

        completed = bool(data.report and data.evidence and data.sub_task)
        return {
            "mode": "single_agent_one_pass",
            "task_completion_rate": (
                f"{data.task_completion_rate:.4f}" if completed else "0.0000"
            ),
            "citation_coverage": f"{data.coverage_rate:.4f}" if completed else "0.0000",
            "overall_steps": "1" if completed else "0",
            "total_retries": "0",
        }

    def audit(self, data: AgentState) -> AgentState:
        if not isinstance(data, AgentState):
            raise TypeError("Audit_agent.audit 需要 AgentState")

        data.overall_steps += 1
        record_event(data, "agent_start", agent="AuditAgent")
        issues: List[str] = []
        valid_source_ids = {
            str(item.get("source_id"))
            for item in data.evidence
            if item.get("source_id")
        }
        cited_source_ids = set(re.findall(r"\[([^\]]+)\]", data.report or ""))
        invalid_citations = sorted(cited_source_ids - valid_source_ids)
        if not data.report.strip():
            issues.append("报告内容为空")
        if not data.evidence:
            issues.append("没有保留检索证据")
        if invalid_citations:
            issues.append(f"存在无效引用: {', '.join(invalid_citations)}")

        missing_tasks: List[str] = []
        completed_task_count = 0
        for index, sub_task in enumerate(data.sub_task, 1):
            task_id = f"subtask_{index:03d}"
            task_evidence = [
                item for item in data.evidence if str(item.get("task_id")) == task_id
            ]
            if not task_evidence:
                missing_tasks.append(sub_task)
                continue
            completed_task_count += 1
            if not any(
                f"[{item.get('source_id')}]" in data.report
                for item in task_evidence
            ):
                missing_tasks.append(sub_task)
        if missing_tasks:
            issues.append("缺少带有效引用的子任务: " + "；".join(missing_tasks))

        data.task_completion_rate = (
            round(completed_task_count / len(data.sub_task), 4)
            if data.sub_task
            else 0.0
        )
        data.audit_result = {
            "passed": not issues,
            "issues": issues,
            "task_completion_rate": data.task_completion_rate,
            "citation_coverage": data.coverage_rate,
            "valid_source_count": len(valid_source_ids),
            "cited_source_count": len(cited_source_ids & valid_source_ids),
            "invalid_citations": invalid_citations,
        }
        data.status = "Completed"
        data.current_agent = "AuditAgent"
        data.retry_count = data.max_retries + 1
        record_event(data, "audit_complete", **data.audit_result)
        add_message(
            data,
            sender="AuditAgent",
            receiver="System",
            message_type="audit_result",
            payload=data.audit_result,
            evidence=data.evidence,
            status="success" if data.audit_result["passed"] else "warning",
        )
        return data
