# Task Plan: 修复模型报告生成可靠性

## Goal
按用户指定优先级修复模型报告生成：拆分子任务、程序化添加引用、实现带反馈的重试、处理输出截断，并保持既有来源快照和 `run_pipeline(data)` 架构。

## Next Step
完成最终回归记录并交付修复结果。

## Current Phase
Phase 5

## Phases

### Phase 1: Requirements & Discovery
- [x] Understand user intent
- [x] Identify constraints
- [x] Document current implementation and repair contract
- **Status:** complete

### Phase 2: Planning & Structure
- [x] Design per-subtask model generation and deterministic report assembly
- [x] Design adaptive retry state and truncation detection
- **Status:** complete

### Phase 3: Implementation
- [x] Update state, main retry flow, writer, and model adapter
- [x] Add focused regression tests
- **Status:** complete

### Phase 4: Testing & Verification
- [x] Run regression tests and local pipeline samples
- [x] Verify source-loading and package import paths
- **Status:** complete

### Phase 5: Delivery
- [x] Review diff and summarize behavior changes
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 保留 `run_pipeline(data)` 和前三个输入字段 | 减少对原始骨架的破坏 |
| 增加可选 `source_ids` | 支持多来源且避免把正文放进输入 |
| 使用固定 revision 和 SHA-256 校验完整快照 | 保证来源可追溯并防止静默数据变更 |
| 每个子任务独立生成，标题和引用由程序组装 | 降低单次输出长度，并消除模型遗漏真实引用标记的风险 |
| 将最近一次 Agent 错误保存到 `AgentState` | 让主循环重试时能修改提示词而不是重复请求 |
| 模型适配器记录是否触及 `max_new_tokens` | 在写作阶段识别被硬截断的输出并触发修复重试 |

## Errors Encountered
| Error | Resolution |
| 初次批量更新使用了错误的相对路径，找不到根目录规划文件 | 改用 `openpangu_qa` 下的绝对路径重新应用更新 |
| Windows 默认代码页显示中文运行输出乱码 | 记录指标并使用 UTF-8 输出复核文本 |
| 读取了不存在的 `tests/test_source_pipeline.py` | 根据项目清单改读实际的 `tests/test_data_pipeline.py` |
| 父目录包导入验证时手写了错误的 Wikipedia URL | 使用 `normal_input.json` 中的准确 URL 重跑 |
