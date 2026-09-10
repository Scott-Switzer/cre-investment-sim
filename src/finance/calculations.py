"""
CRE financial calculations.

All amounts are in $ millions unless otherwise noted.
Rates/returns are decimal fractions (e.g. 0.06 for 6%).
"""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass
class UnderwritingResult:
    purchase_price: float
    bid: float
    equity_required: float
    loan_amount: float
    ltv: float
    annual_debt_service: float
    dscr: float
    debt_yield: float
    current_noi: float
    noi_growth_forecast: float
    predicted_noi: float
    exit_cap_forecast: float
    predicted_value: float
    predicted_equity_value: float
    predicted_cash_flow: float
    predicted_levered_return: float


def loan_amount(purchase_price: float, ltv: float) -> float:
    """Loan amount = price * LTV."""
    return round(purchase_price * ltv, 6)


def equity_required(purchase_price: float, ltv: float) -> float:
    """Equity = price - loan."""
    return round(purchase_price - loan_amount(purchase_price, ltv), 6)


def mortgage_payment_annual(principal: float, annual_rate: float, amortization_years: int) -> float:
    """
    Annual debt service for a fully amortizing fixed-rate loan.
    principal in $ millions, rate decimal, years int.
    Returns $MM per year.
    For a zero-rate loan the annual payment is principal / amortization_years.
    """
    if principal <= 0:
        return 0.0
    if annual_rate <= 0:
        # zero-interest amortizing loan: principal / term
        if amortization_years <= 0:
            return principal
        return round(principal / amortization_years, 6)
    r = annual_rate / 12.0
    n = amortization_years * 12
    p = principal * 1_000_000.0
    pm = p * r * math.pow(1 + r, n) / (math.pow(1 + r, n) - 1)
    return round(pm * 12 / 1_000_000.0, 6)


def annual_debt_service(principal: float, annual_rate: float, amortization_years: int = 25) -> float:
    return mortgage_payment_annual(principal, annual_rate, amortization_years)


def ltv(loan_amount: float, purchase_price: float) -> float:
    if purchase_price <= 0:
        return 0.0
    return round(loan_amount / purchase_price, 6)


def debt_yield(noi: float, loan_amount: float) -> float:
    if loan_amount <= 0:
        return float("inf")
    return round(noi / loan_amount, 6)


def dscr(noi: float, debt_service: float) -> float:
    if debt_service <= 0:
        return float("inf")
    return round(noi / debt_service, 6)


def property_value_from_noi(noi: float, cap_rate: float) -> float:
    if cap_rate <= 0:
        raise ValueError("cap_rate must be > 0")
    return round(noi / cap_rate, 6)


def cap_rate(noi: float, value: float) -> float:
    if value <= 0:
        raise ValueError("value must be > 0")
    return round(noi / value, 6)


def cash_flow_after_debt_service(noi: float, debt_service: float) -> float:
    return round(noi - debt_service, 6)


def levered_equity_return(
    predicted_value: float,
    predicted_cash_flow: float,
    equity_invested: float,
    debt_amount: float,
) -> float:
    """
    One-period levered equity return.
    r = (equity_value_at_exit + cash_flow - equity_invested) / equity_invested
    """
    if equity_invested <= 0:
        return float("nan")
    equity_value = predicted_value - debt_amount
    return round((equity_value + predicted_cash_flow - equity_invested) / equity_invested, 6)


def unlevered_property_return(
    predicted_value: float,
    predicted_cash_flow: float,
    purchase_price: float,
) -> float:
    """
    One-period unlevered property return.
    r = (value_at_exit + cash_flow - purchase_price) / purchase_price
    """
    if purchase_price <= 0:
        return float("nan")
    return round((predicted_value + predicted_cash_flow - purchase_price) / purchase_price, 6)


def round_return(
    purchase_price: float,
    debt_amount: float,
    equity_invested: float,
    exit_value: float,
    cash_flow: float,
) -> float:
    if equity_invested <= 0:
        return float("nan")
    equity_exit = exit_value - debt_amount
    return round((equity_exit + cash_flow - equity_invested) / equity_invested, 6)


def underwrite(
    asking_price: float,
    current_noi: float,
    debt_rate: float,
    amortization_years: int,
    max_ltv: float,
    bid: float,
    ltv_choice: float,
    noi_growth_forecast: float,
    exit_cap_forecast: float,
) -> UnderwritingResult:
    """Build a full underwriting result from a student's choices."""
    effective_ltv = min(max_ltv, max(0.0, ltv_choice))
    price = bid if bid > 0 else asking_price
    loan = loan_amount(price, effective_ltv)
    equity = equity_required(price, effective_ltv)
    ds = annual_debt_service(loan, debt_rate, amortization_years)
    noi = current_noi
    dscr_val = dscr(noi, ds) if ds > 0 else float("inf")
    dy = debt_yield(noi, loan) if loan > 0 else float("inf")
    predicted_noi = noi * (1.0 + noi_growth_forecast)
    predicted_value = property_value_from_noi(predicted_noi, exit_cap_forecast)
    predicted_cash_flow = cash_flow_after_debt_service(predicted_noi, ds)
    predicted_equity_value = predicted_value - loan
    predicted_return = levered_equity_return(
        predicted_value, predicted_cash_flow, equity, loan
    )
    return UnderwritingResult(
        purchase_price=price,
        bid=bid,
        equity_required=equity,
        loan_amount=loan,
        ltv=effective_ltv,
        annual_debt_service=ds,
        dscr=dscr_val,
        debt_yield=dy,
        current_noi=noi,
        noi_growth_forecast=noi_growth_forecast,
        predicted_noi=predicted_noi,
        exit_cap_forecast=exit_cap_forecast,
        predicted_value=predicted_value,
        predicted_equity_value=predicted_equity_value,
        predicted_cash_flow=predicted_cash_flow,
        predicted_levered_return=predicted_return,
    )
