import math
import pytest

from src.finance.calculations import (
    loan_amount,
    equity_required,
    annual_debt_service,
    ltv,
    debt_yield,
    dscr,
    property_value_from_noi,
    cap_rate,
    cash_flow_after_debt_service,
    levered_equity_return,
    unlevered_property_return,
    round_return,
    underwrite,
)
from src.finance.portfolio import Position, build_portfolio_result


@pytest.fixture
def loan():
    return 36.4  # MM


@pytest.fixture
def price():
    return 52.0  # MM


@pytest.fixture
def noi():
    return 3.016  # MM


class TestLoanAndEquity:
    def test_loan_amount(self, price):
        assert loan_amount(price, 0.70) == pytest.approx(36.4, abs=1e-6)
        assert loan_amount(price, 0.0) == 0.0

    def test_equity_required(self, price):
        assert equity_required(price, 0.70) == pytest.approx(15.6, abs=1e-6)
        assert equity_required(price, 0.0) == price

    def test_ltv(self, loan, price):
        assert ltv(loan, price) == pytest.approx(0.70, abs=1e-6)
        assert ltv(0.0, price) == 0.0


class TestMortgageMath:
    def test_annual_debt_service_known(self, loan):
        # 6.35% on 36.4MM, 25yr -> approximate
        ds = annual_debt_service(loan, 0.0635, 25)
        assert ds > 0
        # sanity: monthly payment * 12 must exceed interest-only (loan*rate)
        assert ds > loan * 0.0635

    def test_debt_service_zero_rate_returns_principal_over_term(self):
        # A 0% amortizing loan pays principal only, spread over the amortization term.
        ds = annual_debt_service(10.0, 0.0, 25)
        assert ds == pytest.approx(10.0 / 25, abs=1e-6)

    def test_debt_service_zero_principal(self):
        assert annual_debt_service(0.0, 0.06, 25) == 0.0


class TestCoverageAndYield:
    def test_dscr(self, noi):
        ds = annual_debt_service(36.4, 0.0635, 25)
        assert dscr(noi, ds) > 1.0
        assert dscr(noi, 0) == float("inf")

    def test_debt_yield(self, noi, loan):
        assert debt_yield(noi, loan) > 0
        assert debt_yield(noi, 0) == float("inf")


class TestCapRateAndValuation:
    def test_property_value_from_noi(self):
        assert property_value_from_noi(3.016, 0.058) == pytest.approx(52.0, abs=1e-3)

    def test_cap_rate(self):
        assert cap_rate(3.016, 52.0) == pytest.approx(0.058, abs=1e-4)

    def test_value_zero_cap_raises(self):
        with pytest.raises(ValueError):
            property_value_from_noi(1.0, 0.0)

    def test_cap_zero_value_raises(self):
        with pytest.raises(ValueError):
            cap_rate(1.0, 0.0)


class TestReturns:
    def test_levered_equity_return(self):
        # buy 52.0, 0.70 LTV => 36.4 loan, 15.6 equity
        # exit value 55, cash flow 2.5
        ret = levered_equity_return(55.0, 2.5, 15.6, 36.4)
        assert ret > 0

    def test_levered_equity_return_zero_equity(self):
        assert math.isnan(levered_equity_return(55.0, 2.5, 0.0, 36.4))

    def test_unlevered_return(self):
        ret = unlevered_property_return(55.0, 2.5, 52.0)
        assert ret > 0

    def test_round_return(self):
        ret = round_return(52.0, 36.4, 15.6, 55.0, 2.5)
        assert ret > 0


class TestFullUnderwriting:
    def test_underwrite_mirrors_prototype(self):
        u = underwrite(
            asking_price=52.0,
            current_noi=3.016,
            debt_rate=0.0635,
            amortization_years=25,
            max_ltv=0.70,
            bid=52.0,
            ltv_choice=0.60,
            noi_growth_forecast=0.02,
            exit_cap_forecast=0.058,
        )
        assert u.bid == 52.0
        assert u.loan_amount == pytest.approx(31.2, abs=1e-3)
        assert u.equity_required == pytest.approx(20.8, abs=1e-3)
        assert u.ltv == pytest.approx(0.60, abs=1e-4)
        assert u.dscr > 1.0
        assert u.predicted_noi == pytest.approx(3.016 * 1.02, abs=1e-5)
        assert u.predicted_value == pytest.approx(3.016 * 1.02 / 0.058, abs=1e-3)
        assert u.predicted_levered_return > 0

    def test_underwrite_pass_with_zero_bid_sets_price_to_asking(self):
        # When bid is 0, underwrite() falls back to asking_price.
        u = underwrite(
            asking_price=52.0,
            current_noi=3.016,
            debt_rate=0.0635,
            amortization_years=25,
            max_ltv=0.70,
            bid=0,
            ltv_choice=0.0,
            noi_growth_forecast=0.02,
            exit_cap_forecast=0.058,
        )
        assert u.loan_amount == 0.0
        assert u.purchase_price == 52.0
        assert u.equity_required == 52.0

    def test_underwrite_explicit_zero_price_and_ltv(self):
        u = underwrite(
            asking_price=52.0,
            current_noi=3.016,
            debt_rate=0.0635,
            amortization_years=25,
            max_ltv=0.70,
            bid=0,
            ltv_choice=0.0,
            noi_growth_forecast=0.02,
            exit_cap_forecast=0.058,
        )
        # A true PASS with zero price and zero LTV should produce zero equity.
        u2 = underwrite(
            asking_price=0,
            current_noi=3.016,
            debt_rate=0.0635,
            amortization_years=25,
            max_ltv=0.70,
            bid=0,
            ltv_choice=0.0,
            noi_growth_forecast=0.02,
            exit_cap_forecast=0.058,
        )
        assert u2.purchase_price == 0.0
        assert u2.equity_required == 0.0


class TestPortfolio:
    def test_portfolio_aggregation(self):
        positions = [
            Position(
                property_id="OC-IND-01",
                property_name="Anaheim Commerce Center",
                property_type="Industrial",
                submarket="Anaheim",
                purchase_price=52.0,
                equity_invested=20.8,
                debt_amount=31.2,
                debt_rate=0.0635,
                amortization_years=25,
                exit_value=55.0,
                current_noi=3.016,
                predicted_noi=3.07632,
                cash_flow=2.5,
                decision="BUY",
                bid=52.0,
            ),
            Position(
                property_id="OC-OFF-01",
                property_name="Jamboree Office Plaza",
                property_type="Office",
                submarket="Irvine",
                purchase_price=49.0,
                equity_invested=19.6,
                debt_amount=29.4,
                debt_rate=0.0675,
                amortization_years=25,
                exit_value=50.0,
                current_noi=3.43,
                predicted_noi=3.4643,
                cash_flow=2.0,
                decision="BUY",
                bid=49.0,
            ),
        ]
        res = build_portfolio_result(150.0 - 40.4, positions)
        assert res.total_asset_value == pytest.approx(105.0, abs=1e-3)
        assert res.total_debt == pytest.approx(60.6, abs=1e-3)
        assert res.equity_nav == pytest.approx(res.cash + res.total_asset_value - res.total_debt, abs=1e-3)
        assert res.portfolio_ltv == pytest.approx(res.total_debt / res.total_asset_value, abs=1e-4)
        assert "Industrial" in res.type_concentration
        assert "Office" in res.type_concentration
        assert "Anaheim" in res.submarket_concentration
        assert "Irvine" in res.submarket_concentration
        assert len(res.round_returns) == 2
