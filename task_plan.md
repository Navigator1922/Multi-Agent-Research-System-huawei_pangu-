# 原始骨架内实现计划

目标：在不改变原始数据类、字段、方法名、输入输出格式和主流程的前提下，补全 `openpangu_qa` 的四个 Agent、数据加载和调度逻辑。

## 阶段

- [complete] 核对恢复后的原始骨架与现有接口
- [complete] 设计不扩展数据结构的最小实现
- [complete] 在原文件内实现四个 Agent、loader 和 main 调度
- [complete] 用标准库完成本地验证，并检查差异

## 不可变约束

- 不新增 `ContextInput`、`AgentState`、`SystemOutput` 字段。
- 不改变字段顺序、方法名、类名、`run_pipeline(data)` 签名或 `main.py` 的公开返回结构。
- 不引入新的运行时框架或必需第三方库。
- 证据只能使用现有的 `AgentState.evidence`；过程信息只能使用现有的 `AgentState.log`。

## 错误记录

| 错误 | 尝试 | 处理 |
|---|---:|---|
| PowerShell 内嵌换行命令被当作字面量 `\\n` | 1 | 改用 PowerShell here-string，项目校验通过 |
