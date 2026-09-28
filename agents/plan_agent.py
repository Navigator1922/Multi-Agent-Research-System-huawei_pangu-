try:
    from config.structure import ContextInput, AgentState
except ModuleNotFoundError:
    from ..config.structure import ContextInput, AgentState


class Plan_Agent:
    """负责把原始调研输入拆分成可执行的子任务。"""

    def __init__(self, model):
        self.model = model

    def Split(self, task: AgentState) -> AgentState:
        import json

        if not isinstance(task, AgentState):
            raise TypeError("Split 需要 AgentState")
        if task.status != "Running":
            raise RuntimeError(f"无法在状态 {task.status} 下规划子任务")

        topic = ""
        for item in task.log:
            try:
                record = json.loads(item)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(record, dict) and record.get("type") == "input":
                topic = str(record.get("topic", "")).strip()
                break
        if not topic:
            raise ValueError("规划缺少有效 topic")

        task.overall_steps += 1
        if self.model is None:
            # 无模型模式虽然是确定性的，但仍然使用与模型响应相同的严格数据结构。
            payload = {
                "sub_task": [
                    f"{topic}的背景、基本概念与关键组成",
                    f"{topic}的主要技术、应用场景与实际影响",
                    f"{topic}的风险、限制、治理措施与发展趋势",
                ]
            }
        else:
            prompt = (
                "你是多智能体调研系统的规划 Agent。请仅根据下面的主题进行无文本摘要的盲写规划，"
                "拆分出至少三个互不重复、可由资料证据回答的具体子任务。"
                "只允许输出一个合法 JSON 对象，不得输出解释、Markdown 或代码围栏。"
                '严格格式：{"sub_task":["子任务1","子任务2","子任务3"]}\n'
                f"主题：{topic}"
            )
            response = self.model.generate(prompt)
            if not isinstance(response, str) or not response.strip():
                raise ValueError("规划模型返回为空")
            try:
                payload = json.loads(response.strip().lstrip("\ufeff"))
            except json.JSONDecodeError as exc:
                raise ValueError("规划模型返回的 JSON 无法解析") from exc

        if not isinstance(payload, dict) or set(payload) != {"sub_task"}:
            raise ValueError("规划结果必须是只包含 sub_task 字段的 JSON 对象")
        tasks = payload["sub_task"]
        if not isinstance(tasks, list) or len(tasks) < 3:
            raise ValueError("规划结果的 sub_task 必须至少包含三个任务")
        if any(not isinstance(item, str) or not item.strip() for item in tasks):
            raise ValueError("规划结果中的每个 sub_task 都必须是非空字符串")
        normalized = [item.strip() for item in tasks]
        if len(set(normalized)) != len(normalized):
            raise ValueError("规划结果中的 sub_task 不能重复")

        task.sub_task = normalized
        task.current_agent = "RetrieveAgent"
        task.retry_count = 2
        task.log.append(
            json.dumps(
                {"type": "sub_tasks", "items": task.sub_task},
                ensure_ascii=False,
            )
        )
        return task

    def Programme(self, data: ContextInput) -> AgentState:
        import json

        if not isinstance(data, ContextInput):
            raise TypeError("Programme 需要 ContextInput")
        values = {
            "topic": data.topic,
            "db_collection_id": data.db_collection_id,
            "source_id": data.source_id,
            "url": data.url,
        }
        if any(not isinstance(value, str) or not value.strip() for value in values.values()):
            raise ValueError("ContextInput 的所有字段都必须是非空字符串")

        state = AgentState(
            current_agent="PlanAgent",
            db_collection_id=data.db_collection_id.strip(),
        )
        state.log.append(json.dumps({"type": "input", **values}, ensure_ascii=False))
        state.log.append("PlanAgent: 已接收调研主题，等待生成子任务")
        return state
