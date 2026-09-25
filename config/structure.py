from typing import List, Dict
from dataclasses import dataclass, field

@dataclass
class ContextInput:
    context: str
    source_id: str
    url: str

@dataclass
class AgentState:
    status: str = "Running"     # Running\Completed\Error
    retry_count: int = 2
    current_agent: str = "PlanAgent"    # PlanAgent\RetrieveAgent\WriteAgent\AuditAgent
    overall_steps: int = 0
    total_retries: int = 0      #0\1\2\3
    log: List[str] = field(default_factory=list)
    sub_task: List[str] = field(default_factory=list)
    evidence: List[dict] = field(default_factory=list)      #List[Dict{sub_task:{source_id:context}}]

@dataclass
class SystemOutput:
    final_report: str
    overall_steps: int
    total_retries: int 
    coverage_rate: float = 0.0
    baseline_comparison: Dict[str, str] = field(default_factory=dict)