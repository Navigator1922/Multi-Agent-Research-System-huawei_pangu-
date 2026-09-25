from typing import Any, Dict

try:
    from config.structure import ContextInput
except ModuleNotFoundError:
    from ..config.structure import ContextInput


def loader(data: Any) -> ContextInput:
    """将原始的三个输入字段转换为 ``ContextInput``。

    项目骨架只定义了一条上下文和一个来源。
    对额外输入字段直接拒绝，避免静默转换为另一种数据格式。
    """

    if isinstance(data, ContextInput):
        return data

    if not isinstance(data, dict):
        raise TypeError("输入必须是 ContextInput 或包含 context、source_id、url 的字典")

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
