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
- 本地无模型模式只使用 Python 标准库
- 云端模型模式需要已安装 `torch`、`torch-npu` 和 `transformers`

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

也可以把同样的数据保存为本地 JSON 文件，再把文件路径传给 `run_pipeline`：

```json
{
    "context": "人工智能在教育中的应用",
    "source_id": "source_001",
    "url": "https://example.com/source"
}
```

调用方式：

```python
from main import run_pipeline

result = run_pipeline("data/input.json")
print(result.final_report)
```

JSON 文件的顶层必须是对象，并且必须包含 `context`、`source_id`、`url` 三个字符串字段。

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

本项目通过 `utils/model_adapter.py` 可选接入 openPangu，不改变原始数据类、证据格式和 `run_pipeline(data)` 接口。

本地运行时不设置 `PANGU_MODEL_PATH`，规划和撰写 Agent 使用确定性逻辑；云端运行时设置模型目录，规划 Agent 和撰写 Agent 会共享同一个盘古模型实例。

Linux 云端示例：

```bash
export PANGU_MODEL_PATH=/opt/pangu/openPangu-Embedded-1B-V1.1
export PANGU_DEVICE=auto
export PANGU_MAX_NEW_TOKENS=512
python -c "from main import run_pipeline; r = run_pipeline('data/input.json'); print(r.final_report); print(r.coverage_rate)"
```

也可以使用云端已有的 7B 模型目录：

```bash
export PANGU_MODEL_PATH=/opt/pangu/openPangu-Embedded-7B-V1.1
```

适配器使用 `AutoTokenizer.from_pretrained` 和 `AutoModelForCausalLM.from_pretrained` 加载本地模型目录，并自动优先选择可用的 Ascend NPU、CUDA 或 CPU。模型目录必须已经存在于云端，代码仓库只保存适配逻辑，不保存模型权重。
