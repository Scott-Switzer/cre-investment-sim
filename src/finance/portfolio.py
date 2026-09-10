"""
Portfolio aggregation calculations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from src.finance.calculations import round_return


@dataclass
class Position:
    property_id: str
    property_name: str
    property_type: str
    submarket: str
    purchase_price: float
    equity_invested: float
    debt_amount: float
    debt_rate: float
    amortization_years: int
    exit_value: float
    current_noi: float
    predicted_noi: float
    cash_flow: float
    decision: str  # BUY or PASS
    bid: float


@dataclass
class PortfolioResult:
    cash: float
    total_asset_value: float
    total_debt: float
    equity_nav: float
    portfolio_ltv: float
    portfolio_dscr: float
    type_concentration: dict
    submarket_concentration: dict
    total_equity_deployed: float
    positions: list[Position] = field(default_factory=list)
    round_returns: list[float] = field(default_factory=list)
    cumulative_return: float = 0.0


def portfolio_ltv(total_debt: float, total_asset_value: float) -> float:
    if total_asset_value <= 0:
        return 0.0
    return round(total_debt / total_asset_value, 6)


def portfolio_dscr(total_noi: float, total_debt_service: float) -> float:
    if total_debt_service <= 0:
        return float("inf")
    return round(total_noi / total_debt_service, 6)


def type_concentration(positions: Sequence[Position]) -> dict:
    total = sum(p.exit_value for p in positions if p.decision == "BUY")
    out: dict[str, float] = {}
    for p in positions:
        if p.decision != "BUY":
            continue
        out[p.property_type] = out.get(p.property_type, 0.0) + p.exit_value
    return {k: round(v / total, 6) if total > 0 else 0.0 for k, v in out.items()}


def submarket_concentration(positions: Sequence[Position]) -> dict:
    total = sum(p.exit_value for p in positions if p.decision == "BUY")
    out: dict[str, float] = {}
    for p in positions:
        if p.decision != "BUY":
            continue
        out[p.submarket] = out.get(p.submarket, 0.0) + p.exit_value
    return {k: round(v / total, 6) if total > 0 else 0.0 for k, v in out.items()}


def portfolio_nav(cash: float, total_asset_value: float, total_debt: float) -> float:
    return round(cash + total_asset_value - total_debt, 6)


def build_portfolio_result(
    cash: float,
    positions: Sequence[Position],
) -> PortfolioResult:
    buys = [p for p in positions if p.decision == "BUY"]
    total_asset_value = sum(p.exit_value for p in buys)
    total_debt = sum(p.debt_amount for p in buys)
    total_noi = sum(p.predicted_noi for p in buys)
    total_debt_service = sum(
        p.debt_amount * 0
        for p in buys
    )  # placeholder; compute debt service outside
    # Debt service computed explicitly below from each position
    from src.finance.calculations import annual_debt_service as ads
    total_debt_service = sum(ads(p.debt_amount, p.debt_rate, p.amortization_years) for p in buys)
    equity_deployed = sum(p.equity_invested for p in buys)
    equity_nav = portfolio_nav(cash, total_asset_value, total_debt)
    returns = []
    for p in buys:
        r = round_return(p.purchase_price, p.debt_amount, p.equity_invested, p.exit_value, p.cash_flow)
        returns.append(r)
    cumulative_return = sum(returns) / max(1, len(returns)) if returns else 0.0
    return PortfolioResult(
        cash=cash,
        total_asset_value=round(total_asset_value, 6),
        total_debt=round(total_debt, 6),
        equity_nav=round(equity_nav, 6),
        portfolio_ltv=portfolio_ltv(total_debt, total_asset_value),
        portfolio_dscr=portfolio_dscr(total_noi, total_debt_service),
        type_concentration=type_concentration(positions),
        submarket_concentration=submarket_concentration(positions),
        total_equity_deployed=round(equity_deployed, 6),
        positions=list(positions),
        round_returns=returns,
        cumulative_return=round(cumulative_return, 6),
    )
