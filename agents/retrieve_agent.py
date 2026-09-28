import hashlib
import json
import re
from pathlib import Path

try:
    from config.structure import AgentState,DataBlock
except ModuleNotFoundError:
    from ..config.structure import AgentState,DataBlock

class Retrieve_Agent:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)

    def retrieve(self,data:AgentState)->AgentState:
        if not isinstance(data, AgentState):
            raise TypeError("retrieve 需要 AgentState")
        if data.status != "Running":
            raise RuntimeError(f"无法在状态 {data.status} 下检索")
        if not data.db_collection_id.strip():
            raise ValueError("AgentState.db_collection_id 不能为空")
        if not data.sub_task:
            raise ValueError("没有可检索的 sub_task")

        root = Path(self.data_dir)
        if not root.exists():
            raise FileNotFoundError(f"本地检索目录不存在：{root}")
        if not root.is_dir():
            raise NotADirectoryError(f"本地检索路径不是目录：{root}")

        # 接受不依赖第三方库的简易集合格式；集合可以是包含文档、记录、分块或来源的 JSON/JSONL 文件。
        paths = sorted(
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in {".json", ".jsonl"}
        )
        if not paths:
            raise RuntimeError(f"本地检索目录没有 JSON 或 JSONL 文档：{root}")

        documents = []

        def add_record(record, path, position, inherited_collection=""):
            if isinstance(record, list):
                for index, child in enumerate(record):
                    add_record(child, path, f"{position}.{index}", inherited_collection)
                return
            if not isinstance(record, dict):
                raise ValueError(f"本地文档 {path} 的记录必须是对象")

            collection = str(
                record.get(
                    "db_collection_id",
                    record.get("collection_id", inherited_collection),
                )
                or ""
            ).strip()
            if collection and collection != data.db_collection_id:
                return

            nested_keys = ("documents", "records", "chunks", "sources", "items")
            has_content = any(
                key in record
                for key in ("content", "text", "context", "body", "image", "image_url", "table")
            )
            if not has_content:
                nested = False
                for key in nested_keys:
                    value = record.get(key)
                    if isinstance(value, list):
                        nested = True
                        for index, child in enumerate(value):
                            add_record(child, path, f"{position}.{key}.{index}", collection)
                if nested:
                    return

            metadata = record.get("metadata", {})
            if metadata is None:
                metadata = {}
            if not isinstance(metadata, dict):
                raise ValueError(f"本地文档 {path} 的 metadata 必须是对象")
            metadata = dict(metadata)
            source_id = str(
                record.get("source_id", metadata.get("source_id", record.get("id", "")))
                or ""
            ).strip()
            if not source_id:
                source_id = f"{path.stem}:{position}"

            def as_text(value, field_name):
                if value is None:
                    return ""
                if isinstance(value, str):
                    return value.strip()
                if isinstance(value, (dict, list)):
                    return json.dumps(value, ensure_ascii=False)
                raise TypeError(f"本地文档 {path} 的 {field_name} 必须是字符串或结构化值")

            blocks = []
            explicit_type = str(record.get("type", "")).strip().lower()
            text_value = record.get("content", record.get("text", record.get("context", record.get("body"))))
            if explicit_type in {"text", "image", "table"} and text_value is not None:
                blocks.append((explicit_type, as_text(text_value, "content")))
            else:
                text_content = as_text(text_value, "content")
                if text_content:
                    blocks.append(("text", text_content))

            image_values = record.get("images", [])
            if image_values is None:
                image_values = []
            if isinstance(image_values, (str, dict)):
                image_values = [image_values]
            if not isinstance(image_values, list):
                raise TypeError(f"本地文档 {path} 的 images 必须是数组")
            if record.get("image") is not None:
                image_values.append(record.get("image"))
            if record.get("image_url") is not None:
                image_values.append(record.get("image_url"))
            for image in image_values:
                if isinstance(image, dict):
                    image_content = image.get("url", image.get("content"))
                    if image_content is None:
                        raise ValueError(f"本地文档 {path} 的图片缺少 url/content")
                    image_content = as_text(image_content, "image")
                    image_metadata = image.get("metadata", {})
                    if image_metadata is not None and not isinstance(image_metadata, dict):
                        raise ValueError(f"本地文档 {path} 的图片 metadata 必须是对象")
                    blocks.append(("image", image_content, dict(image_metadata or {})))
                else:
                    blocks.append(("image", as_text(image, "image")))

            table_values = record.get("tables", [])
            if table_values is None:
                table_values = []
            if isinstance(table_values, (str, dict, list)) and not (
                isinstance(table_values, list) and all(isinstance(item, (str, dict, list)) for item in table_values)
            ):
                table_values = [table_values]
            if record.get("table") is not None:
                table_values.append(record.get("table"))
            if record.get("table_markdown") is not None:
                table_values.append(record.get("table_markdown"))
            if record.get("csv") is not None:
                table_values.append(record.get("csv"))
            for table in table_values:
                blocks.append(("table", as_text(table, "table")))

            if not blocks:
                # 清单或索引条目可能与真实文档并列存在；它只是来源元数据，不是证据本身。
                if any(
                    key in record
                    for key in ("file", "revision_id", "stored_characters", "truncated")
                ):
                    return
                raise ValueError(f"本地文档 {path} 不包含可用 DataBlock")
            if any(not content for _, content, *rest in blocks):
                raise ValueError(f"本地文档 {path} 包含空内容记录")
            standard_metadata = dict(metadata)
            standard_metadata.setdefault("source_id", source_id)
            standard_metadata.setdefault("db_collection_id", data.db_collection_id)
            for key in ("title", "url", "page", "section", "content_sha256"):
                if key in record:
                    standard_metadata.setdefault(key, record[key])
            documents.append(
                {
                    "source_id": source_id,
                    "content": "\n".join(content for kind, content, *rest in blocks if kind == "text"),
                    "blocks": blocks,
                    "metadata": standard_metadata,
                    "path": str(path),
                    "fingerprint": hashlib.sha256(
                        json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")
                    ).hexdigest(),
                }
            )

        for path in paths:
            try:
                if path.suffix.lower() == ".jsonl":
                    with path.open("r", encoding="utf-8") as handle:
                        for line_number, line in enumerate(handle, 1):
                            if not line.strip():
                                continue
                            try:
                                record = json.loads(line)
                            except json.JSONDecodeError as exc:
                                raise ValueError(f"本地 JSONL 文档格式错误：{path}:{line_number}") from exc
                            add_record(record, path, line_number)
                else:
                    try:
                        record = json.loads(path.read_text(encoding="utf-8"))
                    except json.JSONDecodeError as exc:
                        raise ValueError(f"本地 JSON 文档格式错误：{path}") from exc
                    add_record(record, path, 1)
            except UnicodeDecodeError as exc:
                raise ValueError(f"本地文档必须使用 UTF-8 编码：{path}") from exc

        if not documents:
            raise RuntimeError(
                f"集合 {data.db_collection_id} 没有可用的本地证据记录"
            )

        evidence = []
        for sub_task in data.sub_task:
            terms = set(
                re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9_]+", sub_task.lower())
            )
            ranked = []
            for document in documents:
                haystack = (
                    f"{document['source_id']} {document['content']}"
                ).lower()
                score = sum(1 for term in terms if term in haystack)
                if sub_task.lower() in haystack:
                    score += 3
                ranked.append((score, document["source_id"], document))
            ranked.sort(key=lambda item: (-item[0], item[1]))
            selected = [item[2] for item in ranked if item[0] > 0][:8]
            if not selected:
                selected = [item[2] for item in ranked[:3]]
            if not selected:
                raise RuntimeError(f"子任务没有检索到证据：{sub_task}")

            source_blocks = {}
            for document in selected:
                blocks = []
                for block_info in document["blocks"]:
                    kind, content, *extra = block_info
                    block_metadata = dict(document["metadata"])
                    if extra and extra[0]:
                        block_metadata.update(extra[0])
                    block_metadata.setdefault("retrieval_method", "local_lexical_vector_placeholder")
                    block_metadata.setdefault("document_fingerprint", document["fingerprint"])
                    blocks.append(DataBlock(type=kind, content=content, metadata=block_metadata))
                source_blocks.setdefault(document["source_id"], []).extend(blocks)
            evidence.append({sub_task: source_blocks})

        data.evidence = evidence
        data.overall_steps += 1
        # web_search 是检索阶段的后半部分；只有本地检索和网络检索都成功后才切换路由，
        # 这样网络错误才能重新进入完整的检索重试流程。
        data.current_agent = "RetrieveAgent"
        data.log.append(
            json.dumps(
                {
                    "type": "retrieval",
                    "method": "local",
                    "collection": data.db_collection_id,
                    "sources": sorted(
                        {
                            source_id
                            for task_mapping in evidence
                            for source_mapping in task_mapping.values()
                            for source_id in source_mapping
                        }
                    ),
                },
                ensure_ascii=False,
            )
        )
        return data

    def web_search(self,data:AgentState)->AgentState:
        import hashlib
        import json
        import re
        from datetime import datetime, timezone
        from html.parser import HTMLParser
        from urllib.error import HTTPError, URLError
        from urllib.parse import urljoin, urlparse
        from urllib.request import Request, urlopen

        try:
            from config.structure import DataBlock
        except ModuleNotFoundError:
            from ..config.structure import DataBlock

        if not isinstance(data, AgentState):
            raise TypeError("web_search 需要 AgentState")
        if data.status != "Running":
            raise RuntimeError(f"无法在状态 {data.status} 下进行网络检索")
        if not data.sub_task:
            raise ValueError("没有可检索的 sub_task")
        if not data.evidence or len(data.evidence) != len(data.sub_task):
            raise RuntimeError("网络检索前必须先完成本地检索")

        input_record = None
        for item in data.log:
            try:
                record = json.loads(item)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(record, dict) and record.get("type") == "input":
                input_record = record
                break
        if input_record is None:
            raise RuntimeError("网络检索缺少原始输入记录")
        url = str(input_record.get("url", "")).strip()
        parsed_url = urlparse(url)
        if parsed_url.scheme not in {"http", "https", "file"} or not parsed_url.netloc and parsed_url.scheme != "file":
            raise ValueError("web_search 需要有效的 http、https 或 file URL")

        class PageParser(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.text_parts = []
                self.title_parts = []
                self.images = []
                self.table_rows = []
                self._title_depth = 0
                self._skip_depth = 0
                self._table_depth = 0
                self._current_table = None
                self._current_row = None
                self._current_cell = None

            def handle_starttag(self, tag, attrs):
                tag = tag.lower()
                attributes = dict(attrs)
                if tag in {"script", "style", "noscript"}:
                    self._skip_depth += 1
                    return
                if self._skip_depth:
                    return
                if tag == "title":
                    self._title_depth += 1
                elif tag == "img":
                    source = attributes.get("src") or attributes.get("data-src")
                    if source:
                        self.images.append(
                            {
                                "url": source.strip(),
                                "alt": (attributes.get("alt") or "").strip(),
                            }
                        )
                elif tag == "table":
                    self._table_depth += 1
                    if self._table_depth == 1:
                        self._current_table = []
                        self.table_rows.append(self._current_table)
                elif tag == "tr" and self._table_depth == 1:
                    self._current_row = []
                    if self._current_table is None:
                        self._current_table = []
                        self.table_rows.append(self._current_table)
                    self._current_table.append(self._current_row)
                elif tag in {"td", "th"} and self._table_depth == 1:
                    self._current_cell = []

            def handle_endtag(self, tag):
                tag = tag.lower()
                if tag in {"script", "style", "noscript"} and self._skip_depth:
                    self._skip_depth -= 1
                    return
                if self._skip_depth:
                    return
                if tag == "title" and self._title_depth:
                    self._title_depth -= 1
                elif tag in {"td", "th"} and self._current_cell is not None:
                    cell = " ".join("".join(self._current_cell).split())
                    if self._current_row is None:
                        self._current_row = []
                        self.table_rows.append(self._current_row)
                    self._current_row.append(cell)
                    self._current_cell = None
                elif tag == "tr":
                    self._current_row = None
                elif tag == "table" and self._table_depth:
                    self._table_depth -= 1
                    if self._table_depth == 0:
                        self._current_table = None

            def handle_data(self, value):
                if self._skip_depth or not value.strip():
                    return
                if self._title_depth:
                    self.title_parts.append(value)
                self.text_parts.append(value)
                if self._current_cell is not None:
                    self._current_cell.append(value)

        request = Request(url, headers={"User-Agent": "research-report-agent/1.0"})
        try:
            with urlopen(request, timeout=10) as response:
                raw = response.read()
                content_type = str(response.headers.get("Content-Type", ""))
        except HTTPError as exc:
            raise RuntimeError(f"网络检索返回 HTTP 错误：{exc.code} {url}") from exc
        except URLError as exc:
            raise RuntimeError(f"网络检索连接失败：{url}：{exc.reason}") from exc
        except OSError as exc:
            raise RuntimeError(f"网络检索读取失败：{url}：{exc}") from exc
        if not raw:
            raise ValueError(f"网络检索返回空内容：{url}")

        charset_match = re.search(r"charset=([\w-]+)", content_type, re.I)
        encoding = charset_match.group(1) if charset_match else "utf-8"
        try:
            page = raw.decode(encoding, errors="strict")
        except (LookupError, UnicodeDecodeError):
            try:
                page = raw.decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                raise ValueError(f"网络页面编码无法解析：{url}") from exc

        parser = PageParser()
        try:
            parser.feed(page)
            parser.close()
        except Exception as exc:
            raise ValueError(f"网络页面 HTML 解析失败：{url}") from exc
        page_text = " ".join(" ".join(parser.text_parts).split())
        title = " ".join(" ".join(parser.title_parts).split())
        if not page_text:
            page_text = " ".join(page.split())
        if not page_text:
            raise ValueError(f"网络页面没有可用文本：{url}")

        source_id = "web:" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        base_metadata = {
            "source_id": source_id,
            "url": url,
            "title": title,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "db_collection_id": data.db_collection_id,
            "retrieval_method": "web_search",
        }
        blocks = [DataBlock(type="text", content=page_text, metadata=dict(base_metadata))]
        for image in parser.images:
            image_url = urljoin(url, image["url"])
            image_metadata = dict(base_metadata)
            image_metadata["alt"] = image["alt"]
            blocks.append(DataBlock(type="image", content=image_url, metadata=image_metadata))
        for row_group in parser.table_rows:
            rows = [row for row in row_group if row]
            if not rows:
                continue
            width = max(len(row) for row in rows)
            normalized_rows = [row + [""] * (width - len(row)) for row in rows]
            markdown = ["| " + " | ".join(normalized_rows[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
            markdown.extend("| " + " | ".join(row) + " |" for row in normalized_rows[1:])
            table_metadata = dict(base_metadata)
            table_metadata["columns"] = width
            blocks.append(DataBlock(type="table", content="\n".join(markdown), metadata=table_metadata))

        for sub_task, task_mapping in zip(data.sub_task, data.evidence):
            if not isinstance(task_mapping, dict) or sub_task not in task_mapping:
                raise ValueError(f"evidence 缺少子任务：{sub_task}")
            source_mapping = task_mapping[sub_task]
            if not isinstance(source_mapping, dict):
                raise TypeError(f"evidence 的来源映射格式错误：{sub_task}")
            if source_id not in source_mapping:
                source_mapping[source_id] = [
                    DataBlock(type=block.type, content=block.content, metadata=dict(block.metadata))
                    for block in blocks
                ]

        data.overall_steps += 1
        data.current_agent = "WriteAgent"
        data.retry_count = 2
        data.log.append(
            json.dumps(
                {
                    "type": "retrieval",
                    "method": "web_search",
                    "url": url,
                    "source_id": source_id,
                    "block_types": [block.type for block in blocks],
                },
                ensure_ascii=False,
            )
        )
        return data
