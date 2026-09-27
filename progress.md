# Progress Log

## Session: 2026-09-27

### Current Status
- **Phase:** 5 - Delivery
- **Started:** 2026-09-27

### Actions Taken
- 确认外层目录内容，发现实际代码在 `openpangu_qa`。
- 阅读并初始化持久化研究计划文件。
- 初步确认项目包含 Python 入口、配置、数据和结果目录。
- 阅读 `README.md` 与 `main.py`，确认公开入口、Agent 路由、重试、报告提取和 baseline 行为。
- 阅读 `config/structure.py`、四个 Agent 以及两个 utility，完成核心数据契约、证据生成、报告校验、审核和模型适配链路的初步梳理。
- 新任务确认：数据可靠性修复需要同时调整来源快照、输入 fixture、manifest 校验和 RetrieveAgent，不能只扩大截断长度。
- 核对样例输入、Wikipedia manifest 和历史结果；确认来源数据为预先抓取并截断的本地 JSON。
- 实际运行正常输入、检索失败输入和内存字典输入，分别验证成功、重试失败和成功分支。
- 完成 Python 3.11.7 的 `compileall` 检查；从父目录进行包方式导入并运行成功。
- 补充数据来源范围、无 CLI 入口、无独立测试套件和云端模型未实测等限制。
- 增加 `utils/source_store.py`，按 manifest 校验来源文件的 source_id、URL、页面 ID、revision、字符数和 SHA-256。
- 增加 `scripts/collect_wikipedia.py`，按固定 revision 和 `variant=zh-cn` 重新抓取完整正文，不再截断。
- 将正常输入改为研究主题 + 5 个 source_ids，将失败输入改为不存在的 source_id；RetrieveAgent 现在真实加载来源快照。
- 更新写作和 baseline 的多来源 URL/摘要行为，保留旧版三参数 ContextInput 的单来源兼容。
- 增加 5 项数据和流程测试，全部通过。
- 收到模型生成可靠性修复请求，重新读取当前工作区；发现来源快照/元数据相关改动已存在，后续将基于当前版本继续实现，不覆盖这些改动。
- 为 `AgentState` 增加最近错误和已完成小节缓存；主流程重试时保存错误反馈。
- 将模型写作改为逐子任务调用，系统确定性组装标题、引用和来源列表，并限制提示词中的来源片段长度。
- 将模型默认 `max_new_tokens` 调整为 1024，并记录是否触及输出上限；规划、写作和 baseline 均能识别相应错误。
- 为 baseline 补齐缺失来源标记，并增加模型写作和主流程自适应重试回归测试。

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| `run_pipeline('data/normal_input.json')` | 完成流水线并有完整引用覆盖 | 4 steps, 0 retries, coverage 1.0, baseline completed | PASS |
| `run_pipeline('data/retrieval_failure.json')` | 检索失败并耗尽重试 | 4 steps, 2 retries, coverage 0.0, Error result | PASS |
| `run_pipeline({...})` | 支持字典输入并完成 | 4 steps, 0 retries, coverage 1.0 | PASS |
| `python scripts/collect_wikipedia.py` | 按固定 revision 刷新完整来源 | 5 sources refreshed, no truncation | PASS |
| `python -m unittest discover -s tests -v` | 数据完整性和流程回归通过 | 5 tests passed | PASS |
| `python -m unittest discover -s tests -v` | 写作拆分、引用和反馈重试通过 | 8 tests passed | PASS |
| 父目录 `from openpangu_qa.main import run_pipeline` | 包方式正常运行 | 4 steps, 0 retries, coverage 1.0 | PASS |
| `python -m compileall -q .` | 源码无语法错误 | PASS | PASS |

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|

### Errors
| Error | Resolution |
|-------|------------|
| 初次批量更新规划文件时路径写错 | 改用项目内绝对路径重新更新 |
| Windows 默认代码页显示中文输出乱码 | 使用数值指标和源码行为完成验证，未影响流程判断 |
