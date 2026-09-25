import json

try:
    from utils.data_loader import loader
    from config.structure import ContextInput, SystemOutput, AgentState
    from agents.plan_agent import Plan_Agent
    from agents.retrieve_agent import Retrieve_Agent
    from agents.write_agent import Write_Agent
    from agents.audit_agent import Audit_agent
except ModuleNotFoundError:
    from .utils.data_loader import loader
    from .config.structure import ContextInput, SystemOutput, AgentState
    from .agents.plan_agent import Plan_Agent
    from .agents.retrieve_agent import Retrieve_Agent
    from .agents.write_agent import Write_Agent
    from .agents.audit_agent import Audit_agent

def run_pipeline(data) -> SystemOutput:
    initial_input: ContextInput = loader(data)
    planner = Plan_Agent()
    retriever = Retrieve_Agent()
    writer = Write_Agent()
    auditor = Audit_agent()

    state: AgentState = planner.Planning(initial_input)
    coverage_rate = 0.0

    while state.status == "Running":
        try:
            if state.current_agent == "RetrieveAgent":
                state = retriever.retrieve(state)

            elif state.current_agent == "WriteAgent":
                state = writer.write(state)
                coverage_rate = writer.calculate(state)

            elif state.current_agent == "AuditAgent":
                state = auditor.audit(state)

            else:
                state.status = "Error"
                state.log.append(f"严重的路由错误: 找不到工位 {state.current_agent}")

        except Exception as e:
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

    report = _latest_report(state)
    if state.status == "Completed" and report:
        final_report = report
    elif report:
        final_report = report + "\n\n任务未正常完成。最终状态: " + state.status
    else:
        final_report = f"任务未正常完成。最终状态: {state.status}，日志: {state.log}"

    baseline = auditor.baseline(state)

    return SystemOutput(
        final_report=final_report,
        coverage_rate=coverage_rate,
        overall_steps=state.overall_steps,
        total_retries=state.total_retries,
        baseline_comparison=baseline
    )


def _latest_report(state: AgentState) -> str:
    """读取保存在原始字符串日志字段中的报告。"""

    report = ""
    for item in state.log:
        try:
            record = json.loads(item)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(record, dict) and record.get("type") == "report":
            report = str(record.get("content", ""))
    return report
