"""负责生成研究大纲并将大纲拆分为可检索子任务。"""

import json

from config.structure import AgentState, ContextInput


class Plan_Agent:
    """使用大模型完成全局研究规划。"""

    def __init__(self, model):
        self.model = model

    def Programme(self, data: ContextInput) -> AgentState:
        """根据主题生成结构化研究大纲并写入正式状态字段。"""

        if not isinstance(data, ContextInput):
            raise TypeError("Programme 需要 ContextInput")
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (data.topic, data.db_collection_id, data.source_id, data.url)
        ):
            raise ValueError("ContextInput 的所有字段都必须是非空字符串")
        if self.model is None or not callable(getattr(self.model, "generate", None)):
            raise RuntimeError("Plan_Agent 必须注入可用的 UniversalModel")

        prompt = (
            "你是多智能体调研系统的总规划 Agent。请围绕给定主题生成一份可执行的全局研究大纲。"
            "大纲至少包含三个互不重复的章节，每个章节必须包含 title、question、evidence_focus。"
            "question 必须是可由检索证据回答的具体问题，evidence_focus 必须说明需要寻找的证据类型。"
            "只能输出合法 JSON，不得输出解释、Markdown 或代码围栏。严格格式："
            '{"outline":[{"title":"章节标题","question":"研究问题","evidence_focus":"证据重点"}]}\n'
            f"主题：{data.topic.strip()}"
        )
        response = self.model.generate(prompt)
        payload = self._parse_outline(response)

        state = AgentState(
            current_agent="PlanAgent",
            topic=data.topic.strip(),
            outline=payload,
            db_collection_id=data.db_collection_id.strip(),
        )
        state.log.append(
            json.dumps(
                {
                    "type": "input",
                    "topic": state.topic,
                    "db_collection_id": state.db_collection_id,
                    "source_id": data.source_id.strip(),
                    "url": data.url.strip(),
                },
                ensure_ascii=False,
            )
        )
        state.log.append(
            json.dumps(
                {"type": "outline", "outline": state.outline},
                ensure_ascii=False,
            )
        )
        state.overall_steps += 1
        return state

    def Split(self, task: AgentState) -> AgentState:
        """将正式大纲字段转换为检索子任务，不读取过程日志。"""

        if not isinstance(task, AgentState):
            raise TypeError("Split 需要 AgentState")
        if task.status != "Running":
            raise RuntimeError(f"无法在状态 {task.status} 下拆分任务")
        if not task.topic.strip():
            raise ValueError("AgentState.topic 不能为空")
        if not isinstance(task.outline, list) or len(task.outline) < 3:
            raise ValueError("AgentState.outline 至少需要三个章节")

        sub_tasks = []
        for item in task.outline:
            if not isinstance(item, dict):
                raise TypeError("outline 中的章节必须是对象")
            title = item.get("title")
            question = item.get("question")
            evidence_focus = item.get("evidence_focus")
            if any(
                not isinstance(value, str) or not value.strip()
                for value in (title, question, evidence_focus)
            ):
                raise ValueError("outline 章节必须包含非空 title、question、evidence_focus")
            sub_tasks.append(
                f"{title.strip()}：{question.strip()}；证据重点：{evidence_focus.strip()}"
            )

        if len(set(sub_tasks)) != len(sub_tasks):
            raise ValueError("outline 生成了重复的检索子任务")
        task.sub_task = sub_tasks
        task.current_agent = "RetrieveAgent"
        task.retry_count = 2
        task.overall_steps += 1
        task.log.append(
            json.dumps(
                {"type": "sub_tasks", "items": task.sub_task},
                ensure_ascii=False,
            )
        )
        return task

    @staticmethod
    def _parse_outline(response: str) -> list[dict[str, str]]:
        """严格解析模型返回的大纲 JSON。"""

        if not isinstance(response, str) or not response.strip():
            raise ValueError("规划模型返回为空")
        try:
            payload = json.loads(response.strip().lstrip("\ufeff"))
        except json.JSONDecodeError as exc:
            raise ValueError("规划模型返回的 JSON 无法解析") from exc
        if not isinstance(payload, dict) or set(payload) != {"outline"}:
            raise ValueError("规划结果必须是只包含 outline 字段的 JSON 对象")

        outline = payload["outline"]
        if not isinstance(outline, list) or len(outline) < 3:
            raise ValueError("规划结果的 outline 至少需要三个章节")
        normalized = []
        for item in outline:
            if not isinstance(item, dict) or set(item) != {
                "title",
                "question",
                "evidence_focus",
            }:
                raise ValueError(
                    "outline 的每个章节必须只包含 title、question、evidence_focus"
                )
            if any(not isinstance(item[key], str) for key in item):
                raise ValueError("outline 章节字段必须是字符串")
            chapter = {key: item[key].strip() for key in item}
            if any(not value for value in chapter.values()):
                raise ValueError("outline 章节字段必须是非空字符串")
            normalized.append(chapter)
        titles = [item["title"] for item in normalized]
        if len(set(titles)) != len(titles):
            raise ValueError("outline 章节标题不能重复")
        return normalized
