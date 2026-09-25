from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Union

try:
    from config.structure import ContextInput
except ModuleNotFoundError:  # Supports `python -m openpangu_qa.main`.
    from ..config.structure import ContextInput


def _read_sources(path_value: Union[str, Path]) -> List[Dict[str, Any]]:
    path = Path(path_value)
    if not path.exists():
        raise FileNotFoundError(f"资料文件不存在: {path}")

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if isinstance(payload, dict):
        payload = payload.get("sources", [payload])
    if not isinstance(payload, list):
        raise ValueError("资料文件必须是 JSON 数组，或包含 sources 数组的 JSON 对象")
    return [_normalize_source(item, index) for index, item in enumerate(payload, 1)]


def _normalize_source(item: Any, index: int) -> Dict[str, Any]:
    if isinstance(item, str):
        return {
            "source_id": f"source_{index:03d}",
            "title": f"本地资料 {index}",
            "url": "",
            "quote": item,
        }
    if not isinstance(item, dict):
        raise ValueError(f"第 {index} 条资料必须是字符串或对象")

    source = dict(item)
    source.setdefault("source_id", f"source_{index:03d}")
    source.setdefault("title", source["source_id"])
    source.setdefault("url", "")
    if not any(source.get(key) for key in ("quote", "content", "text")):
        raise ValueError(f"资料 {source['source_id']} 缺少 quote、content 或 text")
    if not source.get("quote"):
        source["quote"] = source.get("content") or source.get("text")
    return source


def _default_source(context: str, source_id: str, url: str) -> Dict[str, Any]:
    return {
        "source_id": source_id or "input",
        "title": "用户输入资料",
        "url": url,
        "quote": context,
        "content": context,
    }


def loader(data: Any) -> ContextInput:
    """Normalize strings, dictionaries, files, and ContextInput objects.

    A dictionary is the recommended form for experiments. Example::

        {
            "context": "人工智能在教育中的应用",
            "sources": [{"source_id": "s1", "quote": "...", "url": "..."}],
            "log_path": "logs/normal.jsonl"
        }
    """

    if isinstance(data, ContextInput):
        return data

    if isinstance(data, (str, Path)):
        context = str(data).strip()
        if not context:
            raise ValueError("调研主题不能为空")
        return ContextInput(
            context=context,
            sources=[_default_source(context, "input", "")],
        )

    if not isinstance(data, dict):
        raise TypeError("输入必须是字符串、字典或 ContextInput")

    context = str(
        data.get("context")
        or data.get("topic")
        or data.get("query")
        or ""
    ).strip()
    if not context:
        raise ValueError("输入缺少 context/topic/query")

    sources_value = data.get("sources")
    if data.get("sources_path"):
        sources = _read_sources(data["sources_path"])
    elif sources_value is None:
        sources = []
    elif isinstance(sources_value, Iterable) and not isinstance(sources_value, (str, bytes, dict)):
        sources = [_normalize_source(item, index) for index, item in enumerate(sources_value, 1)]
    else:
        raise ValueError("sources 必须是数组，sources_path 必须指向 JSON 文件")

    force_failure = bool(data.get("force_retrieval_failure", False))
    if not sources and not force_failure:
        sources = [
            _default_source(
                context,
                str(data.get("source_id") or "input"),
                str(data.get("url") or ""),
            )
        ]

    max_retries = int(data.get("max_retries", 2))
    if max_retries < 0:
        raise ValueError("max_retries 不能小于 0")

    timeout_seconds = float(data.get("timeout_seconds", 30.0))
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds 必须大于 0")

    reserved = {
        "context",
        "topic",
        "query",
        "sources",
        "sources_path",
        "source_id",
        "url",
        "force_retrieval_failure",
        "timeout_seconds",
        "max_retries",
        "log_path",
    }
    metadata = dict(data.get("metadata") or {})
    metadata.update({key: value for key, value in data.items() if key not in reserved})

    return ContextInput(
        context=context,
        source_id=str(data.get("source_id") or "input"),
        url=str(data.get("url") or ""),
        sources=sources,
        force_retrieval_failure=force_failure,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        log_path=str(data["log_path"]) if data.get("log_path") else None,
        metadata=metadata,
    )
