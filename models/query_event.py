from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime


@dataclass
class QueryEvent:
    query_id: str
    user_id: str
    timestamp: datetime
    raw_query: str
    intent_class: str              # TRIVIAL / SINGLE_DEPT / MULTI_DEPT / AMBIGUOUS
    depts_activated: List[str] = field(default_factory=list)
    agents_selected: List[str] = field(default_factory=list)
    bid_scores: Dict[str, float] = field(default_factory=dict)
    composite_confidence: float = 0.0
    answer_delivered: bool = False
    fallback_triggered: bool = False
