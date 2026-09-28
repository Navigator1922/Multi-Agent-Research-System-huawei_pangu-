from typing import Any

try:
    from config.structure import ContextInput
except ModuleNotFoundError:
    from ..config.structure import ContextInput


def loader(data: Any):
    """Validate an input record and convert it to the locked input contract."""

    import json
    from pathlib import Path

    if isinstance(data, ContextInput):
        payload = {
            "topic": data.topic,
            "db_collection_id": data.db_collection_id,
            "source_id": data.source_id,
            "url": data.url,
        }
    else:
        if isinstance(data, (str, Path)):
            input_path = Path(data)
            if not input_path.is_file():
                raise FileNotFoundError(f"输入文件不存在：{input_path}")
            try:
                payload = json.loads(input_path.read_text(encoding="utf-8"))
            except UnicodeDecodeError as exc:
                raise ValueError(f"输入文件必须使用 UTF-8 编码：{input_path}") from exc
            except json.JSONDecodeError as exc:
                raise ValueError(f"输入文件不是合法 JSON：{input_path}") from exc
        elif isinstance(data, dict):
            payload = data
        else:
            raise TypeError("loader 只接受 ContextInput、字典或 JSON 文件路径")

    if not isinstance(payload, dict):
        raise ValueError("输入数据顶层必须是对象")

    # ``context`` is accepted only as a compatibility alias for older input
    # files; the returned object always uses the current ``topic`` field.
    topic = payload.get("topic", payload.get("context"))
    collection_id = payload.get(
        "db_collection_id", payload.get("collection_id")
    )
    source_id = payload.get("source_id")
    url = payload.get("url")
    fields = {
        "topic": topic,
        "db_collection_id": collection_id,
        "source_id": source_id,
        "url": url,
    }
    missing = [name for name, value in fields.items() if value is None]
    if missing:
        raise ValueError(f"输入缺少必填字段：{', '.join(missing)}")
    invalid = [name for name, value in fields.items() if not isinstance(value, str)]
    if invalid:
        raise TypeError(f"输入字段必须是字符串：{', '.join(invalid)}")
    normalized = {name: value.strip() for name, value in fields.items()}
    empty = [name for name, value in normalized.items() if not value]
    if empty:
        raise ValueError(f"输入字段不能为空：{', '.join(empty)}")

    return ContextInput(**normalized)
