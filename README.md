# openpangu_qa

这是 openPangu 第九题的多 Agent 调研报告生成与审核系统。项目按照原始骨架实现，包含规划、检索、撰写和审核四个 Agent。

## 项目结构

```text
openpangu_qa/
├── main.py                         # 主流程与 Agent 调度
├── config/
│   └── structure.py                # 三个原始数据结构
├── agents/
│   ├── plan_agent.py               # 规划 Agent
│   ├── retrieve_agent.py           # 检索 Agent
│   ├── write_agent.py              # 撰写 Agent
│   └── audit_agent.py              # 审核 Agent
└── utils/
    └── data_loader.py              # 输入数据加载
```

## 运行环境

- Python 3.10 或更高版本
- 只使用 Python 标准库
- 当前本地版本不要求安装第三方 Python 包

## 数据结构

输入必须包含以下三个字符串字段：

```python
{
    "context": "人工智能在教育中的应用",
    "source_id": "source_001",
    "url": "https://example.com/source"
}
```

也可以直接传入 `ContextInput`：

```python
from config.structure import ContextInput

data = ContextInput(
    context="人工智能在教育中的应用",
    source_id="source_001",
    url="https://example.com/source",
)
```

## 运行示例

在 `openpangu_qa` 目录下执行：

```bash
python -c "from main import run_pipeline; r = run_pipeline({'context': '人工智能在教育中的应用', 'source_id': 'source_001', 'url': 'https://example.com/source'}); print(r.final_report); print(r.coverage_rate)"
```

从项目父目录以包方式运行：

```bash
python -c "from openpangu_qa.main import run_pipeline; r = run_pipeline({'context': '人工智能在教育中的应用', 'source_id': 'source_001', 'url': 'https://example.com/source'}); print(r.final_report)"
```

## 工作流程

```text
ContextInput
    ↓
PlanAgent       拆分至少三个子任务
    ↓
RetrieveAgent   为每个子任务保留来源证据
    ↓
WriteAgent      生成带来源引用的调研报告
    ↓
AuditAgent      检查证据和引用覆盖率
    ↓
SystemOutput    返回报告与评测指标
```

Agent 之间通过 `AgentState` 传递状态。证据保持原始骨架定义的格式：

```python
[
    {
        "子任务": {
            "source_001": "来源内容"
        }
    }
]
```

## 返回结果

`run_pipeline` 返回 `SystemOutput`，包含：

- `final_report`：最终调研报告或失败信息
- `overall_steps`：完成的 Agent 步骤数
- `total_retries`：累计重试次数
- `coverage_rate`：子任务引用覆盖率
- `baseline_comparison`：与单 Agent 一次性撰写方式的对比结果

单次 Agent 执行失败时，系统最多重试两次。检索阶段如果 `source_id` 为空，会被视为检索失败并进入重试流程。

## openPangu 云端说明

当前版本首先保证本地标准库流程可运行。原始骨架没有模型字段或模型构造接口，因此没有擅自增加盘古模型适配器。云端接入 openPangu 时，应在不破坏现有数据结构的前提下，为 Agent 明确增加模型调用接口，再替换规划、撰写等需要生成能力的内部逻辑。
