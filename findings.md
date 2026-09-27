# Findings & Decisions

## Requirements
- 用户希望通读 `openpangu_qa` 项目，理解其运行方式和工作机制。
- 用户现在要求按“拆分子任务、程序化引用、反馈式重试、提高预算并检测截断”的优先级修复业务代码。
- 修复必须遵循现有设计架构，保持 `run_pipeline(data)` 对外接口兼容。
- 项目根目录不是 Git 仓库；分析范围为 `openpangu_qa` 子目录。

## Research Findings
- 初步观察：项目包含 `main.py`、`config`、`utils`、`data`、`result`，并带有 `README.md`；整体表现为 Python 项目。
- README 将系统定义为“规划、检索、撰写、审核”四 Agent 的调研报告生成系统。
- `main.run_pipeline(data)` 是公开入口：先通过 `loader` 规范化输入，再按 `AgentState.current_agent` 路由 Retrieve/Write/Audit；异常按当前状态的 `retry_count` 重试，最终由 `_latest_report` 从日志中提取报告，并额外执行独立 baseline。
- 本地默认不需要第三方模型；设置 `PANGU_MODEL_PATH` 后才尝试加载本地 openPangu 模型，模型适配在 `utils/model_adapter.py`。
- 输入要求是包含 `context`、`source_id`、`url` 三个字符串字段的对象，也可以传 `ContextInput` 或 JSON 文件路径。
- 数据为本地 Wikipedia JSON 来源；项目没有网络检索实现，检索 Agent 应从这些本地来源匹配证据。
- `ContextInput` 是三字段数据类；`AgentState` 保存状态、当前 Agent、重试计数、日志、子任务和证据；`SystemOutput` 对外返回报告、步数、重试、覆盖率和 baseline。
- PlanAgent 在主循环外执行：本地模式固定生成三个主题子任务；模型模式要求模型返回可解析且至少三个不重复任务，失败会在内部最多重试两次。
- RetrieveAgent 不进行关键词搜索，而是把单一输入 `context` 原样挂到每个子任务的 `source_id` 下，形成原始骨架要求的 evidence 格式。
- WriteAgent 本地模式确定性拼接报告；模型模式动态生成提示词并校验每个真实子任务的小节及引用。覆盖率按子任务小节计算，而不是全文搜索。
- AuditAgent 检查报告是否为空、是否有证据、每个子任务是否有对应引用；通过后置为 `Completed`，否则置为 `Error`。流程结束后 baseline 独立执行一次单 Agent 报告生成。
- `data/normal_input.json`、`data/retrieval_failure.json` 是主要运行样例；`data/wikipedia_sources/` 存放页面来源，`data/wikipedia_manifest.json` 存放来源元数据。
- 项目未发现 `requirements.txt`、`pyproject.toml` 等依赖清单；README 声明本地模式仅使用标准库，云端模式需要 `torch`、`torch-npu`、`transformers`。
- 实际本地运行 `normal_input.json` 成功：`overall_steps=4`、`total_retries=0`、`coverage_rate=1.0`、baseline 成功且 `model_used=false`。
- 实际本地运行 `retrieval_failure.json` 进入错误路径：`source_id` 为空导致 RetrieveAgent 连续失败并耗尽两次重试，最终 `coverage_rate=0.0`，baseline 也因来源编号为空失败。
- 直接传入字典也成功，说明 `run_pipeline` 同时支持 JSON 路径和内存对象；本地正常流程的四步是 Plan（循环外执行）、Retrieve、Write、Audit。
- `wikipedia_manifest.json` 记录了 5 个预抓取来源，但当前 `normal_input.json` 只携带 `wiki_generative_ai` 的 3000 字符上下文；`RetrieveAgent` 不会自动读取 manifest 或 `wikipedia_sources`，这些文件主要是数据准备和备用来源。
- `main.py` 没有命令行入口或 `if __name__ == '__main__'` 执行块，因此推荐按 README 用 `python -c` 导入 `run_pipeline`；从父目录以命名空间包方式导入同样可用。
- 当前没有独立测试目录或测试配置；验证主要依靠 README 样例和手工运行。
- 当前工作区已经存在来源快照方向的改动：`ContextInput` 已包含 `source_ids`，`AgentState` 已包含 `source_metadata`，`WriteAgent` 已开始从来源元数据读取 URL 和摘要信息；这些改动视为现有工作并保留。
- 当前待修复的模型路径仍把全部子任务和证据放进一次 `WriteAgent._model_write` 调用；`PanguModel.generate` 仍默认 `max_new_tokens=512`、`do_sample=False`，且主流程重试只重复调用，不传入上次错误。

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| 当前修复保留 `run_pipeline(data)` 和前三个输入字段兼容性 | 避免破坏原始骨架，同时把来源正文从输入中移出 |
| 输入改为研究主题 + `source_ids`，来源正文由本地数据加载器按 ID 读取 | 使 RetrieveAgent 真正承担来源读取与校验职责 |
| Wikipedia 快照保存完整正文，并用 SHA-256、revision_id、URL 和字符数校验 | 防止静默截断、来源错配和文件被意外修改 |
| 每个子任务独立生成，标题和引用由程序组装 | 降低单次输出长度，并消除模型遗漏真实引用标记的风险 |
| 将最近一次 Agent 错误保存到 `AgentState` | 让主循环重试时能修改提示词而不是重复请求 |
| 模型适配器记录是否触及 `max_new_tokens` | 在写作阶段识别被硬截断的输出并触发修复重试 |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| 外层工作目录不是 Git 仓库 | 将 `openpangu_qa` 作为项目根目录分析 |
| 当前 `normal_input.json` 直接包含 3000 字符截断正文 | 计划改为只保存主题和来源 ID，由检索阶段读取完整快照 |
| 终端默认代码页导致中文运行输出显示乱码 | 以返回指标和代码逻辑为准，后续用 UTF-8 输出复核文本 |

## Resources
- `README.md`：运行方式、数据格式和云端模型说明。
- `main.py`：主流程与状态路由。
- `config/structure.py`：跨 Agent 状态和输入输出的数据契约。
- `agents/*.py`：四个 Agent 的具体行为。
- `utils/data_loader.py`、`utils/model_adapter.py`：输入加载和可选模型接入。
