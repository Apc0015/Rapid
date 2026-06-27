from __future__ import annotations
"""
CalculationTool — deterministic financial and operational formulas.
No LLM needed — pure Python math that returns formatted NL strings.
"""

import logging
from agents.tools.base_tool import BaseTool

logger = logging.getLogger(__name__)

# ── Supported formulas ────────────────────────────────────────────────────────
_FORMULAS = {
    "variance", "roi", "yoy_change", "burn_rate", "cagr",
    "margin", "headcount_change", "cost_per_unit", "churn_rate",
    "nps_score", "conversion_rate", "utilisation_rate",
}


class CalculationTool(BaseTool):
    name = "calculate"
    description = (
        "Run a named financial or operational formula. "
        "Supported: variance, roi, yoy_change, burn_rate, cagr, margin, "
        "headcount_change, cost_per_unit, churn_rate, nps_score, "
        "conversion_rate, utilisation_rate."
    )

    async def run(self, formula: str, params: dict) -> str:
        """
        Execute a named formula and return a formatted NL result.
        params keys depend on the formula — see each method below.
        """
        formula = formula.lower().strip()
        if formula not in _FORMULAS:
            return f"Unknown formula '{formula}'. Supported: {', '.join(sorted(_FORMULAS))}."

        try:
            fn = getattr(self, f"_calc_{formula}")
            return fn(**params)
        except TypeError as exc:
            logger.warning(f"CalculationTool bad params for '{formula}': {exc}")
            return f"Could not compute '{formula}': missing or invalid parameters."
        except ZeroDivisionError:
            return f"Cannot compute '{formula}': division by zero (check denominator)."
        except Exception as exc:
            logger.error(f"CalculationTool error for '{formula}': {exc!r}")
            return f"Calculation error for '{formula}'."

    # ── Formulas ──────────────────────────────────────────────────────────────

    def _calc_variance(self, actual: float, budget: float, label: str = "metric") -> str:
        diff = actual - budget
        pct  = (diff / budget * 100) if budget else 0.0
        sign = "+" if diff >= 0 else ""
        return (
            f"{label.title()} variance: actual {actual:,.2f} vs budget {budget:,.2f} "
            f"→ {sign}{diff:,.2f} ({sign}{pct:.1f}%)."
        )

    def _calc_roi(self, gain: float, cost: float, label: str = "investment") -> str:
        roi = (gain - cost) / cost * 100 if cost else 0.0
        return f"ROI on {label}: {roi:.1f}% (gain {gain:,.2f} on cost {cost:,.2f})."

    def _calc_yoy_change(self, current: float, prior: float, label: str = "metric") -> str:
        change = ((current - prior) / prior * 100) if prior else 0.0
        direction = "up" if change >= 0 else "down"
        return (
            f"{label.title()} YoY: {current:,.2f} vs prior year {prior:,.2f} "
            f"→ {direction} {abs(change):.1f}%."
        )

    def _calc_burn_rate(self, total_spend: float, periods: int, label: str = "spend") -> str:
        rate = total_spend / periods if periods else 0.0
        return f"Burn rate ({label}): {rate:,.2f} per period over {periods} periods."

    def _calc_cagr(self, start_value: float, end_value: float, years: float) -> str:
        if start_value <= 0 or years <= 0:
            return "CAGR: insufficient data (start value and years must be positive)."
        cagr = ((end_value / start_value) ** (1 / years) - 1) * 100
        return f"CAGR over {years:.1f} years: {cagr:.2f}% (from {start_value:,.2f} to {end_value:,.2f})."

    def _calc_margin(self, revenue: float, cost: float, label: str = "gross") -> str:
        margin = ((revenue - cost) / revenue * 100) if revenue else 0.0
        return f"{label.title()} margin: {margin:.1f}% (revenue {revenue:,.2f}, cost {cost:,.2f})."

    def _calc_headcount_change(self, current: int, prior: int, label: str = "headcount") -> str:
        diff   = current - prior
        pct    = (diff / prior * 100) if prior else 0.0
        sign   = "+" if diff >= 0 else ""
        return f"{label.title()} change: {current} vs prior {prior} → {sign}{diff} ({sign}{pct:.1f}%)."

    def _calc_cost_per_unit(self, total_cost: float, units: float, label: str = "unit") -> str:
        cpu = total_cost / units if units else 0.0
        return f"Cost per {label}: {cpu:,.2f} (total cost {total_cost:,.2f} / {units:,.0f} units)."

    def _calc_churn_rate(self, churned: float, total: float, period: str = "period") -> str:
        rate = (churned / total * 100) if total else 0.0
        return f"Churn rate ({period}): {rate:.2f}% ({churned:,.0f} of {total:,.0f})."

    def _calc_nps_score(self, promoters: float, detractors: float, total: float) -> str:
        nps = ((promoters - detractors) / total * 100) if total else 0.0
        sentiment = "excellent" if nps >= 50 else "good" if nps >= 30 else "needs improvement"
        return f"NPS score: {nps:.0f} ({sentiment}) — promoters {promoters:.0f}, detractors {detractors:.0f}."

    def _calc_conversion_rate(self, converted: float, total: float, label: str = "leads") -> str:
        rate = (converted / total * 100) if total else 0.0
        return f"Conversion rate ({label}): {rate:.1f}% ({converted:,.0f} of {total:,.0f})."

    def _calc_utilisation_rate(self, used: float, capacity: float, label: str = "capacity") -> str:
        rate = (used / capacity * 100) if capacity else 0.0
        status = "over capacity" if rate > 100 else "at capacity" if rate >= 90 else "normal"
        return f"{label.title()} utilisation: {rate:.1f}% ({status})."
