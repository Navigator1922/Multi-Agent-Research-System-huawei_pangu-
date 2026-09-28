# Findings & Decisions

## Requirements
- 只能在现有函数体内实现逻辑，不修改类名、函数签名及返回类型。
- `ContextInput`、`AgentState`、`DataBlock` 是锁定的数据契约；`evidence` 必须由 `DataBlock` 构成。
- 模型调用统一通过 `UniversalModel.generate()`；模型输出异常必须向上抛出，不能模板兜底。
- `Plan_Agent` 需要基于 `topic` 生成 JSON 的 `sub_task` 列表；`Retrieve_Agent` 需要整合本地 retrieve 和 web_search；`Write_Agent` 需要 frame/text/image/table 状态流；`Audit_Agent` 不调用大模型。

## Research Findings
- 项目位于 `报告撰写` 子目录；根目录不是 Git 仓库，但项目目录是 Git 仓库。
- 当前工作树已有用户改动，包含 Agent 文件、`main.py`、结构和适配器，以及若干被删除的数据/脚本文件；这些改动必须保留并在其基础上工作。
- 当前占位点：`utils/data_loader.py` 1 处，`agents/plan_agent.py` 3 处，`agents/retrieve_agent.py` 3 处，`agents/write_agent.py` 5 处，`agents/audit_agent.py` 3 处。
- 当前 `main.py` 调用顺序固定为 `Programme -> Split -> retrieve -> web_search -> frame -> text -> image -> table -> kpi -> audit`；实现需适配该顺序，不能依赖旧提交中的 `Planning/write/baseline` 接口。
- 旧提交中的 `source_store.py`、`source_metadata` 等字段已被当前结构删除，不能依赖；检索实现需在 `Retrieve_Agent` 内直接产出 `DataBlock`。
- `UniversalModel` 在未配置 `LLM_MODEL_NAME` 时由加载器返回 `None`，因此无模型模式需要有确定性本地逻辑；模型模式的返回异常必须保留并抛出。

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| 仅在当前函数体中实现，使用函数内导入和局部辅助逻辑 | 遵守“不得修改现有接口”的开发纪律 |
| 本地检索使用可验证的 JSON/JSONL 文档读取和词项相关性排序 | 当前仓库已删除旧来源存储模块，且任务允许预留标准向量检索占位符 |
| 报告中同时保存来源编号和完整 metadata JSON | 让 DataBlock 引用元数据在状态和最终报告中都可追溯 |

## Issues Encountered
| Issue | Resolution |
|-------|------------|

- 项目当前工作树删除了默认 `data/` 和 `utils/source_store.py`，行为验证将使用临时 JSON/HTML fixture，不恢复用户删除内容。
- 端到端验证首次暴露 HTML table 分组错误和 web 失败路由问题，均已修正并重新验证。

## Resources
-
