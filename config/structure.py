from typing import List, Dict, Any
from dataclasses import dataclass, field

@dataclass
class DataBlock:
    type: str           # 枚举值："text" (纯文本), "image" (图片URL/路径), "table" (Markdown/CSV格式)
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)  # 存放原始页码、所属章节等上下文信息

@dataclass
class ContextInput:
    topic: str                 # 提取出的核心主题（专供 PlanAgent 进行无上下文盲写规划）
    db_collection_id: str      # 核心！向量库的命名空间/集合ID（告诉 RetrieveAgent 去哪找数据）
    source_id: str
    url: str

@dataclass
class AgentState:
    status: str = "Running"
    retry_count: int = 2
    current_agent: str = "PlanAgent"
    overall_steps: int = 0
    total_retries: int = 0
    
    db_collection_id: str = "" 
    
    log: List[str] = field(default_factory=list)
    sub_task: List[str] = field(default_factory=list)

    evidence: List[Dict[str, Dict[str, List[DataBlock]]]] = field(default_factory=list)

    audit_metrics: Dict[str, float] = field(default_factory=lambda: {
        "coverage_rate": 0.0,
        "ai_flavor_rate": 0.0
    })

@dataclass
class SystemOutput:
    final_report: str
    overall_steps: int
    total_retries: int
    coverage_rate: float = 0.0
    ai_flavor_rate: float = 0.0  # 最终输出暴露 AI 味浓度指标
    baseline_comparison: Dict[str, str] = field(default_factory=dict)