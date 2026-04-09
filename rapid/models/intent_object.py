from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class IntentObject:
    fields_needed: List[str]           # column/concept names requested
    filters: Dict[str, Any]            # e.g. {"department": "Engineering"}
    aggregation: Optional[str]         # "COUNT", "AVG", "SUM", None
    sort: Optional[str] = None         # e.g. "salary DESC"
    limit: Optional[int] = None
    raw_query: str = ""
