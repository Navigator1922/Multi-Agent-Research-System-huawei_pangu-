"""Load and validate the offline source snapshots used by the pipeline."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
MANIFEST_NAME = "wikipedia_manifest.json"


class SourceDataError(ValueError):
    """Raised when a source snapshot cannot be trusted."""


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    title: str
    url: str
    api_url: str
    page_id: int
    revision_id: int
    revision_timestamp: str
    retrieved_at: str
    context: str
    content_sha256: str


def load_manifest(data_dir: str | Path = DEFAULT_DATA_DIR) -> dict[str, Any]:
    """Read the manifest and require the fields needed for provenance checks."""

    path = Path(data_dir) / MANIFEST_NAME
    if not path.is_file():
        raise SourceDataError(f"来源清单不存在：{path}")

    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SourceDataError(f"来源清单格式错误：{path}") from exc

    if not isinstance(manifest, dict) or not isinstance(manifest.get("sources"), list):
        raise SourceDataError("来源清单必须包含 sources 数组")
    if manifest.get("schema_version") != 2:
        raise SourceDataError("来源清单 schema_version 必须为 2")
    return manifest


def load_sources(
    source_ids: Iterable[str],
    data_dir: str | Path = DEFAULT_DATA_DIR,
) -> dict[str, SourceRecord]:
    """Load requested snapshots and verify them against the manifest.

    The function deliberately fails closed: a missing source, a mismatched URL or
    revision, an unexpected character count, or a changed checksum is not silently
    accepted as evidence.
    """

    normalized_ids = _normalize_ids(source_ids)
    if not normalized_ids:
        raise SourceDataError("没有指定来源 ID")

    data_path = Path(data_dir).resolve()
    manifest = load_manifest(data_path)
    entries = {
        str(entry.get("source_id", "")): entry
        for entry in manifest["sources"]
        if isinstance(entry, dict)
    }
    if len(entries) != len(manifest["sources"]):
        raise SourceDataError("来源清单包含重复或无效 source_id")

    records: dict[str, SourceRecord] = {}
    for source_id in normalized_ids:
        entry = entries.get(source_id)
        if entry is None:
            raise SourceDataError(f"来源清单中不存在 source_id：{source_id}")

        relative_file = entry.get("file")
        source_path = _safe_source_path(data_path, relative_file)
        if not source_path.is_file():
            raise SourceDataError(f"来源文件不存在：{relative_file}")

        try:
            payload = json.loads(source_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SourceDataError(f"来源文件格式错误：{source_path}") from exc

        record = _validate_record(payload, entry, source_path)
        records[source_id] = record

    return records


def _normalize_ids(source_ids: Iterable[str]) -> list[str]:
    if isinstance(source_ids, (str, bytes)):
        raise SourceDataError("source_ids 必须是字符串数组")
    result: list[str] = []
    for source_id in source_ids:
        if not isinstance(source_id, str) or not source_id.strip():
            raise SourceDataError("source_ids 中只能包含非空字符串")
        normalized = source_id.strip()
        if normalized not in result:
            result.append(normalized)
    return result


def _safe_source_path(data_dir: Path, relative_file: Any) -> Path:
    if not isinstance(relative_file, str) or not relative_file.strip():
        raise SourceDataError("来源清单中的 file 必须是非空字符串")
    candidate = (data_dir / relative_file).resolve()
    if data_dir != candidate and data_dir not in candidate.parents:
        raise SourceDataError(f"来源文件路径越界：{relative_file}")
    return candidate


def _validate_record(
    payload: Any,
    entry: dict[str, Any],
    source_path: Path,
) -> SourceRecord:
    if not isinstance(payload, dict):
        raise SourceDataError(f"来源文件顶层必须是对象：{source_path}")

    source_id = str(entry.get("source_id", "")).strip()
    context = payload.get("context")
    if payload.get("source_id") != source_id:
        raise SourceDataError(f"source_id 不匹配：{source_path}")
    if not isinstance(context, str) or not context.strip():
        raise SourceDataError(f"来源正文为空：{source_path}")
    if payload.get("url") != entry.get("url"):
        raise SourceDataError(f"URL 不匹配：{source_path}")
    if payload.get("revision_id") != entry.get("revision_id"):
        raise SourceDataError(f"revision_id 不匹配：{source_path}")
    for field in ("title", "page_id", "revision_timestamp"):
        if payload.get(field) != entry.get(
            "resolved_title" if field == "title" else field
        ):
            raise SourceDataError(f"{field} 不匹配：{source_path}")
    if entry.get("truncated") is not False:
        raise SourceDataError(f"来源仍被标记为截断：{source_id}")
    if entry.get("stored_characters") != len(context):
        raise SourceDataError(f"来源字符数与清单不匹配：{source_id}")

    digest = hashlib.sha256(context.encode("utf-8")).hexdigest()
    expected_digest = entry.get("content_sha256")
    if payload.get("content_sha256") != digest or expected_digest != digest:
        raise SourceDataError(f"来源正文校验和不匹配：{source_id}")

    required = (
        "title",
        "api_url",
        "page_id",
        "revision_timestamp",
        "retrieved_at",
    )
    missing = [name for name in required if not payload.get(name)]
    if missing:
        raise SourceDataError(
            f"来源文件缺少元数据 {', '.join(missing)}：{source_path}"
        )

    return SourceRecord(
        source_id=source_id,
        title=str(payload["title"]),
        url=str(payload["url"]),
        api_url=str(payload["api_url"]),
        page_id=int(payload["page_id"]),
        revision_id=int(payload["revision_id"]),
        revision_timestamp=str(payload["revision_timestamp"]),
        retrieved_at=str(payload["retrieved_at"]),
        context=context,
        content_sha256=digest,
    )


__all__ = [
    "DEFAULT_DATA_DIR",
    "SourceDataError",
    "SourceRecord",
    "load_manifest",
    "load_sources",
]
