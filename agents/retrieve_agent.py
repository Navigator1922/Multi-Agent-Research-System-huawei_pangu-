from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Set

try:
    from config.structure import AgentState, add_message, record_event
except ModuleNotFoundError:  # Supports package execution from the parent folder.
    from ..config.structure import AgentState, add_message, record_event


class Retrieve_Agent:
    def __init__(self, top_k: int = 2):
        self.top_k = max(1, int(top_k))

    def retrieve(self, data: AgentState) -> AgentState:
        if not isinstance(data, AgentState):
            raise TypeError("Retrieve_Agent.retrieve 需要 AgentState")
        if data.input_data is None:
            raise ValueError("AgentState 缺少 input_data")

        data.overall_steps += 1
        input_data = data.input_data
        record_event(
            data,
            "agent_start",
            agent="RetrieveAgent",
            attempt=data.max_retries + 2 - data.retry_count,
        )

        if input_data.force_retrieval_failure:
            message = "测试模式要求检索失败"
            record_event(data, "retrieval_empty", reason=message)
            add_message(
                data,
                sender="RetrieveAgent",
                receiver="RetrieveAgent",
                message_type="error",
                status="failed",
                error=message,
            )
            raise RuntimeError(message)

        if not input_data.sources:
            message = "资料库为空，无法完成检索"
            record_event(data, "retrieval_empty", reason=message)
            add_message(
                data,
                sender="RetrieveAgent",
                receiver="RetrieveAgent",
                message_type="error",
                status="failed",
                error=message,
            )
            raise RuntimeError(message)

        # Each retry recomputes the result so a future remote retriever can
        # replace or refresh its source set without changing the interface.
        data.evidence = []
        minimum_score = float(input_data.metadata.get("minimum_score", 0.0))
        for task_index, sub_task in enumerate(data.sub_task, 1):
            ranked = sorted(
                (
                    (self._score_source(input_data.context, sub_task, source), source)
                    for source in input_data.sources
                ),
                key=lambda item: item[0],
                reverse=True,
            )
            selected = [item for item in ranked if item[0] > minimum_score][: self.top_k]
            if not selected:
                message = f"子任务没有检索到有效证据: {sub_task}"
                record_event(
                    data,
                    "retrieval_empty",
                    task_id=f"subtask_{task_index:03d}",
                    reason=message,
                )
                add_message(
                    data,
                    sender="RetrieveAgent",
                    receiver="RetrieveAgent",
                    message_type="error",
                    task_id=f"subtask_{task_index:03d}",
                    status="failed",
                    error=message,
                )
                raise RuntimeError(message)

            for score, source in selected:
                evidence = self._to_evidence(
                    source,
                    score=score,
                    task_id=f"subtask_{task_index:03d}",
                    sub_task=sub_task,
                )
                data.evidence.append(evidence)

        data.current_agent = "WriteAgent"
        data.status = "Running"
        data.retry_count = data.max_retries + 1
        record_event(
            data,
            "retrieval_complete",
            evidence_count=len(data.evidence),
        )
        add_message(
            data,
            sender="RetrieveAgent",
            receiver="WriteAgent",
            message_type="result",
            payload={"evidence_count": len(data.evidence)},
            evidence=data.evidence,
        )
        return data

    def retrieve_retry(self, data: AgentState) -> AgentState:
        record_event(data, "retrieval_retry", retry_number=data.total_retries + 1)
        return self.retrieve(data)

    @staticmethod
    def _tokens(text: str) -> Set[str]:
        # Character-level Chinese tokens plus word-level Latin tokens keep
        # this implementation dependency-free while handling mixed text.
        return set(re.findall(r"[\u4e00-\u9fff]|[a-zA-Z0-9]+", text.lower()))

    def _score_source(self, topic: str, sub_task: str, source: Dict[str, Any]) -> float:
        source_text = " ".join(
            str(source.get(key) or "")
            for key in ("title", "quote", "content", "text", "keywords")
        )
        query_tokens = self._tokens(f"{topic} {sub_task}")
        source_tokens = self._tokens(source_text)
        if not query_tokens or not source_tokens:
            return 0.0
        overlap = len(query_tokens & source_tokens)
        return round(overlap / len(query_tokens), 6)

    @staticmethod
    def _to_evidence(
        source: Dict[str, Any],
        score: float,
        task_id: str,
        sub_task: str,
    ) -> Dict[str, Any]:
        quote = str(source.get("quote") or source.get("content") or source.get("text") or "")
        return {
            "task_id": task_id,
            "sub_task": sub_task,
            "source_id": str(source.get("source_id") or "unknown"),
            "title": str(source.get("title") or "未命名资料"),
            "url": str(source.get("url") or ""),
            "quote": quote[:1000],
            "score": score,
        }
