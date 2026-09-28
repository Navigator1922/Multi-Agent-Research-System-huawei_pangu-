# Task Plan: Complete multi-agent research report agents

## Goal
补全所有占位实现，保持现有接口和数据结构不变，并验证多智能体报告生成主流程及异常传播行为。

## Next Step
无，任务已完成。

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
- [x] Confirm existing project structure
- **Status:** complete

### Phase 3: Implementation
- [x] Execute the plan
- [x] Write to files before executing
- **Status:** complete

### Phase 4: Testing & Verification
- [x] Verify requirements met
- [x] Document test results
- **Status:** complete

### Phase 5: Delivery
- [x] Review outputs
- [x] Deliver to user
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 保留现有接口和用户当前工作树 | 用户明确要求只能补全函数体，仓库已有未提交改动 | 

## Errors Encountered
| Error | Resolution |
|-------|------------|
| HTML 表格解析将行当成字符串拼接 | 改为按 table -> row -> cell 分组解析 |
| web 检索失败后路由跳过 web 阶段 | 本地检索成功后保持 `RetrieveAgent`，web 成功才转 `WriteAgent` |
| 重试阶段本地检索反复重置计数 | 只在完整检索阶段成功后重置 `retry_count` |
