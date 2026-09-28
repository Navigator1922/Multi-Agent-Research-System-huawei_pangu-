import json

try:
    from config.structure import AgentState,DataBlock
except ModuleNotFoundError:
    from ..config.structure import AgentState,DataBlock


class Write_Agent:

    def __init__(self, model):
        self.model = model

    def frame(self, data: AgentState):
        if not isinstance(data, AgentState):
            raise TypeError("frame 需要 AgentState")
        if data.status != "Running":
            raise RuntimeError(f"无法在状态 {data.status} 下撰写报告")
        if not data.sub_task:
            raise ValueError("报告缺少 sub_task")
        if not isinstance(data.evidence, list) or len(data.evidence) != len(data.sub_task):
            raise ValueError("evidence 必须与 sub_task 一一对应")

        sections = []
        for sub_task, task_mapping in zip(data.sub_task, data.evidence):
            if not isinstance(task_mapping, dict) or set(task_mapping) != {sub_task}:
                raise ValueError(f"evidence 的子任务映射格式错误：{sub_task}")
            sources = task_mapping[sub_task]
            if not isinstance(sources, dict) or not sources:
                raise ValueError(f"子任务没有来源证据：{sub_task}")
            normalized_sources = {}
            for source_id, blocks in sources.items():
                if not isinstance(source_id, str) or not source_id.strip():
                    raise ValueError(f"子任务存在无效 source_id：{sub_task}")
                if not isinstance(blocks, list) or not blocks:
                    raise ValueError(f"来源没有 DataBlock：{source_id}")
                for block in blocks:
                    if not isinstance(block, DataBlock):
                        raise TypeError("evidence 最内层必须全部是 DataBlock 对象")
                    if block.type not in {"text", "image", "table"}:
                        raise ValueError(f"不支持的 DataBlock 类型：{block.type}")
                    if not isinstance(block.content, str) or not block.content.strip():
                        raise ValueError(f"DataBlock.content 不能为空：{source_id}")
                    if not isinstance(block.metadata, dict):
                        raise TypeError(f"DataBlock.metadata 必须是字典：{source_id}")
                normalized_sources[source_id] = list(blocks)
            sections.append(
                {
                    "sub_task": sub_task,
                    "sources": normalized_sources,
                    "body": "",
                    "images": [],
                    "tables": [],
                }
            )

        data._write_sections = sections
        data.overall_steps += 1
        data.log.append(
            json.dumps(
                {"type": "frame", "sections": [item["sub_task"] for item in sections]},
                ensure_ascii=False,
            )
        )
        return data

    def text(self, data: AgentState):
        import json

        try:
            from config.structure import DataBlock
        except ModuleNotFoundError:
            from ..config.structure import DataBlock

        if not isinstance(data, AgentState):
            raise TypeError("text 需要 AgentState")
        sections = getattr(data, "_write_sections", None)
        if not isinstance(sections, list) or len(sections) != len(data.sub_task):
            raise RuntimeError("text 必须在 frame 完成后执行")

        for section in sections:
            evidence_parts = []
            for source_id, blocks in section["sources"].items():
                for block in blocks:
                    if not isinstance(block, DataBlock):
                        raise TypeError("evidence 最内层必须全部是 DataBlock 对象")
                    if block.type != "text":
                        continue
                    metadata = json.dumps(block.metadata, ensure_ascii=False)
                    evidence_parts.append(
                        f"来源编号：[{source_id}]\n来源 metadata：{metadata}\n来源正文：{block.content}"
                    )
            if not evidence_parts:
                raise ValueError(f"子任务缺少文本 DataBlock：{section['sub_task']}")
            evidence_text = "\n\n".join(evidence_parts)
            if self.model is None:
                body = (
                    f"本节围绕“{section['sub_task']}”整理可核验事实。\n"
                    + "\n\n".join(
                        f"- {part.split('来源正文：', 1)[-1].strip()}"
                        for part in evidence_parts
                    )
                )
            else:
                prompt = (
                    "你是调研报告撰写 Agent。请只依据给出的 DataBlock 文本证据，"
                    "围绕指定子任务写一段客观、具体、中文的报告正文。不要编造证据，"
                    "不要输出标题、来源列表或 Markdown 代码围栏；来源编号和 metadata 由系统保留。\n\n"
                    f"子任务：{section['sub_task']}\n"
                    f"DataBlock 证据：\n{evidence_text}"
                )
                body = self.model.generate(prompt)
                if not isinstance(body, str) or not body.strip():
                    raise ValueError(f"撰写模型返回空正文：{section['sub_task']}")
                body = body.strip()
            section["body"] = body

        data.overall_steps += 1
        data.log.append("WriteAgent: text 阶段完成")
        return data

    def image(self, data: AgentState):
        import json

        try:
            from config.structure import DataBlock
        except ModuleNotFoundError:
            from ..config.structure import DataBlock

        if not isinstance(data, AgentState):
            raise TypeError("image 需要 AgentState")
        sections = getattr(data, "_write_sections", None)
        if not isinstance(sections, list):
            raise RuntimeError("image 必须在 frame 完成后执行")

        for section in sections:
            image_blocks = []
            for source_id, blocks in section["sources"].items():
                for block in blocks:
                    if not isinstance(block, DataBlock):
                        raise TypeError("evidence 最内层必须全部是 DataBlock 对象")
                    if block.type != "image":
                        continue
                    metadata = json.dumps(block.metadata, ensure_ascii=False)
                    alt = str(block.metadata.get("alt", source_id)).strip() or source_id
                    image_blocks.append(
                        f"![{alt}]({block.content})\n图片引用：[{source_id}] metadata={metadata}"
                    )
            section["images"] = image_blocks

        data.overall_steps += 1
        data.log.append("WriteAgent: image 阶段完成")
        return data

    def table(self, data: AgentState):
        import json

        try:
            from config.structure import DataBlock
        except ModuleNotFoundError:
            from ..config.structure import DataBlock

        if not isinstance(data, AgentState):
            raise TypeError("table 需要 AgentState")
        sections = getattr(data, "_write_sections", None)
        if not isinstance(sections, list):
            raise RuntimeError("table 必须在 frame 完成后执行")

        report_lines = ["# 调研报告", ""]
        for section in sections:
            if not section.get("body"):
                raise RuntimeError(f"子任务尚未生成正文：{section['sub_task']}")
            table_blocks = []
            references = []
            for source_id, blocks in section["sources"].items():
                for block in blocks:
                    if not isinstance(block, DataBlock):
                        raise TypeError("evidence 最内层必须全部是 DataBlock 对象")
                    metadata = json.dumps(block.metadata, ensure_ascii=False)
                    if block.type == "table":
                        table_blocks.append(
                            f"数据表引用：[{source_id}] metadata={metadata}\n{block.content}"
                        )
                    references.append(
                        f"[{source_id}] type={block.type} metadata={metadata}"
                    )
            section["tables"] = table_blocks
            report_lines.append(f"## {section['sub_task']}")
            report_lines.append(section["body"].strip())
            if section["images"]:
                report_lines.append("\n".join(section["images"]))
            if table_blocks:
                report_lines.append("\n\n".join(table_blocks))
            report_lines.append("引用证据：")
            report_lines.extend(references)
            report_lines.append("")

        report = "\n\n".join(report_lines).strip()
        if not report:
            raise RuntimeError("报告组装结果为空")
        data.overall_steps += 1
        data.log.append("WriteAgent: table 阶段完成")
        data.log.append(
            json.dumps({"type": "report", "content": report}, ensure_ascii=False)
        )
        data.current_agent = "AuditAgent"
        data.retry_count = 2
        return data
