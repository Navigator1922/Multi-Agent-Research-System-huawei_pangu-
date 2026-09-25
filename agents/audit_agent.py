import json
from typing import Dict

try:
    from config.structure import AgentState
except ModuleNotFoundError:
    from ..config.structure import AgentState

class Audit_agent:
    def __init__(self):
        pass

    def baseline(self,data:AgentState)->Dict[str,str]:
        if not isinstance(data, AgentState):
            raise TypeError("baseline 需要 AgentState")
        report = self._latest_report(data)
        coverage = self._coverage(data, report)
        return {
            "method": "单Agent一次性撰写",
            "overall_steps": "1" if report else "0",
            "total_retries": "0",
            "coverage_rate": f"{coverage:.4f}",
        }

    def audit(self,data:AgentState)->AgentState:
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
            task_evidence = [item for item in data.evidence if sub_task in item]
            if not task_evidence:
                issues.append(f"子任务缺少证据：{sub_task}")
                continue
            source_ids = task_evidence[0][sub_task].keys()
            if not any(f"[{source_id}]" in report for source_id in source_ids):
                issues.append(f"子任务缺少有效引用：{sub_task}")

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
    def _coverage(data: AgentState, report: str) -> float:
        if not data.sub_task or not report:
            return 0.0
        covered = 0
        for sub_task in data.sub_task:
            for item in data.evidence:
                if sub_task not in item:
                    continue
                if any(
                    f"[{source_id}]" in report
                    for source_id in item[sub_task].keys()
                ):
                    covered += 1
                break
        return covered / len(data.sub_task)
