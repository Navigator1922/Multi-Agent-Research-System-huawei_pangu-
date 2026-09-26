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
    三个字段的字典，也可以是保存了这个字典的本地 JSON 文件路径。
    项目骨架只定义了一条上下文和一个来源，对缺少字段或类型不正确的
    输入直接报错。
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

    return ContextInput(
        context=values["context"],
        source_id=values["source_id"],
        url=values["url"],
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
