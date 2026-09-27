"""Refresh complete, revision-pinned Wikipedia snapshots from the manifest.

Usage:
    python scripts/collect_wikipedia.py

The manifest already pins each page to a revision_id. The script fetches that
exact revision, stores the complete plaintext extract, and records a checksum.
It never truncates the extract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
MANIFEST_NAME = "wikipedia_manifest.json"
USER_AGENT = "openpangu-qa-data-refresh/1.0 (educational reproducible dataset)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args()

    data_dir = args.data_dir.resolve()
    manifest_path = data_dir / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("sources")
    if not isinstance(entries, list) or not entries:
        raise ValueError("manifest.sources 必须是非空数组")

    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    refreshed_entries = []
    for entry in entries:
        refreshed_entries.append(
            refresh_source(entry, data_dir=data_dir, retrieved_at=retrieved_at)
        )

    manifest["schema_version"] = 2
    manifest.pop("context_limit_characters", None)
    manifest["content_field"] = "context"
    manifest["content_policy"] = "complete revision-pinned plaintext extract; no truncation"
    manifest["retrieved_at"] = retrieved_at
    manifest["sources"] = refreshed_entries
    _write_json(manifest_path, manifest)
    print(f"Refreshed {len(refreshed_entries)} Wikipedia sources in {data_dir}")
    return 0


def refresh_source(entry: dict[str, Any], data_dir: Path, retrieved_at: str) -> dict[str, Any]:
    source_id = str(entry["source_id"])
    revision_id = int(entry["revision_id"])
    page = fetch_revision(revision_id)
    extract = page.get("extract")
    if not isinstance(extract, str) or not extract.strip():
        raise ValueError(f"Wikipedia extract is empty: {source_id}")

    revision = (page.get("revisions") or [{}])[0]
    fetched_revision = int(revision.get("revid", 0))
    if fetched_revision != revision_id:
        raise ValueError(
            f"Wikipedia revision changed for {source_id}: "
            f"expected {revision_id}, got {fetched_revision}"
        )

    url = str(page.get("fullurl") or entry["url"])
    if entry.get("page_id") and int(entry["page_id"]) != int(page["pageid"]):
        raise ValueError(
            f"Wikipedia page changed for {source_id}: "
            f"expected {entry['page_id']}, got {page['pageid']}"
        )
    if entry.get("url") and url != entry["url"]:
        raise ValueError(
            f"Wikipedia URL changed for {source_id}: "
            f"expected {entry['url']}, got {url}"
        )
    if entry.get("revision_timestamp") and str(entry["revision_timestamp"]) != str(
        revision["timestamp"]
    ):
        raise ValueError(
            f"Wikipedia revision timestamp changed for {source_id}: "
            f"expected {entry['revision_timestamp']}, got {revision['timestamp']}"
        )
    digest = hashlib.sha256(extract.encode("utf-8")).hexdigest()
    payload = {
        "source_id": source_id,
        "title": str(page.get("title") or entry.get("resolved_title", "")),
        "url": url,
        "api_url": build_api_url(revision_id),
        "page_id": int(page["pageid"]),
        "revision_id": fetched_revision,
        "revision_timestamp": str(revision["timestamp"]),
        "retrieved_at": retrieved_at,
        "content_sha256": digest,
        "context": extract,
        "license": entry.get(
            "license",
            "Wikipedia 内容依据 CC BY-SA 4.0 和 GFDL 发布，使用时请保留来源和许可说明。",
        ),
    }

    relative_file = Path(str(entry["file"]))
    target = (data_dir / relative_file).resolve()
    if data_dir not in target.parents:
        raise ValueError(f"来源文件路径越界：{relative_file}")
    _write_json(target, payload)

    refreshed = dict(entry)
    refreshed.update(
        {
            "resolved_title": payload["title"],
            "page_id": payload["page_id"],
            "revision_id": payload["revision_id"],
            "revision_timestamp": payload["revision_timestamp"],
            "url": payload["url"],
            "api_url": payload["api_url"],
            "retrieved_at": retrieved_at,
            "original_characters": len(extract),
            "stored_characters": len(extract),
            "truncated": False,
            "content_sha256": digest,
        }
    )
    return refreshed


def fetch_revision(revision_id: int) -> dict[str, Any]:
    params = {
        "action": "query",
        "prop": "extracts|info|revisions",
        "explaintext": "1",
        "exsectionformat": "plain",
        "variant": "zh-cn",
        "inprop": "url",
        "rvprop": "ids|timestamp",
        "revids": str(revision_id),
        "format": "json",
        "formatversion": "2",
    }
    url = "https://zh.wikipedia.org/w/api.php?" + urlencode(params)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60) as response:
        payload = json.load(response)

    if "error" in payload:
        raise RuntimeError(f"Wikipedia API error: {payload['error']}")
    pages = payload.get("query", {}).get("pages", [])
    if not pages:
        raise RuntimeError(f"Wikipedia returned no page for revision {revision_id}")
    return pages[0]


def build_api_url(revision_id: int) -> str:
    params = {
        "action": "query",
        "prop": "extracts|info|revisions",
        "explaintext": "1",
        "exsectionformat": "plain",
        "variant": "zh-cn",
        "inprop": "url",
        "rvprop": "ids|timestamp",
        "revids": str(revision_id),
        "format": "json",
        "formatversion": "2",
    }
    return "https://zh.wikipedia.org/w/api.php?" + urlencode(params)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"collect_wikipedia failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
