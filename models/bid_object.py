from dataclasses import dataclass, field


@dataclass
class BidObject:
    agent_id: str
    can_handle: bool
    confidence: float          # 0.0 – 1.0
    estimated_tokens: int
    needs_web_fallback: bool = False
    caveats: str = ""
