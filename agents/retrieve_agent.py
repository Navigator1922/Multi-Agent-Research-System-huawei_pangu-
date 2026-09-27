import json
from pathlib import Path

try:
    from config.structure import AgentState
    from utils.source_store import DEFAULT_DATA_DIR, SourceDataError, load_sources
except ModuleNotFoundError:
    from ..config.structure import AgentState
    from ..utils.source_store import DEFAULT_DATA_DIR, SourceDataError, load_sources

class Retrieve_Agent:
    def __init__(self, data_dir: str | Path = DEFAULT_DATA_DIR):
        self.data_dir = Path(data_dir)

    def retrieve(self,data:AgentState)->AgentState:
        if not isinstance(data, AgentState):
            raise TypeError("retrieve 需要 AgentState")
        if not data.sub_task:
            raise ValueError("没有可检索的子任务")

        data.overall_steps += 1
        input_record = self._input_record(data)
        if input_record is None:
            raise RuntimeError("检索缺少原始输入")

        source_ids = input_record.get("source_ids")
        if source_ids is None:
            source_id = str(input_record.get("source_id", "")).strip()
            source_ids = [source_id] if source_id else []
        if not isinstance(source_ids, list) or not source_ids:
            raise RuntimeError("检索来源为空：source_ids 为空")

        try:
            records = load_sources(source_ids, self.data_dir)
        except SourceDataError as exc:
            raise RuntimeError(f"检索来源校验失败：{exc}") from exc

        primary_source_id = str(input_record.get("source_id", "")).strip()
        input_url = str(input_record.get("url", "")).strip()
        if primary_source_id:
            primary = records.get(primary_source_id)
            if primary is None:
                raise RuntimeError(f"主来源不在 source_ids 中：{primary_source_id}")
            if input_url and input_url != primary.url:
                raise RuntimeError(f"输入 URL 与主来源不匹配：{primary_source_id}")

        data.source_metadata = {
            source_id: {
                "title": record.title,
                "url": record.url,
                "revision_id": record.revision_id,
                "content_sha256": record.content_sha256,
            }
            for source_id, record in records.items()
        }
        data.evidence = [
            {
                sub_task: {
                    source_id: record.context
                    for source_id, record in records.items()
                }
            }
            for sub_task in data.sub_task
        ]
        if not data.evidence:
            raise RuntimeError("检索结果为空")

        data.log.append(
            "RetrieveAgent: 已为 "
            f"{len(data.evidence)} 个子任务加载来源 {', '.join(records)}"
        )
        data.current_agent = "WriteAgent"
        data.retry_count = 2
        data.last_error = ""
        return data

    def retrieve_retry(self,data:AgentState)->AgentState:
        if not isinstance(data, AgentState):
            raise TypeError("retrieve_retry 需要 AgentState")
        data.log.append("RetrieveAgent: 执行重试")
        return self.retrieve(data)

    @staticmethod
    def _input_record(data: AgentState):
        """从 AgentState.log 中读取规划阶段保存的原始输入。

        检索 Agent 需要从这条记录中获取主题内容和来源编号，
        以便按照原始 evidence 格式生成检索证据。
        """

        for item in data.log:
            try:
                record = json.loads(item)
            except (TypeError, json.JSONDecodeError):
                # 非 JSON 日志只是过程说明，不是输入记录。
                continue
            if isinstance(record, dict) and record.get("type") == "input":
                return record
        return None
