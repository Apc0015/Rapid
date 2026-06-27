"""
bid_selector.py — Extracted bidding logic for MasterPlanner.
Responsible for: filtering eligible bids, selecting winners, flagging gaps.
"""

import logging
from typing import Dict, List, Tuple, Optional
from models.bid_object import BidObject
import config

logger = logging.getLogger(__name__)


class BidSelector:
    """Encapsulates bid selection logic: eligibility, preference, tie-breaking."""

    @staticmethod
    def select_winner(
        sub_query: str,
        dept_hint: Optional[str],
        all_bids: List[BidObject],
    ) -> Tuple[Optional[str], bool]:
        """
        Select a single winning agent for a sub-query.

        Returns:
            (winning_agent_id, is_gap_flagged)
            If no qualifying bid: (None, True)
            Otherwise: (agent_id, False)
        """
        # 1. Filter candidates that can handle the query
        eligible = [b for b in all_bids if b.can_handle]

        # 2. Prefer dept-hinted agent if it qualifies
        if dept_hint:
            dept_bids = [b for b in eligible if b.agent_id == dept_hint]
            if dept_bids:
                eligible = dept_bids + [b for b in eligible if b.agent_id != dept_hint]

        # 3. Check minimum confidence threshold
        qualifying = [b for b in eligible if b.confidence >= config.MIN_BID_CONF]
        if not qualifying:
            logger.warning(
                f"No qualifying bid for sub-query: '{sub_query[:60]}' — gap flagged"
            )
            return None, True

        # 4. Sort by confidence (desc), then token count (asc)
        winner = sorted(qualifying, key=lambda b: (-b.confidence, b.estimated_tokens))[0]
        logger.info(
            f"Bid winner: {winner.agent_id} "
            f"(confidence={winner.confidence:.2f}, tokens={winner.estimated_tokens})"
        )
        return winner.agent_id, False

    @staticmethod
    def select_winners_batch(
        sub_queries: List[dict],
        bids_per_subquery: Dict[str, List[BidObject]],
    ) -> Tuple[Dict[str, Optional[str]], List[str]]:
        """
        Select winners for all sub-queries.

        Returns:
            (assignments: {sub_query: agent_id or None}, gaps: [sub_query, ...])
        """
        assignments: Dict[str, Optional[str]] = {}
        gaps: List[str] = []

        for sq in sub_queries:
            key = sq["sub_query"]
            dept_hint = sq.get("dept")
            all_bids = bids_per_subquery.get(key, [])

            winner_id, is_gap = BidSelector.select_winner(key, dept_hint, all_bids)
            assignments[key] = winner_id
            if is_gap:
                gaps.append(key)

        return assignments, gaps
