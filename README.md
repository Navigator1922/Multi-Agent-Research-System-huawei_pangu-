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
│   ├── data_loader.py              # 输入数据加载
│   └── source_store.py             # 来源快照和完整性校验
├── data/                            # Wikipedia 真实数据与实验输入
│   ├── wikipedia_sources/           # 每个页面一个完整 JSON 快照
│   ├── wikipedia_manifest.json      # 来源、revision 和校验和
│   ├── normal_input.json            # 正常运行输入
│   └── retrieval_failure.json       # 真实来源解析失败输入
├── scripts/
│   └── collect_wikipedia.py        # 按固定 revision 重建完整 Wikipedia 快照
└── tests/
    ├── test_data_pipeline.py       # 数据完整性和流程测试
    └── test_model_write.py          # 子任务拆分、引用和重试测试
```

## 运行环境

- Python 3.10 或更高版本
- 本地无模型模式只使用 Python 标准库
- 云端模型模式需要已安装 `torch`、`torch-npu` 和 `transformers`

## 数据结构

输入必须包含以下三个字符串字段，并可以用 `source_ids` 选择多个本地来源：

```python
{
    "context": "生成式人工智能的技术基础、应用与风险",
    "source_id": "wiki_generative_ai",
    "source_ids": ["wiki_generative_ai"],
    "url": "https://zh.wikipedia.org/wiki/%E7%94%9F%E6%88%90%E5%BC%8F%E4%BA%BA%E5%B7%A5%E6%99%BA%E6%85%A7"
}
```

`context` 是研究主题，不是来源正文。来源正文只保存在 `data/wikipedia_sources/`
中，由 `RetrieveAgent` 根据 `source_ids` 加载并校验。省略 `source_ids` 时会兼容
使用单个 `source_id`。

也可以直接传入 `ContextInput`：

```python
from config.structure import ContextInput

data = ContextInput(
    context="生成式人工智能的技术基础、应用与风险",
    source_id="wiki_generative_ai",
    url="https://zh.wikipedia.org/wiki/%E7%94%9F%E6%88%90%E5%BC%8F%E4%BA%BA%E5%B7%A5%E6%99%BA%E6%85%A7",
    source_ids=["wiki_generative_ai"],
)
```

也可以把同样的数据保存为本地 JSON 文件，再把文件路径传给 `run_pipeline`：

```json
{
    "context": "生成式人工智能的技术基础、应用与风险",
    "source_id": "wiki_generative_ai",
    "source_ids": ["wiki_generative_ai"],
    "url": "https://zh.wikipedia.org/wiki/%E7%94%9F%E6%88%90%E5%BC%8F%E4%BA%BA%E5%B7%A5%E6%99%BA%E6%85%A7"
}
```

调用方式：

```python
from main import run_pipeline

result = run_pipeline("data/input.json")
print(result.final_report)
```

JSON 文件的顶层必须是对象，并且必须包含 `context`、`source_id`、`url` 三个字符串字段；`source_ids` 为可选字符串数组。

当前实验保存 5 个完整的 Wikipedia revision 快照。`normal_input.json` 只保存研究主题、主来源和 5 个来源 ID；运行时会从来源目录加载全部正文。`retrieval_failure.json` 使用不存在的来源 ID，专门测试真实的来源解析失败。

刷新数据时执行：

```bash
python scripts/collect_wikipedia.py
```

采集脚本按照 manifest 中固定的 `revision_id` 请求 Wikipedia API，不截断正文，
并更新 `stored_characters`、`truncated` 和 `content_sha256`。运行前后的来源可以用
测试命令检查一致性。

## 运行示例

在 `openpangu_qa` 目录下执行：

```bash
python -c "from main import run_pipeline; r = run_pipeline({'context': '生成式人工智能的技术基础、应用与风险', 'source_id': 'wiki_generative_ai', 'source_ids': ['wiki_generative_ai'], 'url': 'https://zh.wikipedia.org/wiki/%E7%94%9F%E6%88%90%E5%BC%8F%E4%BA%BA%E5%B7%A5%E6%99%BA%E6%85%A7'}); print(r.final_report); print(r.coverage_rate)"
```

使用本次构建的真实 Wikipedia 数据：

```bash
python -c "from main import run_pipeline; r = run_pipeline('data/normal_input.json'); print(r.final_report); print('覆盖率:', r.coverage_rate)"
```

运行检索失败测试：

```bash
python -c "from main import run_pipeline; r = run_pipeline('data/retrieval_failure.json'); print(r.final_report); print('重试次数:', r.total_retries)"
```

运行数据测试：

```bash
python -m unittest discover -s tests -v
```

从项目父目录以包方式运行：

```bash
python -c "from openpangu_qa.main import run_pipeline; r = run_pipeline({'context': '生成式人工智能的技术基础、应用与风险', 'source_id': 'wiki_generative_ai', 'source_ids': ['wiki_generative_ai'], 'url': 'https://zh.wikipedia.org/wiki/%E7%94%9F%E6%88%90%E5%BC%8F%E4%BA%BA%E5%B7%A5%E6%99%BA%E6%85%A7'}); print(r.final_report)"
```

## 工作流程

```text
ContextInput
    ↓
PlanAgent       拆分至少三个子任务
    ↓
RetrieveAgent   按 source_ids 加载并校验完整来源证据
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
            "wiki_generative_ai": "来源内容"
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
而是记录原始返回并进入重试。模型模式下，WriteAgent 会为每个子任务单独调用一次模型；
模型只负责正文，系统负责组装小节标题、真实来源引用和来源列表，因此不会因为模型漏写
`[source_id]` 而丢失引用。已经成功生成的小节会保存在 AgentState 中，重试时只重新生成
失败的小节，并把上一次错误反馈注入提示词。适配器检测到输出达到 `max_new_tokens` 时
会将其视为疑似截断并触发修复重试。

撰写 Agent 的提示词会动态注入当前真实子任务和来源正文片段，不会使用“原文任务1”或
通用来源编号作为输出模板；完整来源仍保存在已校验快照中，提示词只使用受控长度片段
以避免上下文过长。

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
export PANGU_MAX_NEW_TOKENS=1024
export PANGU_USE_FUSED_ATTN=0
python -c "from main import run_pipeline; r = run_pipeline('data/input.json'); print(r.final_report); print(r.coverage_rate)"
```

也可以使用云端已有的 7B 模型目录：

```bash
export PANGU_MODEL_PATH=/opt/pangu/openPangu-Embedded-7B-V1.1
```

适配器使用 `AutoTokenizer.from_pretrained` 和 `AutoModelForCausalLM.from_pretrained` 加载本地模型目录，并自动优先选择可用的 Ascend NPU、CUDA 或 CPU。当前课程环境中的 openPangu 自定义代码会默认启用 NPU 融合 attention，但该算子实际推理时报 `aclnnFusedInferAttentionOnScoreV3` 错误，因此适配器默认关闭融合 attention，改用模型自带的 `eager` 实现。只有在确认 CANN、`torch-npu` 与模型版本兼容后，才设置 `PANGU_USE_FUSED_ATTN=1`。

模型目录必须已经存在于云端，代码仓库只保存适配逻辑，不保存模型权重。模型加载成功不代表推理成功；运行时应检查是否出现 `模型推理失败`，以及最终是否生成了非空子任务和报告。
