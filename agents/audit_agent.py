import json
import re

try:
    from config.structure import AgentState,DataBlock
except ModuleNotFoundError:
    from ..config.structure import AgentState,DataBlock


class Audit_agent:
    def __init__(self):
        self._ai_flavor_phrases = (
            "综上所述",
            "总的来说",
            "总而言之",
            "值得注意的是",
            "不可忽视的是",
            "在当今时代",
            "本文将",
            "可以看出",
            "展望未来",
            "一方面",
            "另一方面",
        )

    def kpi(self, data: AgentState) -> AgentState:
        if not isinstance(data, AgentState):
            raise TypeError("kpi 需要 AgentState")
        if not isinstance(data.evidence, list):
            raise TypeError("evidence 必须是列表")

        report = ""
        for item in data.log:
            try:
                record = json.loads(item)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(record, dict) and record.get("type") == "report":
                report = str(record.get("content", ""))

        covered_tasks = 0
        checked_tasks = 0
        for task_index, sub_task in enumerate(data.sub_task):
            if task_index >= len(data.evidence):
                raise ValueError(f"evidence 缺少子任务：{sub_task}")
            task_mapping = data.evidence[task_index]
            if not isinstance(task_mapping, dict) or set(task_mapping) != {sub_task}:
                raise ValueError(f"evidence 子任务映射格式错误：{sub_task}")
            source_mapping = task_mapping[sub_task]
            if not isinstance(source_mapping, dict) or not source_mapping:
                raise ValueError(f"子任务没有来源映射：{sub_task}")
            checked_tasks += 1

            heading = f"## {sub_task}"
            start = report.find(heading)
            if start < 0:
                continue
            next_heading = re.search(r"\n## ", report[start + len(heading):])
            end = start + len(heading) + next_heading.start() if next_heading else len(report)
            section = report[start:end]
            task_covered = True
            for source_id, blocks in source_mapping.items():
                if not isinstance(blocks, list) or not blocks:
                    raise ValueError(f"来源没有 DataBlock：{source_id}")
                for block in blocks:
                    if not isinstance(block, DataBlock):
                        raise TypeError("evidence 最内层必须全部是 DataBlock 对象")
                    if block.type not in {"text", "image", "table"}:
                        raise ValueError(f"不支持的 DataBlock 类型：{block.type}")
                    if not isinstance(block.metadata, dict):
                        raise TypeError("DataBlock.metadata 必须是字典")
                if f"[{source_id}]" not in section:
                    task_covered = False
            if task_covered:
                covered_tasks += 1

        coverage = covered_tasks / checked_tasks if checked_tasks else 0.0
        data.audit_metrics["coverage_rate"] = round(float(coverage), 4)
        data.overall_steps += 1
        data.current_agent = "AuditAgent"
        data.log.append(
            json.dumps(
                {
                    "type": "audit_kpi",
                    "coverage_rate": data.audit_metrics["coverage_rate"],
                    "covered_tasks": covered_tasks,
                    "total_tasks": checked_tasks,
                },
                ensure_ascii=False,
            )
        )
        return data

    def audit(self, data: AgentState) -> AgentState:
        import json
        import re

        if not isinstance(data, AgentState):
            raise TypeError("audit 需要 AgentState")
        if not isinstance(data.audit_metrics, dict):
            raise TypeError("audit_metrics 必须是字典")

        report = ""
        for item in data.log:
            try:
                record = json.loads(item)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(record, dict) and record.get("type") == "report":
                report = str(record.get("content", ""))

        phrases = tuple(self._ai_flavor_phrases)
        phrase_hits = sum(report.count(phrase) for phrase in phrases)
        sentence_count = len(
            [sentence for sentence in re.split(r"[。！？!?\.]+", report) if sentence.strip()]
        )
        ai_rate = min(1.0, phrase_hits / max(1, sentence_count))
        data.audit_metrics["ai_flavor_rate"] = round(float(ai_rate), 4)
        data.overall_steps += 1

        coverage = float(data.audit_metrics.get("coverage_rate", 0.0))
        issues = []
        if not report.strip():
            issues.append("报告为空")
        if coverage < 1.0:
            issues.append(f"引用覆盖率不足：{coverage:.4f}")
        if ai_rate > 0.35:
            issues.append(f"AI 味词频过高：{ai_rate:.4f}")

        data.log.append(
            json.dumps(
                {
                    "type": "audit_result",
                    "coverage_rate": coverage,
                    "ai_flavor_rate": data.audit_metrics["ai_flavor_rate"],
                    "issues": issues,
                },
                ensure_ascii=False,
            )
        )
        data.current_agent = "AuditAgent"
        if issues:
            # 保持状态为运行中，以便 main.py 应用重试策略；抛出异常可让该策略感知审核失败。
            raise RuntimeError("审核未通过：" + "；".join(issues))

        data.status = "Completed"
        data.retry_count = 0
        data.log.append("AuditAgent: 审核通过")
        return data
