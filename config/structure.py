from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ContextInput:
    """Normalized input for one research run.

    The first three fields preserve the original project interface. The
    optional fields let local test data and cloud runs share the same entry
    point without changing the Agent classes.
    """

    context: str
    source_id: str = "input"
    url: str = ""
    sources: List[Dict[str, Any]] = field(default_factory=list)
    force_retrieval_failure: bool = False
    timeout_seconds: float = 30.0
    max_retries: int = 2
    log_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentMessage:
    """The shared message protocol used between the four Agents."""

    run_id: str
    step_id: str
    sender: str
    receiver: str
    message_type: str
    task_id: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "success"
    error: Optional[str] = None
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentState:
    status: str = "Running"  # Running\Completed\Error
    retry_count: int = 2
    current_agent: str = "PlanAgent"  # PlanAgent\RetrieveAgent\WriteAgent\AuditAgent
    overall_steps: int = 0
    total_retries: int = 0
    log: List[str] = field(default_factory=list)
    sub_task: List[str] = field(default_factory=list)
    evidence: List[Dict[str, Any]] = field(default_factory=list)

    # Runtime fields added without changing the original state fields above.
    max_retries: int = 2
    run_id: str = field(default_factory=lambda: _new_id("run"))
    input_data: Optional[ContextInput] = None
    report: str = ""
    coverage_rate: float = 0.0
    task_completion_rate: float = 0.0
    audit_result: Dict[str, Any] = field(default_factory=dict)
    messages: List[AgentMessage] = field(default_factory=list)


def record_event(state: AgentState, event: str, **payload: Any) -> None:
    """Append one JSON event to the legacy string log field."""

    record = {
        "time": _now(),
        "run_id": state.run_id,
        "step": state.overall_steps,
        "event": event,
        **payload,
    }
    state.log.append(json.dumps(record, ensure_ascii=False, default=str))


def add_message(
    state: AgentState,
    sender: str,
    receiver: str,
    message_type: str,
    payload: Optional[Dict[str, Any]] = None,
    evidence: Optional[List[Dict[str, Any]]] = None,
    task_id: str = "",
    status: str = "success",
    error: Optional[str] = None,
) -> AgentMessage:
    """Create and log a protocol message while keeping AgentState central."""

    message = AgentMessage(
        run_id=state.run_id,
        step_id=_new_id("step"),
        sender=sender,
        receiver=receiver,
        message_type=message_type,
        task_id=task_id,
        payload=payload or {},
        evidence=evidence or [],
        status=status,
        error=error,
    )
    state.messages.append(message)
    record_event(state, "message", message=message.to_dict())
    return message


@dataclass
class SystemOutput:
    final_report: str
    overall_steps: int
    total_retries: int
    coverage_rate: float = 0.0
    baseline_comparison: Dict[str, str] = field(default_factory=dict)
    task_completion_rate: float = 0.0
    status: str = "Completed"
    run_id: str = ""
    audit_result: Dict[str, Any] = field(default_factory=dict)
    log_path: Optional[str] = None
    logs: List[str] = field(default_factory=list)
    messages: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
