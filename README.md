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
├── utils/
    └── data_loader.py              # 输入数据加载
└── data/                            # Wikipedia 真实数据与实验输入
    ├── wikipedia_sources/           # 每个页面一个 JSON 来源
    ├── wikipedia_manifest.json      # 来源与版本信息
    ├── normal_input.json            # 正常运行输入
    └── retrieval_failure.json       # 检索失败输入
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

当前实验采用单来源方案，因此每个 Wikipedia 页面单独保存为一个 JSON 文件。`normal_input.json` 选用“生成式人工智能”页面，其他页面保存在 `data/wikipedia_sources/` 中备用。

## 运行示例

在 `openpangu_qa` 目录下执行：

```bash
python -c "from main import run_pipeline; r = run_pipeline({'context': '人工智能在教育中的应用', 'source_id': 'source_001', 'url': 'https://example.com/source'}); print(r.final_report); print(r.coverage_rate)"
```

使用本次构建的真实 Wikipedia 数据：

```bash
python -c "from main import run_pipeline; r = run_pipeline('data/normal_input.json'); print(r.final_report); print('覆盖率:', r.coverage_rate)"
```

运行检索失败测试：

```bash
python -c "from main import run_pipeline; r = run_pipeline('data/retrieval_failure.json'); print(r.final_report); print('重试次数:', r.total_retries)"
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
- `baseline_comparison`：独立执行一次单 Agent 撰写后的对比结果；其中
  `executed` 表示是否真正执行，`status` 表示该次 baseline 是否成功，
  `model_used` 表示是否调用了盘古模型。

单次 Agent 执行失败时，系统最多重试两次。检索阶段如果 `source_id` 为空，会被视为检索失败并进入重试流程。
启用盘古模型后，规划结果必须由模型返回至少三个有效子任务；解析失败不会静默替换为固定子任务，
而是记录原始返回并进入重试。撰写结果也必须逐个包含子任务小节及其对应来源引用，
否则会进入撰写阶段重试。

撰写 Agent 的提示词会动态注入本次运行的真实子任务标题、来源编号和来源 URL，
不会使用“原文任务1”或通用来源编号作为输出模板，避免模型照抄占位符。

`baseline_comparison` 不是从多 Agent 报告推导出来的伪基线。主流程结束后，
`Audit_agent.baseline` 会使用相同输入独立执行一次单 Agent 撰写，并单独统计步骤数、重试次数和引用覆盖率。

## openPangu 云端说明

本项目通过 `utils/model_adapter.py` 可选接入 openPangu，不改变原始数据类、证据格式和 `run_pipeline(data)` 接口。

本地运行时不设置 `PANGU_MODEL_PATH`，规划和撰写 Agent 使用确定性逻辑，baseline 也会独立执行一次本地单 Agent 撰写；
云端运行时设置模型目录，规划 Agent、撰写 Agent 和 baseline 会共享同一个盘古模型实例，但每个阶段仍然独立调用模型。

Linux 云端示例：

```bash
export PANGU_MODEL_PATH=/opt/pangu/openPangu-Embedded-1B-V1.1
export PANGU_DEVICE=auto
export PANGU_MAX_NEW_TOKENS=512
export PANGU_USE_FUSED_ATTN=0
python -c "from main import run_pipeline; r = run_pipeline('data/input.json'); print(r.final_report); print(r.coverage_rate)"
```

也可以使用云端已有的 7B 模型目录：

```bash
export PANGU_MODEL_PATH=/opt/pangu/openPangu-Embedded-7B-V1.1
```

适配器使用 `AutoTokenizer.from_pretrained` 和 `AutoModelForCausalLM.from_pretrained` 加载本地模型目录，并自动优先选择可用的 Ascend NPU、CUDA 或 CPU。当前课程环境中的 openPangu 自定义代码会默认启用 NPU 融合 attention，但该算子实际推理时报 `aclnnFusedInferAttentionOnScoreV3` 错误，因此适配器默认关闭融合 attention，改用模型自带的 `eager` 实现。只有在确认 CANN、`torch-npu` 与模型版本兼容后，才设置 `PANGU_USE_FUSED_ATTN=1`。

模型目录必须已经存在于云端，代码仓库只保存适配逻辑，不保存模型权重。模型加载成功不代表推理成功；运行时应检查是否出现 `模型推理失败`，以及最终是否生成了非空子任务和报告。
