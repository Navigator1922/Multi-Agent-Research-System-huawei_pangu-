# Findings & Decisions

## Requirements
- 只能在现有函数体内实现逻辑，不修改类名、函数签名及返回类型。
- `ContextInput`、`AgentState`、`DataBlock` 是锁定的数据契约；`evidence` 必须由 `DataBlock` 构成。
- 模型调用统一通过 `UniversalModel.generate()`；模型输出异常必须向上抛出，不能模板兜底。
- `Plan_Agent` 需要基于 `topic` 生成 JSON 的全局大纲并拆分子任务；`Retrieve_Agent` 需要执行 Chroma Dense Retrieval；`Write_Agent` 需要 frame/text/image/table 状态流；`Audit_agent` 使用模型审核。

## Research Findings
- 项目位于 `报告撰写` 子目录；根目录不是 Git 仓库，但项目目录是 Git 仓库。
- 当前工作树已有用户改动，包含 Agent 文件、`main.py`、结构和适配器，以及若干被删除的数据/脚本文件；这些改动必须保留并在其基础上工作。
- 当前占位点：`utils/data_loader.py` 1 处，`agents/plan_agent.py` 3 处，`agents/retrieve_agent.py` 3 处，`agents/write_agent.py` 5 处，`agents/audit_agent.py` 3 处。
- 当前 `main.py` 调用顺序固定为 `Programme -> Split -> retrieve -> web_search -> frame -> text -> image -> table -> kpi -> audit`；实现需适配该顺序，不能依赖旧提交中的 `Planning/write/baseline` 接口。
- 旧提交中的 `source_store.py`、`source_metadata` 等字段已被当前结构删除，不能依赖；检索实现需在 `Retrieve_Agent` 内直接产出 `DataBlock`。
- `UniversalModel` 在未配置 `LLM_MODEL_NAME` 时由加载器返回 `None`；本轮四个 Agent 均要求注入可用模型并明确抛出配置错误。
- 本轮新要求覆盖旧的审核规则：`Audit_agent` 必须接收 `UniversalModel`，并用模型完成 AI 味和深度覆盖率审核。
- `Retrieve_Agent` 不得扫描本地文件或进行词频排序，必须连接 `./chroma_db`，使用中文 `SentenceTransformerEmbeddingFunction` 和 `collection.query`。
- `Write_Agent` 不得向 `AgentState` 动态注入属性；草稿必须通过现有 `log` 字段 JSON 序列化保存。
- `Plan_Agent` 不得在 `Split` 中反向解析日志推导主题；主题需要在状态中显式传递。
- 当前 `AgentState` 没有 `topic` 或 `outline` 字段，需要做最小数据类扩展；当前 `main.py` 使用 `Audit_agent()`，需要改为传入模型。

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| 仅在当前函数体中实现，使用函数内导入和局部辅助逻辑 | 遵守“不得修改现有接口”的开发纪律 |
| 检索使用 Loader 写入的 Chroma 集合 | RetrieveAgent 必须与 Loader 使用相同嵌入模型并执行 Dense Retrieval |
| 报告中同时保存来源编号和完整 metadata JSON | 让 DataBlock 引用元数据在状态和最终报告中都可追溯 |

## Issues Encountered
| Issue | Resolution |
|-------|------------|

- 项目当前工作树删除了默认 `data/` 和 `utils/source_store.py`，行为验证将使用临时 JSON/HTML fixture，不恢复用户删除内容。
- 端到端验证首次暴露 HTML table 分组错误和 web 失败路由问题，均已修正并重新验证。
- 当前环境的 `openai` 依赖在导入时因 `aiohttp` 版本元数据为 `None` 抛出比较异常，导致 `main.py` 导入验证未完成；这不是本轮四个 Agent 的代码错误。

## Resources
-
