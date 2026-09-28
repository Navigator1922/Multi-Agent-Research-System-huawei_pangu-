"""使用模型完成证据覆盖率和报告风格审核。"""

from __future__ import annotations

import json
import re

from config.structure import AgentState, DataBlock


class Audit_agent:
    """通过两次严格的模型评审计算审核指标。"""

    def __init__(self, model):
        if model is None or not callable(getattr(model, "generate", None)):
            raise RuntimeError("Audit_agent 必须注入可用的 UniversalModel")
        self.model = model

    def kpi(self, data: AgentState) -> AgentState:
        """让模型逐个判断章节结论是否真正使用了对应 DataBlock。"""

        if not isinstance(data, AgentState):
            raise TypeError("kpi 需要 AgentState")
        if not isinstance(data.evidence, list) or len(data.evidence) != len(data.sub_task):
            raise ValueError("kpi 需要与 sub_task 一一对应的 evidence")

        report = _latest_report(data)
        task_payload = []
        allowed_ids_by_task = {}
        for task_index, sub_task in enumerate(data.sub_task):
            task_mapping = data.evidence[task_index]
            if not isinstance(task_mapping, dict) or set(task_mapping) != {sub_task}:
                raise ValueError(f"evidence 子任务映射格式错误：{sub_task}")
            block_payload = []
            task_allowed_ids = set()
            for source_id, blocks in task_mapping[sub_task].items():
                if not isinstance(blocks, list) or not blocks:
                    raise ValueError(f"来源没有 DataBlock：{source_id}")
                for block_index, block in enumerate(blocks):
                    if not isinstance(block, DataBlock):
                        raise TypeError("evidence 最内层必须全部是 DataBlock 对象")
                    block_id = f"task-{task_index}:source-{source_id}:block-{block_index}"
                    task_allowed_ids.add(block_id)
                    block_payload.append(
                        {
                            "block_id": block_id,
                            "type": block.type,
                            "content": _clip(block.content, 3000),
                            "metadata": block.metadata,
                        }
                    )
            allowed_ids_by_task[sub_task] = task_allowed_ids
            task_payload.append(
                {
                    "sub_task": sub_task,
                    "report_section": _task_section(report, sub_task, data.sub_task),
                    "evidence": block_payload,
                }
            )

        prompt = (
            "你是严谨的调研报告证据审计 Agent。请逐个检查每个子任务章节的结论，"
            "判断结论是否确实由该章节提供的 DataBlock 支撑，而不是只检查引用编号。"
            "只有正文结论与 DataBlock 内容存在明确语义对应时，covered 才能为 true。"
            "只输出合法 JSON，不要输出解释、Markdown 或代码围栏。严格格式："
            '{"task_results":[{"sub_task":"原子任务","covered":true,"used_block_ids":["块编号"],"reason":"判断依据"}]}\n\n'
            f"报告与证据：{json.dumps(task_payload, ensure_ascii=False)}"
        )
        response = self.model.generate(prompt)
        results = _parse_coverage_response(
            response,
            data.sub_task,
            allowed_ids_by_task,
        )
        covered_count = sum(1 for item in results if item["covered"])
        coverage_rate = covered_count / len(data.sub_task)
        data.audit_metrics["coverage_rate"] = round(coverage_rate, 4)
        data.overall_steps += 1
        data.current_agent = "AuditAgent"
        data.log.append(
            json.dumps(
                {
                    "type": "audit_kpi",
                    "coverage_rate": data.audit_metrics["coverage_rate"],
                    "task_results": results,
                },
                ensure_ascii=False,
            )
        )
        return data

    def audit(self, data: AgentState) -> AgentState:
        """让模型从三个维度评估报告的 AI 味并触发真实重试。"""

        if not isinstance(data, AgentState):
            raise TypeError("audit 需要 AgentState")
        if not isinstance(data.audit_metrics, dict):
            raise TypeError("audit_metrics 必须是字典")

        report = _latest_report(data)
        prompt = (
            "你是调研报告风格审计 Agent。请阅读完整报告，分别从以下三个维度评分："
            "句式多样性、机器味副词、排版僵化度。每个维度和 ai_flavor_rate 都必须是 0 到 1 的浮点数，"
            "其中 ai_flavor_rate 越高表示越像机器生成。请给出可执行的修改反馈。"
            "只输出合法 JSON，不要输出解释、Markdown 或代码围栏。严格格式："
            '{"sentence_diversity":0.0,"machine_adverb_usage":0.0,"layout_rigidity":0.0,"ai_flavor_rate":0.0,"feedback":"详细反馈"}\n\n'
            f"当前引用覆盖率：{data.audit_metrics.get('coverage_rate', 0.0)}\n"
            f"报告：\n{report}"
        )
        response = self.model.generate(prompt)
        result = _parse_style_response(response)
        data.audit_metrics["ai_flavor_rate"] = result["ai_flavor_rate"]
        data.overall_steps += 1

        coverage = float(data.audit_metrics.get("coverage_rate", 0.0))
        issues = []
        if coverage < 1.0:
            issues.append(
                f"证据覆盖率未达标：{coverage:.4f}；"
                f"逐任务反馈：{_latest_coverage_feedback(data)}"
            )
        if result["ai_flavor_rate"] > 0.4:
            issues.append(
                f"AI 味评分超过阈值：{result['ai_flavor_rate']:.4f}；"
                f"风格反馈：{result['feedback']}"
            )
        feedback = "；".join(issues)
        data.log.append(
            json.dumps(
                {
                    "type": "audit_result",
                    "coverage_rate": coverage,
                    "ai_flavor_rate": result["ai_flavor_rate"],
                    "sentence_diversity": result["sentence_diversity"],
                    "machine_adverb_usage": result["machine_adverb_usage"],
                    "layout_rigidity": result["layout_rigidity"],
                    "feedback": result["feedback"],
                    "issues": issues,
                },
                ensure_ascii=False,
            )
        )
        data.current_agent = "AuditAgent"
        if feedback:
            raise ValueError(feedback)

        data.status = "Completed"
        data.retry_count = 0
        data.log.append("AuditAgent: 审核通过")
        return data


def _latest_report(data: AgentState) -> str:
    """从 log 中取得最后一份报告。"""

    report = ""
    for item in data.log:
        try:
            record = json.loads(item)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(record, dict) and record.get("type") == "report":
            report = str(record.get("content", ""))
    if not report.strip():
        raise ValueError("审核缺少有效报告")
    return report


def _task_section(report: str, sub_task: str, all_tasks: list[str]) -> str:
    """截取单个子任务章节供模型进行证据对应判断。"""

    heading = f"## {sub_task}"
    start = report.find(heading)
    if start < 0:
        return ""
    end = len(report)
    for other_task in all_tasks:
        if other_task == sub_task:
            continue
        other_start = report.find(f"## {other_task}", start + len(heading))
        if other_start >= 0:
            end = min(end, other_start)
    return report[start:end]


def _parse_coverage_response(response, sub_tasks, allowed_ids_by_task):
    """严格解析模型的证据覆盖判断。"""

    payload = _parse_json_object(response, "覆盖率审核")
    if set(payload) != {"task_results"} or not isinstance(payload["task_results"], list):
        raise ValueError("覆盖率审核结果必须只包含 task_results 列表")
    raw_results = payload["task_results"]
    if len(raw_results) != len(sub_tasks):
        raise ValueError("覆盖率审核结果数量与 sub_task 不一致")

    by_task = {}
    for item in raw_results:
        if not isinstance(item, dict) or set(item) != {
            "sub_task",
            "covered",
            "used_block_ids",
            "reason",
        }:
            raise ValueError("覆盖率审核单项字段格式错误")
        sub_task = item["sub_task"]
        if not isinstance(sub_task, str):
            raise ValueError("覆盖率审核 sub_task 必须是字符串")
        if sub_task in by_task or sub_task not in sub_tasks:
            raise ValueError("覆盖率审核包含未知或重复的 sub_task")
        if not isinstance(item["covered"], bool):
            raise ValueError("覆盖率审核 covered 必须是布尔值")
        if not isinstance(item["used_block_ids"], list) or any(
            not isinstance(block_id, str)
            or block_id not in allowed_ids_by_task[sub_task]
            for block_id in item["used_block_ids"]
        ):
            raise ValueError("覆盖率审核使用了不存在的 DataBlock")
        if item["covered"] and not item["used_block_ids"]:
            raise ValueError("覆盖率审核不能在没有使用 DataBlock 时判定 covered=true")
        if not isinstance(item["reason"], str) or not item["reason"].strip():
            raise ValueError("覆盖率审核 reason 不能为空")
        by_task[sub_task] = item
    if set(by_task) != set(sub_tasks):
        raise ValueError("覆盖率审核没有覆盖全部 sub_task")
    return [by_task[sub_task] for sub_task in sub_tasks]


def _parse_style_response(response):
    """严格解析模型的风格评分。"""

    payload = _parse_json_object(response, "AI 味审核")
    required = {
        "sentence_diversity",
        "machine_adverb_usage",
        "layout_rigidity",
        "ai_flavor_rate",
        "feedback",
    }
    if set(payload) != required:
        raise ValueError("AI 味审核结果字段不完整或包含未知字段")
    for key in required - {"feedback"}:
        if not isinstance(payload[key], (int, float)) or not 0 <= payload[key] <= 1:
            raise ValueError(f"AI 味审核评分不在 0 到 1 范围内：{key}")
    if not isinstance(payload["feedback"], str):
        raise ValueError("AI 味审核 feedback 必须是字符串")
    return payload


def _parse_json_object(response, name):
    """解析指定审核阶段返回的 JSON 对象。"""

    if not isinstance(response, str) or not response.strip():
        raise ValueError(f"{name}模型返回为空")
    try:
        payload = json.loads(response.strip().lstrip("\ufeff"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name}模型返回的 JSON 无法解析") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{name}模型返回必须是 JSON 对象")
    return payload


def _latest_coverage_feedback(data: AgentState) -> str:
    """从最近一次覆盖率审核记录提取逐任务反馈。"""

    latest = None
    for item in data.log:
        try:
            record = json.loads(item)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(record, dict) and record.get("type") == "audit_kpi":
            latest = record
    if not latest or not isinstance(latest.get("task_results"), list):
        return "模型没有提供逐任务覆盖反馈"
    return "；".join(
        f"{item.get('sub_task', '未知任务')}：{item.get('reason', '无理由')}"
        for item in latest["task_results"]
        if isinstance(item, dict)
    ) or "模型没有提供逐任务覆盖反馈"


def _clip(value: str, limit: int) -> str:
    """限制提示词中的单块长度，同时明确标记内容被截取。"""

    if len(value) <= limit:
        return value
    return value[:limit] + "\n[证据片段已截取]"
