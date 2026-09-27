import json
import re
from typing import Any, List, Optional
from urllib.parse import unquote, urlparse

try:
    from config.structure import ContextInput, AgentState
except ModuleNotFoundError:
    from ..config.structure import ContextInput, AgentState


class Plan_Agent:
    """负责把原始调研输入拆分成可执行的子任务。"""

    def __init__(self, model: Optional[Any] = None):
        """创建规划 Agent；未传模型时使用本地确定性规划。"""

        self.model = model
        self._last_model_response = ""

    def Planning(self, data: ContextInput) -> AgentState:
        """初始化状态并执行规划；模型规划失败时按原有重试规则重试。"""

        if not isinstance(data, ContextInput):
            raise TypeError("Planning 需要 ContextInput")
        if not data.context.strip():
            raise ValueError("context 不能为空")

        state = AgentState()
        source_ids = list(data.source_ids)
        if not source_ids and data.source_id.strip():
            source_ids = [data.source_id.strip()]
        state.log.append(
            json.dumps(
                {
                    "type": "input",
                    "context": data.context,
                    "source_id": data.source_id,
                    "source_ids": source_ids,
                    "url": data.url,
                },
                ensure_ascii=False,
            )
        )
        state.log.append("PlanAgent: 已接收调研主题")

        # Planning 在主流程进入循环前执行，因此规划阶段的重试在这里完成，
        # 但仍然沿用 AgentState 中的 retry_count 和 total_retries 字段。
        while state.status == "Running":
            try:
                return self.Split(state)
            except Exception as exc:
                state.log.append(
                    json.dumps(
                        {
                            "type": "plan_error",
                            "error": str(exc),
                            "model_output": self._last_model_response[:4000],
                        },
                        ensure_ascii=False,
                    )
                )
                state.log.append(f"工位 PlanAgent 执行异常: {exc}")
                state.last_error = f"PlanAgent: {exc}"
                if state.retry_count > 0:
                    state.retry_count -= 1
                    state.total_retries += 1
                    state.log.append(
                        f"工位 PlanAgent 将重试，剩余重试次数: {state.retry_count}"
                    )
                    continue

                state.status = "Error"
                state.log.append("工位 PlanAgent 已达到最大重试次数")
                return state

    def Split(self, task: AgentState) -> AgentState:
        """生成至少三个子任务；模型模式下不允许静默回退到固定任务。"""

        if not isinstance(task, AgentState):
            raise TypeError("Split 需要 AgentState")

        task.overall_steps += 1
        input_record = self._input_record(task)
        topic = self._topic(input_record) if input_record else "当前主题"
        selected = [item.strip() for item in task.sub_task if item.strip()]

        if self.model is not None:
            selected = self._model_split(topic, repair_feedback=task.last_error)
            if len(selected) < 3:
                raise ValueError("盘古模型没有生成至少三个有效子任务")
            task.log.append("PlanAgent: 已使用盘古模型生成子任务")
        else:
            # 本地无模型模式仍提供确定性规划，便于在 VS Code 中验证流程。
            default_tasks = [
                f"研究{topic}的背景与基本概念",
                f"分析{topic}的主要特点、应用与影响",
                f"总结{topic}存在的问题、风险与发展方向",
            ]
            for item in default_tasks:
                if len(selected) >= 3:
                    break
                if item not in selected:
                    selected.append(item)

        if len(selected) < 3:
            raise ValueError("规划结果必须至少包含三个子任务")

        task.sub_task = selected
        task.current_agent = "RetrieveAgent"
        task.retry_count = 2
        task.last_error = ""
        task.log.append(f"PlanAgent: 已拆分 {len(task.sub_task)} 个子任务")
        task.log.append(
            json.dumps(
                {"type": "sub_tasks", "items": task.sub_task},
                ensure_ascii=False,
            )
        )
        return task

    def _model_split(self, topic: str, repair_feedback: str = "") -> List[str]:
        """调用盘古模型并严格解析 JSON 子任务结果。"""

        self._last_model_response = ""
        repair_text = (
            f"上一次规划失败，必须修复以下问题：{repair_feedback[:1200]}\n"
            if repair_feedback
            else ""
        )
        prompt = (
            "你是调研系统的规划 Agent。请把下面的主题拆分为至少三个相互独立、"
            "不能互相重复的子任务。每个子任务必须是可以由资料证据回答的具体问题。"
            "只返回 JSON，不要返回解释、Markdown 或代码围栏。格式必须是："
            '{"sub_tasks":["任务1","任务2","任务3"]}\n'
            f"{repair_text}"
            f"调研主题：{topic}"
        )
        try:
            response = self.model.generate(prompt)
        except Exception as exc:
            raise RuntimeError("盘古模型规划调用失败") from exc

        if not isinstance(response, str) or not response.strip():
            raise ValueError("盘古模型规划返回为空")
        self._last_model_response = response

        payload = self._parse_json_payload(response)
        if isinstance(payload, dict):
            payload = payload.get("sub_tasks", payload.get("tasks"))
        if not isinstance(payload, list):
            raise ValueError("盘古模型规划结果不是子任务列表")

        tasks: List[str] = []
        for item in payload:
            if not isinstance(item, str) or not item.strip():
                continue
            normalized = item.strip()
            if normalized not in tasks:
                tasks.append(normalized)
        if len(tasks) < 3:
            raise ValueError("盘古模型规划结果少于三个有效子任务")
        return tasks

    @staticmethod
    def _parse_json_payload(response: str):
        """从模型文本中提取第一个合法 JSON 对象或数组。"""

        candidate = response.strip().lstrip("\ufeff")
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", candidate, re.S | re.I)
        if fenced:
            candidate = fenced.group(1).strip()

        decoder = json.JSONDecoder()
        for index, char in enumerate(candidate):
            if char not in "[{":
                continue
            try:
                payload, _ = decoder.raw_decode(candidate[index:])
            except json.JSONDecodeError:
                continue
            return payload
        raise ValueError("盘古模型规划结果不是合法 JSON")

    @staticmethod
    def _input_record(task: AgentState):
        """从状态日志中提取规划阶段保存的原始输入记录。"""

        for item in task.log:
            try:
                record = json.loads(item)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(record, dict) and record.get("type") == "input":
                return record
        return None

    @staticmethod
    def _topic(input_record: dict) -> str:
        """从输入主题生成任务名称，不再把来源正文当作主题。"""

        context = str(input_record.get("context", "")).strip()
        if context:
            first_sentence = re.split(r"[。！？\n]", context, maxsplit=1)[0].strip()
            return first_sentence[:120] or "当前主题"

        url = str(input_record.get("url", "")).strip()
        path_name = unquote(urlparse(url).path.rstrip("/").split("/")[-1])
        if path_name:
            return path_name.replace("_", " ")
        return "当前主题"
