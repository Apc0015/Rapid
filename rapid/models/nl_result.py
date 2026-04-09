from dataclasses import dataclass, field
from typing import List


@dataclass
class NLResult:
    summary: str
    source: str                    # 'rag', 'database', 'direct', 'web', 'merged'
    confidence: float              # composite 0.0 – 1.0
    citations: List[str] = field(default_factory=list)
    dept_tag: str = ""
    governance_log: List[dict] = field(default_factory=list)
