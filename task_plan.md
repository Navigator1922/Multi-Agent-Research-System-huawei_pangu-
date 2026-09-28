# Task Plan: Rewrite four agents as a real multimodal RAG flow

## Goal
将四个 Agent 改为基于 Chroma Dense Retrieval、模型驱动排版和模型审核的真实多智能体流程。

## Next Step
无，整改已完成。

## Current Phase
Phase 5

## Phases

### Phase 1: Requirements & Discovery
- [x] Understand user intent
- [x] Identify constraints
- [x] Document in findings.md
- **Status:** complete

### Phase 2: Planning & Structure
- [x] Define approach
- [x] Confirm required state changes
- **Status:** complete

### Phase 3: Implementation
- [x] Rewrite Plan/Retrieve/Write/Audit
- [x] Update main wiring for model-driven audit
- **Status:** complete

### Phase 4: Testing & Verification
- [x] Run syntax and contract tests
- [x] Verify retry and strict JSON failure paths
- **Status:** complete

### Phase 5: Delivery
- [x] Review outputs
- [x] Deliver to user
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 保留现有接口和用户当前工作树 | 用户明确要求只能补全函数体，仓库已有未提交改动 | 
| 在 `AgentState` 增加正式 `topic` 和 `outline` 字段 | 用户要求切断日志反向解析，并让主题可靠流转 |
| 通过 `AgentState.log` 保存写作草稿 | 用户明确禁止动态挂载 `_write_sections` |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| HTML 表格解析将行当成字符串拼接 | 改为按 table -> row -> cell 分组解析 |
| web 检索失败后路由跳过 web 阶段 | 本地检索成功后保持 `RetrieveAgent`，web 成功才转 `WriteAgent` |
| 重试阶段本地检索反复重置计数 | 只在完整检索阶段成功后重置 `retry_count` |
| 覆盖率解析器初始化缩进错误 | 将 `by_task` 移到正常解析路径并通过回归测试 |
