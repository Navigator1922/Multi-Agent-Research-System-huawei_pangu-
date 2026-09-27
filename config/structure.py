from typing import List, Dict
from dataclasses import dataclass, field

@dataclass
class ContextInput:
    context: str
    source_id: str
    url: str
    source_ids: List[str] = field(default_factory=list)

@dataclass
class AgentState:
    status: str = "Running"     # 状态：运行中\已完成\错误
    retry_count: int = 2
    current_agent: str = "PlanAgent"    # 当前 Agent：PlanAgent\RetrieveAgent\WriteAgent\AuditAgent
    overall_steps: int = 0
    total_retries: int = 0      # 重试次数：0\1\2\3
    log: List[str] = field(default_factory=list)
    sub_task: List[str] = field(default_factory=list)
    evidence: List[dict] = field(default_factory=list)      # 格式：List[Dict{sub_task:{source_id:context}}]
    source_metadata: Dict[str, dict] = field(default_factory=dict)
    last_error: str = ""
    draft_sections: Dict[str, str] = field(default_factory=dict)

@dataclass
class SystemOutput:
    final_report: str
    overall_steps: int
    total_retries: int
    coverage_rate: float = 0.0
    baseline_comparison: Dict[str, str] = field(default_factory=dict)
