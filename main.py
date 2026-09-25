from utils.data_loader import loader
from config.structure import ContextInput, SystemOutput, AgentState
from agents.plan_agent import Plan_Agent
from agents.retrieve_agent import Retrieve_Agent
from agents.write_agent import Write_Agent
from agents.audit_agent import Audit_agent

def run_pipeline(data) -> SystemOutput:
    initial_input: ContextInput = loader(data)
    
    planner = Plan_Agent()
    retriever = Retrieve_Agent()
    writer = Write_Agent()
    auditor = Audit_agent()
    
    state: AgentState = planner.Planning(initial_input)

    while state.status == "Running" and state.retry_count > 0:
        
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
            state.retry_count -= 1
            state.total_retries += 1
            state.log.append(f"工位 {state.current_agent} 执行异常: {str(e)}")
            
    if state.status != "Completed":
        final_report = f"任务未正常完成。最终状态: {state.status}，日志: {state.log}"
    else:
        final_report = "最终提取的报告内容..."
        
    baseline = auditor.baseline(state)

    return SystemOutput(
        final_report=final_report,
        coverage_rate=coverage_rate,
        overall_steps=state.overall_steps,
        total_retries=state.total_retries,
        baseline_comparison=baseline
    )