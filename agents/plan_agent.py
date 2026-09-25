from __future__ import annotations

import json
import re
from typing import Any, List, Optional

try:
    from config.structure import AgentState, ContextInput, add_message, record_event
except ModuleNotFoundError:  # Supports package execution from the parent folder.
    from ..config.structure import AgentState, ContextInput, add_message, record_event


class Plan_Agent:
    def __init__(self, model: Optional[Any] = None):
        self.model = model

    def Planning(self, data: ContextInput) -> AgentState:
        if not isinstance(data, ContextInput):
            raise TypeError("Plan_Agent.Planning 需要 ContextInput")
        if not data.context.strip():
            raise ValueError("调研主题不能为空")

        state = AgentState(
            retry_count=data.max_retries + 1,
            max_retries=data.max_retries,
            input_data=data,
        )
        record_event(
            state,
            "agent_start",
            agent="PlanAgent",
            context=data.context,
        )

        requested_tasks = data.metadata.get("sub_tasks") or data.metadata.get("subtasks")
        if requested_tasks:
            state.sub_task = [str(item).strip() for item in requested_tasks if str(item).strip()]
        return state

    def Split(self, task: AgentState) -> AgentState:
        """Ensure a research plan with at least three explicit sub-tasks."""

        topic = task.input_data.context if task.input_data else "该调研主题"
        if not task.sub_task and self.model is not None:
            task.sub_task = self._model_split(topic)
        if not task.sub_task:
            task.sub_task = [
                f"{topic}的基本概念、背景与发展过程",
                f"{topic}的核心方法、主要应用与实际价值",
                f"{topic}面临的问题、风险与未来发展趋势",
            ]

        defaults = [
            f"{topic}的研究背景与基本定义",
            f"{topic}的关键技术和应用场景",
            f"{topic}的局限性、风险和发展趋势",
        ]
        for fallback in defaults:
            if len(task.sub_task) >= 3:
                break
            task.sub_task.append(fallback)
        task.sub_task = list(dict.fromkeys(task.sub_task))
        task.overall_steps += 1
        task.current_agent = "RetrieveAgent"
        task.status = "Running"
        task.retry_count = task.max_retries + 1
        record_event(task, "plan_created", sub_tasks=task.sub_task)
        add_message(
            task,
            sender="PlanAgent",
            receiver="RetrieveAgent",
            message_type="task",
            payload={"context": topic, "sub_tasks": task.sub_task},
        )
        return task

    def _model_split(self, topic: str) -> List[str]:
        prompt = (
            "请把下面的调研主题拆分为至少三个相互独立的子任务。"
            "只返回 JSON，格式为 {\"sub_tasks\":[\"...\"]}。\n主题："
            f"{topic}"
        )
        response = self.model.generate(prompt)
        if not isinstance(response, str):
            return []

        candidate = response.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, re.S)
        if fenced:
            candidate = fenced.group(1)
        else:
            match = re.search(r"\{.*\}", candidate, re.S)
            if match:
                candidate = match.group(0)
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            return []
        tasks = payload.get("sub_tasks") if isinstance(payload, dict) else payload
        if not isinstance(tasks, list):
            return []
        return [str(item).strip() for item in tasks if str(item).strip()]
