"""模型驱动的多模态报告写作和排版 Agent。"""

from __future__ import annotations

import json

from config.structure import AgentState, DataBlock


class Write_Agent:
    """使用模型生成正文，并由模型决定多模态块的插入位置。"""

    def __init__(self, model):
        self.model = model

    def frame(self, data: AgentState):
        """校验证据并在 log 中创建结构化写作草稿。"""

        self._validate_state(data, "frame")
        previous = _latest_draft(data)
        previous_by_task = {
            section.get("sub_task"): section
            for section in previous.get("sections", [])
            if isinstance(section, dict)
        }
        sections = []
        for sub_task in data.sub_task:
            old = previous_by_task.get(sub_task, {})
            sections.append(
                {
                    "sub_task": sub_task,
                    "body": str(old.get("body", "")),
                    "image_placements": list(old.get("image_placements", [])),
                    "table_placements": list(old.get("table_placements", [])),
                }
            )
        _append_draft(data, "frame", sections)
        data.overall_steps += 1
        return data

    def text(self, data: AgentState):
        """根据文本 DataBlock 逐节生成正文，并保存到 JSON 草稿。"""

        self._validate_model()
        sections = _draft_sections(data, "text")
        for section in sections:
            if section["body"].strip():
                continue
            sub_task = section["sub_task"]
            evidence = _blocks_for_task(data, sub_task, "text")
            if not evidence:
                raise ValueError(f"子任务缺少文本 DataBlock：{sub_task}")
            evidence_text = _format_blocks(evidence)
            prompt = (
                "你是调研报告正文撰写 Agent。请围绕指定子任务，仅依据给出的文本 DataBlock"
                "撰写客观、连贯、具体的中文正文。可以进行归纳，但不得引入证据之外的事实。"
                "只输出正文，不要输出标题、来源列表、JSON、解释或代码围栏。\n\n"
                f"子任务：{sub_task}\n"
                f"文本 DataBlock：\n{evidence_text}"
            )
            body = self.model.generate(prompt)
            if not isinstance(body, str) or not body.strip():
                raise ValueError(f"正文模型返回为空：{sub_task}")
            section["body"] = body.strip()

        _append_draft(data, "text", sections)
        data.overall_steps += 1
        return data

    def image(self, data: AgentState):
        """让模型结合正文判断图片应插入的自然位置。"""

        self._validate_model()
        sections = _draft_sections(data, "image")
        for section in sections:
            sub_task = section["sub_task"]
            candidates = _blocks_for_task(data, sub_task, "image")
            section["body"], section["image_placements"] = self._layout_blocks(
                section=section,
                candidates=candidates,
                block_type="image",
            )

        _append_draft(data, "image", sections)
        data.overall_steps += 1
        return data

    def table(self, data: AgentState):
        """让模型结合正文判断表格应插入的自然位置并生成最终报告。"""

        self._validate_model()
        sections = _draft_sections(data, "table")
        for section in sections:
            sub_task = section["sub_task"]
            candidates = _blocks_for_task(data, sub_task, "table")
            section["body"], section["table_placements"] = self._layout_blocks(
                section=section,
                candidates=candidates,
                block_type="table",
            )

        _append_draft(data, "table", sections)
        report = _assemble_report(data, sections)
        data.overall_steps += 1
        data.log.append(
            json.dumps({"type": "report", "content": report}, ensure_ascii=False)
        )
        data.current_agent = "AuditAgent"
        data.retry_count = 2
        return data

    def _layout_blocks(self, section, candidates, block_type):
        """调用模型返回已排版正文，并严格校验块是否被使用。"""

        candidate_payload = []
        for block_id, block in candidates:
            candidate_payload.append(
                {
                    "block_id": block_id,
                    "content": block.content,
                    "metadata": block.metadata,
                }
            )
        prompt = (
            "你是调研报告多模态排版 Agent。请在内部分析正文语义和候选 DataBlock 的关系，"
            f"判断 {block_type} 放在哪一句之后最自然，然后输出排版后的完整正文。"
            "必须保留原正文事实，不得编造候选块之外的内容。"
            "对每个候选块都必须使用一次：图片必须以 Markdown 图片形式保留准确 URL/路径，"
            "表格必须原样保留准确 Markdown 内容。只输出合法 JSON，不要输出解释或代码围栏。"
            '格式：{"body":"排版后的正文","used_block_ids":["块编号"]}\n\n'
            f"子任务：{section['sub_task']}\n"
            f"当前正文：\n{section['body']}\n\n"
            f"候选 {block_type} DataBlock：\n"
            f"{json.dumps(candidate_payload, ensure_ascii=False)}"
        )
        response = self.model.generate(prompt)
        payload = _parse_layout_response(response, block_type)
        expected_ids = {block_id for block_id, _ in candidates}
        used_ids = set(payload["used_block_ids"])
        if used_ids != expected_ids:
            raise ValueError(
                f"{block_type} 排版结果未完整使用候选 DataBlock："
                f"expected={sorted(expected_ids)}, actual={sorted(used_ids)}"
            )
        content_by_id = {block_id: block.content for block_id, block in candidates}
        for block_id, content in content_by_id.items():
            if content not in payload["body"]:
                raise ValueError(f"{block_type} 排版结果丢失 DataBlock 内容：{block_id}")
        return payload["body"], payload["used_block_ids"]

    def _validate_model(self):
        if self.model is None or not callable(getattr(self.model, "generate", None)):
            raise RuntimeError("Write_Agent 必须注入可用的 UniversalModel")

    @staticmethod
    def _validate_state(data: AgentState, stage: str):
        if not isinstance(data, AgentState):
            raise TypeError(f"{stage} 需要 AgentState")
        if data.status != "Running":
            raise RuntimeError(f"无法在状态 {data.status} 下执行 {stage}")
        if not data.sub_task:
            raise ValueError("报告缺少 sub_task")
        if not isinstance(data.evidence, list) or len(data.evidence) != len(data.sub_task):
            raise ValueError("evidence 必须与 sub_task 一一对应")


def _latest_draft(data: AgentState) -> dict:
    """从 log 中读取最新写作草稿。"""

    latest = None
    for item in data.log:
        try:
            record = json.loads(item)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(record, dict) and record.get("type") == "write_draft":
            latest = record
    if latest is None:
        return {"type": "write_draft", "stage": "initial", "sections": []}
    if not isinstance(latest.get("sections"), list):
        raise ValueError("write_draft.sections 必须是列表")
    return latest


def _draft_sections(data: AgentState, stage: str) -> list[dict]:
    """读取当前草稿并校验章节顺序。"""

    draft = _latest_draft(data)
    sections = draft["sections"]
    if len(sections) != len(data.sub_task):
        raise ValueError(f"{stage} 阶段的草稿章节数量不匹配")
    for section, sub_task in zip(sections, data.sub_task):
        if not isinstance(section, dict) or section.get("sub_task") != sub_task:
            raise ValueError(f"{stage} 阶段的草稿章节顺序或格式错误")
        if not isinstance(section.get("body"), str):
            raise ValueError(f"{stage} 阶段的草稿正文必须是字符串")
    return sections


def _append_draft(data: AgentState, stage: str, sections: list[dict]):
    """将不含 DataBlock 对象的草稿快照序列化到 log。"""

    serializable = []
    for section in sections:
        serializable.append(
            {
                "sub_task": section["sub_task"],
                "body": section["body"],
                "image_placements": list(section.get("image_placements", [])),
                "table_placements": list(section.get("table_placements", [])),
            }
        )
    data.log.append(
        json.dumps(
            {"type": "write_draft", "stage": stage, "sections": serializable},
            ensure_ascii=False,
        )
    )


def _blocks_for_task(data: AgentState, sub_task: str, block_type: str):
    """提取一个子任务对应类型的 DataBlock，并生成稳定的块编号。"""

    task_mapping = next((item for item in data.evidence if sub_task in item), None)
    if not isinstance(task_mapping, dict):
        raise ValueError(f"evidence 缺少子任务：{sub_task}")
    source_mapping = task_mapping[sub_task]
    if not isinstance(source_mapping, dict):
        raise TypeError(f"evidence 的来源映射格式错误：{sub_task}")

    result = []
    for source_id, blocks in source_mapping.items():
        if not isinstance(blocks, list):
            raise TypeError(f"来源的 DataBlock 列表格式错误：{source_id}")
        for index, block in enumerate(blocks):
            if not isinstance(block, DataBlock):
                raise TypeError("evidence 最内层必须全部是 DataBlock 对象")
            if block.type == block_type:
                result.append((f"{source_id}:{block_type}:{index}", block))
    return result


def _format_blocks(blocks) -> str:
    """将 DataBlock 转成模型可读但不改变原内容的证据文本。"""

    return "\n\n".join(
        f"块编号：{block_id}\n内容：{block.content}\nmetadata："
        f"{json.dumps(block.metadata, ensure_ascii=False)}"
        for block_id, block in blocks
    )


def _parse_layout_response(response: str, block_type: str) -> dict:
    """严格解析模型排版 JSON。"""

    if not isinstance(response, str) or not response.strip():
        raise ValueError(f"{block_type} 排版模型返回为空")
    try:
        payload = json.loads(response.strip().lstrip("\ufeff"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{block_type} 排版模型返回的 JSON 无法解析") from exc
    if not isinstance(payload, dict) or set(payload) != {"body", "used_block_ids"}:
        raise ValueError(f"{block_type} 排版结果必须只包含 body 和 used_block_ids")
    if not isinstance(payload["body"], str) or not payload["body"].strip():
        raise ValueError(f"{block_type} 排版结果 body 不能为空")
    if not isinstance(payload["used_block_ids"], list) or any(
        not isinstance(item, str) or not item.strip()
        for item in payload["used_block_ids"]
    ):
        raise ValueError(f"{block_type} 排版结果 used_block_ids 格式错误")
    if len(set(payload["used_block_ids"])) != len(payload["used_block_ids"]):
        raise ValueError(f"{block_type} 排版结果存在重复块编号")
    payload["body"] = payload["body"].strip()
    return payload


def _assemble_report(data: AgentState, sections: list[dict]) -> str:
    """组装章节正文和证据追踪信息，不改变模型生成的正文。"""

    lines = ["# 调研报告", ""]
    for section in sections:
        lines.extend([f"## {section['sub_task']}", section["body"].strip(), "证据追踪："])
        task_mapping = next(item[section["sub_task"]] for item in data.evidence if section["sub_task"] in item)
        for source_id, blocks in task_mapping.items():
            for index, block in enumerate(blocks):
                if not isinstance(block, DataBlock):
                    raise TypeError("evidence 最内层必须全部是 DataBlock 对象")
                metadata = json.dumps(block.metadata, ensure_ascii=False)
                lines.append(
                    f"[{source_id}:{block.type}:{index}] metadata={metadata}"
                )
        lines.append("")
    report = "\n\n".join(lines).strip()
    if not report:
        raise RuntimeError("报告组装结果为空")
    return report
