import json

try:
    from config.structure import ContextInput, AgentState
except ModuleNotFoundError:
    from ..config.structure import ContextInput, AgentState

class Plan_Agent:
    def __init__(self):
        pass

    def Planning(self,data:ContextInput)->AgentState:
        if not isinstance(data, ContextInput):
            raise TypeError("Planning 需要 ContextInput")
        if not data.context.strip():
            raise ValueError("context 不能为空")

        state = AgentState()
        state.overall_steps += 1
        state.log.append(
            json.dumps(
                {
                    "type": "input",
                    "context": data.context,
                    "source_id": data.source_id,
                    "url": data.url,
                },
                ensure_ascii=False,
            )
        )
        state.log.append("PlanAgent: 已接收调研主题")
        return self.Split(state)

    def Split(self,task:AgentState)->AgentState:
        if not isinstance(task, AgentState):
            raise TypeError("Split 需要 AgentState")

        input_record = self._input_record(task)
        topic = input_record["context"] if input_record else "当前主题"
        default_tasks = [
            f"研究{topic}的背景与基本概念",
            f"分析{topic}的主要特点、应用与影响",
            f"总结{topic}存在的问题、风险与发展方向",
        ]

        selected = [item.strip() for item in task.sub_task if item.strip()]
        for item in default_tasks:
            if len(selected) >= 3:
                break
            if item not in selected:
                selected.append(item)
        task.sub_task = selected
        task.current_agent = "RetrieveAgent"
        task.retry_count = 2
        task.log.append(f"PlanAgent: 已拆分 {len(task.sub_task)} 个子任务")
        return task

    @staticmethod
    def _input_record(task: AgentState):
        """从状态日志中提取规划阶段保存的原始输入记录。

        规划阶段没有新增状态字段，而是把输入保存为日志中的 JSON 字符串。
        找到后返回字典；找不到时返回 ``None``。
        """

        for item in task.log:
            try:
                record = json.loads(item)
            except (TypeError, json.JSONDecodeError):
                # 普通文本日志不能作为输入记录，继续检查下一条。
                continue
            if isinstance(record, dict) and record.get("type") == "input":
                return record
        return None
