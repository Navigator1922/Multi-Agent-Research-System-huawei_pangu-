import json

try:
    from config.structure import AgentState
except ModuleNotFoundError:
    from ..config.structure import AgentState

class Retrieve_Agent:
    def __init__(self):
        pass

    def retrieve(self,data:AgentState)->AgentState:
        if not isinstance(data, AgentState):
            raise TypeError("retrieve 需要 AgentState")
        if not data.sub_task:
            raise ValueError("没有可检索的子任务")

        data.overall_steps += 1
        input_record = self._input_record(data)
        if input_record is None:
            raise RuntimeError("检索缺少原始输入")

        context = str(input_record.get("context", "")).strip()
        source_id = str(input_record.get("source_id", "")).strip()
        if not context:
            raise RuntimeError("检索结果为空：context 为空")
        if not source_id:
            raise RuntimeError("检索结果为空：source_id 为空")

        # 原始输入只包含一个来源，因此保留骨架定义的证据格式，
        # 不额外引入来源集合字段。
        data.evidence = [
            {sub_task: {source_id: context}}
            for sub_task in data.sub_task
        ]
        if not data.evidence:
            raise RuntimeError("检索结果为空")

        data.log.append(
            f"RetrieveAgent: 已为 {len(data.evidence)} 个子任务保留来源 {source_id}"
        )
        data.current_agent = "WriteAgent"
        data.retry_count = 2
        return data

    def retrieve_retry(self,data:AgentState)->AgentState:
        if not isinstance(data, AgentState):
            raise TypeError("retrieve_retry 需要 AgentState")
        data.log.append("RetrieveAgent: 执行重试")
        return self.retrieve(data)

    @staticmethod
    def _input_record(data: AgentState):
        for item in data.log:
            try:
                record = json.loads(item)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(record, dict) and record.get("type") == "input":
                return record
        return None
