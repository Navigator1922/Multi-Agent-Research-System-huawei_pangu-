# 核对记录

- 当前工作目录为 `openpangu_qa`。
- 当前源码已恢复为骨架状态：四个 Agent 方法主体为 `pass`，`utils/data_loader.py` 为空，`main.py` 仍有基础路由框架。
- 不采用此前实现中的 `report`、`sources`、`metadata`、`max_retries`、`timeout_seconds`、`status` 等新增字段，除非它们本来就在恢复后的骨架中。
- `HEAD` 与当前工作树不同，不能直接用 `HEAD` 覆盖当前文件；当前文件是用户要求保留的恢复版本。
- `v0` 的 `AgentState` 没有输入数据或报告字段，因此输入记录和报告只能分别放入既有 `log: List[str]`；这保持了数据类字段完全不变。
- `v0` 的 `evidence` 注释定义为 `List[Dict{sub_task: {source_id: context}}]`，实现严格采用该形状。
- `retry_count` 按“剩余重试次数”解释：初始为 2，失败后允许两次重试；因此失败路径总执行 3 次，`total_retries` 为 2。
