from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

try:
    from utils.data_loader import loader
    from config.structure import (
        AgentState,
        ContextInput,
        SystemOutput,
        add_message,
        record_event,
    )
    from agents.audit_agent import Audit_agent
    from agents.plan_agent import Plan_Agent
    from agents.retrieve_agent import Retrieve_Agent
    from agents.write_agent import Write_Agent
except ModuleNotFoundError:  # Supports `python -m openpangu_qa.main`.
    from .utils.data_loader import loader
    from .config.structure import (
        AgentState,
        ContextInput,
        SystemOutput,
        add_message,
        record_event,
    )
    from .agents.audit_agent import Audit_agent
    from .agents.plan_agent import Plan_Agent
    from .agents.retrieve_agent import Retrieve_Agent
    from .agents.write_agent import Write_Agent


class AgentTimeoutError(TimeoutError):
    """Raised when an Agent exceeds the configured per-call timeout."""


def _execute_with_timeout(
    function: Callable[[AgentState], AgentState],
    state: AgentState,
    timeout_seconds: float,
) -> AgentState:
    # Work on a copy so a timed-out worker cannot mutate the live pipeline
    # state after the dispatcher has scheduled a retry.
    working_state = copy.deepcopy(state)
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(function, working_state)
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError as exc:
        future.cancel()
        raise AgentTimeoutError(
            f"{state.current_agent} 超过 {timeout_seconds:.2f} 秒未完成"
        ) from exc
    finally:
        # Do not block the dispatcher while a timed-out worker unwinds.
        executor.shutdown(wait=False, cancel_futures=True)


def _save_log(state: AgentState, input_data: ContextInput) -> str:
    configured_path = input_data.log_path
    path = Path(configured_path) if configured_path else Path("logs") / f"{state.run_id}.jsonl"
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        for raw_record in state.log:
            try:
                json.loads(raw_record)
                handle.write(raw_record + "\n")
            except (TypeError, json.JSONDecodeError):
                handle.write(
                    json.dumps(
                        {
                            "run_id": state.run_id,
                            "event": "legacy_log",
                            "message": str(raw_record),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
    return str(path)


def _error_result(state: AgentState) -> str:
    last_error = ""
    for item in reversed(state.log):
        try:
            payload = json.loads(item)
        except json.JSONDecodeError:
            continue
        if payload.get("event") == "agent_error":
            last_error = str(payload.get("error") or "")
            break
    suffix = f" 原因: {last_error}" if last_error else ""
    return f"任务未正常完成。最终状态: {state.status}。{suffix}".strip()


def _route(
    state: AgentState,
    planner: Plan_Agent,
    retriever: Retrieve_Agent,
    writer: Write_Agent,
    auditor: Audit_agent,
) -> Tuple[Callable[[AgentState], AgentState], str]:
    routes = {
        "PlanAgent": planner.Split,
        "RetrieveAgent": retriever.retrieve,
        "WriteAgent": writer.write,
        "AuditAgent": auditor.audit,
    }
    function = routes.get(state.current_agent)
    if function is None:
        raise RuntimeError(f"严重的路由错误: 找不到工位 {state.current_agent}")
    return function, state.current_agent


def run_pipeline(data: Any, model: Optional[Any] = None) -> SystemOutput:
    """Run the existing Plan -> Retrieve -> Write -> Audit pipeline.

    ``model`` is optional. Without it the pipeline is deterministic and uses
    the local report template. A cloud Pangu adapter can be injected later
    without changing the four Agent interfaces.
    """

    initial_input: ContextInput = loader(data)
    planner = Plan_Agent(model=model)
    retriever = Retrieve_Agent()
    writer = Write_Agent(model=model)
    auditor = Audit_agent()

    state: AgentState = planner.Planning(initial_input)
    loop_count = 0
    max_loop_count = max(20, len(state.sub_task) * 10)

    while state.status == "Running":
        loop_count += 1
        if loop_count > max_loop_count:
            state.status = "Error"
            record_event(state, "agent_error", error="超过最大调度步数")
            break

        current_name = state.current_agent
        record_event(
            state,
            "agent_attempt",
            agent=current_name,
            attempt=state.max_retries + 2 - state.retry_count,
        )
        try:
            function, _ = _route(state, planner, retriever, writer, auditor)
            state = _execute_with_timeout(
                function,
                state,
                initial_input.timeout_seconds,
            )
            state.retry_count = state.max_retries + 1
        except Exception as exc:
            # The Agent ran in an isolated state copy. Count failed and timed
            # out attempts here because their partial state is discarded.
            state.overall_steps += 1
            state.retry_count -= 1
            record_event(
                state,
                "agent_error",
                agent=current_name,
                error=str(exc),
                retries_used=state.total_retries,
                retries_remaining=max(0, state.retry_count),
            )
            add_message(
                state,
                sender=current_name,
                receiver=current_name,
                message_type="error",
                status="failed",
                error=str(exc),
            )
            if state.retry_count > 0:
                state.total_retries += 1
                record_event(
                    state,
                    "retry_scheduled",
                    agent=current_name,
                    retry_number=state.total_retries,
                )
                state.status = "Running"
                continue
            state.status = "Error"
            break

    baseline = auditor.baseline(state)
    final_report = state.report if state.status == "Completed" else _error_result(state)
    log_path = _save_log(state, initial_input)
    return SystemOutput(
        final_report=final_report,
        coverage_rate=state.coverage_rate,
        task_completion_rate=state.task_completion_rate,
        overall_steps=state.overall_steps,
        total_retries=state.total_retries,
        baseline_comparison=baseline,
        status=state.status,
        run_id=state.run_id,
        audit_result=state.audit_result,
        log_path=log_path,
        logs=list(state.log),
        messages=[message.to_dict() for message in state.messages],
    )


def run_demo() -> None:
    """Run one normal and one forced-failure case for local verification."""

    sources = [
        {
            "source_id": "source_001",
            "title": "人工智能教育应用综述",
            "url": "https://example.com/ai-education",
            "quote": "人工智能在教育中的应用包括个性化学习、智能辅导和学习分析。",
        },
        {
            "source_id": "source_002",
            "title": "教育人工智能风险说明",
            "url": "https://example.com/ai-risk",
            "quote": "教育人工智能需要关注隐私保护、算法偏差、数据安全和教师角色变化。",
        },
    ]
    normal = run_pipeline(
        {
            "context": "人工智能在教育中的应用",
            "sources": sources,
            "log_path": "logs/normal.jsonl",
        }
    )
    failed = run_pipeline(
        {
            "context": "人工智能在教育中的应用",
            "sources": sources,
            "force_retrieval_failure": True,
            "log_path": "logs/retrieval_failure.jsonl",
        }
    )
    print(json.dumps({"normal": normal.to_dict(), "failure": failed.to_dict()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_demo()
