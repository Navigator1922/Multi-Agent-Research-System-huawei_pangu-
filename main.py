import json

try:
    from utils.data_loader import loader
    from config.structure import ContextInput, SystemOutput, AgentState
    from agents.plan_agent import Plan_Agent
    from agents.retrieve_agent import Retrieve_Agent
    from agents.write_agent import Write_Agent
    from agents.audit_agent import Audit_agent
    from utils.model_adapter import load_model_from_environment
except ModuleNotFoundError:
    from .utils.data_loader import loader
    from .config.structure import ContextInput, SystemOutput, AgentState
    from .agents.plan_agent import Plan_Agent
    from .agents.retrieve_agent import Retrieve_Agent
    from .agents.write_agent import Write_Agent
    from .agents.audit_agent import Audit_agent
    from .utils.model_adapter import load_model_from_environment

def run_pipeline(data, data_dir="./data") -> SystemOutput:
    # 1. 解析入口数据，存入向量库并生成凭证 (ContextInput)
    initial_input: ContextInput = loader(data)
    
    # 2. 初始化环境与智能体
    model = load_model_from_environment()
    planner = Plan_Agent(model=model)
    retriever = Retrieve_Agent(data_dir=data_dir)
    writer = Write_Agent(model=model)
    auditor = Audit_agent(model=model)

    # 3. 规划阶段 (Plan)
    # 先进行大纲规划，再切分具体子任务
    state: AgentState = planner.Programme(initial_input)
    if state.status == "Running":
        state = planner.Split(state)

    # 4. 核心状态机循环
    while state.status == "Running":
        try:
            if state.current_agent == "RetrieveAgent":
                # 双路检索策略：本地向量检索 + Web补充检索
                state = retriever.retrieve(state)
                state = retriever.web_search(state)
                
                # 手动推进状态机（建议在 Agent 内部完成，此处作为双保险）
                state.current_agent = "WriteAgent"

            elif state.current_agent == "WriteAgent":
                # 多模态报告生产流水线
                state = writer.frame(state)   # 搭建章节骨架
                state = writer.text(state)    # 撰写核心文本
                state = writer.image(state)   # 匹配并插入图片
                state = writer.table(state)   # 渲染数据表格
                
                state.current_agent = "AuditAgent"

            elif state.current_agent == "AuditAgent":
                # 多维度审核机制
                state = auditor.kpi(state)    # 计算引用覆盖率 (coverage_rate)
                state = auditor.audit(state)  # 综合评估 AI 味浓度并决定是否通过

            else:
                state.status = "Error"
                state.log.append(f"严重的路由错误: 找不到工位 {state.current_agent}")

        except Exception as e:
            # 异常捕获与重试退避机制
            current_agent = state.current_agent
            state.log.append(f"工位 {current_agent} 执行异常: {str(e)}")
            if state.retry_count > 0:
                state.retry_count -= 1
                state.total_retries += 1
                state.log.append(
                    f"工位 {current_agent} 将重试，剩余重试次数: {state.retry_count}"
                )
            else:
                state.status = "Error"
                state.log.append(f"工位 {current_agent} 已达到最大重试次数")

    # 5. 提取最终报告与状态日志
    report = _latest_report(state)
    if state.status == "Completed" and report:
        final_report = report
    elif report:
        final_report = report + "\n\n任务未正常完成。最终状态: " + state.status
    else:
        final_report = f"任务未正常完成。最终状态: {state.status}，日志: {state.log[-5:]}"

    # 6. 返回多维度系统输出
    return SystemOutput(
        final_report=final_report,
        overall_steps=state.overall_steps,
        total_retries=state.total_retries,
        # 新架构下，指标从 audit_metrics 字典中安全提取
        coverage_rate=state.audit_metrics.get("coverage_rate", 0.0),
        ai_flavor_rate=state.audit_metrics.get("ai_flavor_rate", 0.0),
        baseline_comparison={}  # 废弃原有的无用基线，预留给未来真正的评测框架
    )

def _latest_report(state: AgentState) -> str:
    """从 AgentState.log 中找到最后一条报告并返回报告正文。"""
    report = ""
    for item in state.log:
        try:
            record = json.loads(item)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(record, dict) and record.get("type") == "report":
            report = str(record.get("content", ""))
    return report
