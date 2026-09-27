import json
from pathlib import Path
from typing import Any, Dict

try:
    from config.structure import ContextInput
except ModuleNotFoundError:
    from ..config.structure import ContextInput


def loader(data: Any) -> ContextInput:
    """检查并转换输入数据，统一返回一个 ``ContextInput`` 对象。

    输入可以是 ``ContextInput``、包含 ``context``、``source_id``、``url``
    和可选 ``source_ids`` 的字典，也可以是保存了这个字典的本地 JSON
    文件路径。``context`` 是研究主题，不是来源正文；来源正文由检索
    Agent 根据 source_ids 从本地快照加载。
    """

    if isinstance(data, ContextInput):
        return data

    if isinstance(data, (str, Path)):
        data = _load_json_file(data)

    if not isinstance(data, dict):
        raise TypeError(
            "输入必须是 ContextInput、JSON 文件路径或包含 "
            "context、source_id、url 的字典"
        )

    required = ("context", "source_id", "url")
    missing = [name for name in required if name not in data]
    if missing:
        raise ValueError("输入缺少字段: " + ", ".join(missing))

    values: Dict[str, Any] = {name: data[name] for name in required}
    for name, value in values.items():
        if not isinstance(value, str):
            raise TypeError(f"字段 {name} 必须是字符串")

    if not values["context"].strip():
        raise ValueError("context 不能为空")

    raw_source_ids = data.get("source_ids")
    if raw_source_ids is None:
        source_ids = [values["source_id"].strip()] if values["source_id"].strip() else []
    elif not isinstance(raw_source_ids, list):
        raise TypeError("字段 source_ids 必须是字符串数组")
    else:
        source_ids = []
        for source_id in raw_source_ids:
            if not isinstance(source_id, str) or not source_id.strip():
                raise TypeError("字段 source_ids 只能包含非空字符串")
            normalized = source_id.strip()
            if normalized not in source_ids:
                source_ids.append(normalized)

    primary_source_id = values["source_id"].strip()
    if primary_source_id and primary_source_id not in source_ids:
        raise ValueError("source_id 必须包含在 source_ids 中")

    return ContextInput(
        context=values["context"],
        source_id=values["source_id"],
        url=values["url"],
        source_ids=source_ids,
    )


def _load_json_file(file_path: str | Path) -> Dict[str, Any]:
    """读取本地 JSON 文件，并返回其中的顶层字典。

    JSON 文件应直接保存一个对象，例如：
    ``{"context": "主题", "source_id": "来源1", "url": "链接"}``。
    文件不存在、格式错误或顶层不是对象时，给出明确的错误信息。
    """

    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"JSON 输入文件不存在：{path}")

    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 输入文件格式错误：{path}") from exc

    if not isinstance(payload, dict):
        raise ValueError("JSON 输入文件的顶层结构必须是对象，不能是数组或字符串")

    return payload
