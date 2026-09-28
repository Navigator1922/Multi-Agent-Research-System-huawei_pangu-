"""通过 ChromaDB 执行密集向量检索并组装多模态证据。"""

from __future__ import annotations

import json
import os
from pathlib import Path

from config.structure import AgentState, DataBlock


_DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
_ALLOWED_BLOCK_TYPES = {"text", "image", "table"}


class Retrieve_Agent:
    """连接 Loader 创建的 Chroma 集合并执行 Dense Retrieval。"""

    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.chroma_path = Path("./chroma_db").resolve()
        model_name = (
            os.getenv("CHROMA_EMBEDDING_MODEL", _DEFAULT_EMBEDDING_MODEL).strip()
            or _DEFAULT_EMBEDDING_MODEL
        )
        try:
            import chromadb
            from chromadb.utils import embedding_functions

            self.client = chromadb.PersistentClient(path=str(self.chroma_path))
            self.embedding_function = (
                embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name=model_name
                )
            )
        except Exception as exc:
            raise RuntimeError(
                f"ChromaDB 或中文嵌入模型初始化失败：{self.chroma_path}"
            ) from exc

    def retrieve(self, data: AgentState) -> AgentState:
        """针对每个子任务从指定 Chroma 集合召回最多五个证据块。"""

        if not isinstance(data, AgentState):
            raise TypeError("retrieve 需要 AgentState")
        if data.status != "Running":
            raise RuntimeError(f"无法在状态 {data.status} 下检索")
        if not data.db_collection_id.strip():
            raise ValueError("AgentState.db_collection_id 不能为空")
        if not data.sub_task:
            raise ValueError("没有可检索的 sub_task")

        try:
            collection = self.client.get_collection(
                name=data.db_collection_id,
                embedding_function=self.embedding_function,
            )
        except Exception as exc:
            raise RuntimeError(
                f"无法获取 Chroma 集合：{data.db_collection_id}"
            ) from exc

        evidence = []
        retrieval_log = []
        for sub_task in data.sub_task:
            try:
                result = collection.query(
                    query_texts=[sub_task],
                    n_results=5,
                    include=["documents", "metadatas", "distances"],
                )
            except Exception as exc:
                raise RuntimeError(f"向量检索失败：{sub_task}") from exc

            source_blocks, result_count = self._to_data_blocks(
                result=result,
                sub_task=sub_task,
            )
            if result_count == 0 or not source_blocks:
                raise ValueError(f"子任务没有召回有效证据：{sub_task}")

            evidence.append({sub_task: source_blocks})
            retrieval_log.append(
                {
                    "sub_task": sub_task,
                    "result_count": result_count,
                    "source_ids": sorted(source_blocks),
                }
            )

        data.evidence = evidence
        data.overall_steps += 1
        data.current_agent = "RetrieveAgent"
        data.log.append(
            json.dumps(
                {
                    "type": "dense_retrieval",
                    "collection": data.db_collection_id,
                    "results": retrieval_log,
                },
                ensure_ascii=False,
            )
        )
        return data

    def web_search(self, data: AgentState) -> AgentState:
        """完成检索阶段并将状态转交给写作 Agent。"""

        if not isinstance(data, AgentState):
            raise TypeError("web_search 需要 AgentState")
        if data.status != "Running":
            raise RuntimeError(f"无法在状态 {data.status} 下结束检索")
        if not data.evidence or len(data.evidence) != len(data.sub_task):
            raise RuntimeError("向量检索未生成完整 evidence")

        data.overall_steps += 1
        data.current_agent = "WriteAgent"
        data.retry_count = 2
        data.log.append("RetrieveAgent: Dense Retrieval 已完成，进入 WriteAgent")
        return data

    @staticmethod
    def _to_data_blocks(result, sub_task: str):
        """把 Chroma query 的 documents、metadatas、distances 转为 DataBlock。"""

        if not isinstance(result, dict):
            raise TypeError("Chroma query 返回值必须是字典")
        documents = result.get("documents")
        metadatas = result.get("metadatas")
        distances = result.get("distances")
        if not isinstance(documents, list) or not documents:
            raise ValueError(f"Chroma query 没有返回 documents：{sub_task}")
        if not isinstance(metadatas, list) or not metadatas:
            raise ValueError(f"Chroma query 没有返回 metadatas：{sub_task}")

        query_documents = documents[0]
        query_metadatas = metadatas[0]
        query_distances = distances[0] if isinstance(distances, list) and distances else []
        if not isinstance(query_documents, list) or not isinstance(query_metadatas, list):
            raise TypeError("Chroma query 的 documents/metadatas 层级格式错误")
        if len(query_documents) != len(query_metadatas):
            raise ValueError("Chroma query 的 documents 与 metadatas 数量不一致")

        source_blocks = {}
        result_count = 0
        for index, (document, raw_metadata) in enumerate(
            zip(query_documents, query_metadatas)
        ):
            if not isinstance(document, str) or not document.strip():
                raise ValueError(f"Chroma query 返回空文档：{sub_task}#{index}")
            if not isinstance(raw_metadata, dict):
                raise TypeError(f"Chroma query 返回非法 metadata：{sub_task}#{index}")

            metadata = dict(raw_metadata)
            source_id = metadata.get("source_id")
            block_type = metadata.get("type", "text")
            if not isinstance(source_id, str) or not source_id.strip():
                raise ValueError(f"召回块缺少 source_id：{sub_task}#{index}")
            if block_type not in _ALLOWED_BLOCK_TYPES:
                raise ValueError(f"召回块包含未知类型：{block_type}")
            if index < len(query_distances) and query_distances[index] is not None:
                metadata["distance"] = float(query_distances[index])
            metadata["retrieval_query"] = sub_task
            metadata["retrieval_rank"] = index + 1

            block = DataBlock(
                type=block_type,
                content=document,
                metadata=metadata,
            )
            source_blocks.setdefault(source_id, []).append(block)
            result_count += 1

        return source_blocks, result_count
