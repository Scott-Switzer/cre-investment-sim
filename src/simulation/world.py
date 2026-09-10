"""
Simulation world state.

The simulator does NOT claim to be an econometric forecasting model.
It is a pedagogical simulator calibrated to plausible relationships and
public market anchors. All random outcomes are reproducible from a seed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import numpy as np


# Scenario deltas: per property type (noi_growth, cap_rate_delta)
SCENARIO_DELTAS: Dict[str, Dict[str, List[float]]] = {
    "Base Case": {
        "Industrial": [-0.010, 0.001],
        "Office": [0.010, 0.000],
        "Multifamily": [0.025, 0.0005],
        "Retail": [0.015, 0.001],
    },
    "Rate Shock": {
        "Industrial": [-0.025, 0.0065],
        "Office": [-0.040, 0.008],
        "Multifamily": [0.005, 0.005],
        "Retail": [-0.020, 0.007],
    },
    "Growth Rebound": {
        "Industrial": [0.040, -0.002],
        "Office": [0.030, -0.0015],
        "Multifamily": [0.040, -0.001],
        "Retail": [0.030, -0.0015],
    },
}


SCENARIOS: List[str] = list(SCENARIO_DELTAS.keys())


@dataclass
class WorldState:
    """Hidden simulation state for one round."""
    round_index: int
    scenario: str
    # macro
    policy_rate: float
    unemployment: float
    employment_growth: float
    inflation: float
    # market-level by property type
    vacancy: Dict[str, float]
    asking_rent_index: Dict[str, float]
    cap_rate: Dict[str, float]
    new_supply_pressure: Dict[str, float]
    credit_conditions: float
    # seed for idempotency
    seed: int
    _rng: np.random.Generator = field(default=None, repr=False, init=False)

    def __post_init__(self):
        self._rng = np.random.default_rng(self.seed)

    def next_seed(self) -> int:
        self.seed += 1
        return self.seed


@dataclass
class RoundResolution:
    """Outcome for a single property in a single round."""
    property_id: str
    property_type: str
    noi_growth_actual: float
    cap_delta_actual: float
    exit_noi: float
    exit_cap: float
    exit_value: float
    exit_cash_flow: float
    exit_equity_value: float
    levered_return: float
    unlevered_return: float
    occupancy_change: float
    market_comment: str


def build_world_state(
    round_index: int,
    scenario: str,
    previous_state: Optional[WorldState] = None,
    seed: int = 20240331,
) -> WorldState:
    """Build the hidden state for a round given a scenario."""
    deltas = SCENARIO_DELTAS[scenario]
    # start from a plausible base macro environment
    base_policy_rate = 0.053
    # scenario influences policy rate
    if scenario == "Rate Shock":
        policy_rate = round(base_policy_rate + 0.02, 6)
    elif scenario == "Growth Rebound":
        policy_rate = round(base_policy_rate - 0.005, 6)
    else:
        policy_rate = round(base_policy_rate, 6)

    rng = np.random.default_rng(seed + round_index)
    employment_growth = round(0.006 + (0.0 if scenario == "Base Case" else (0.01 if scenario == "Growth Rebound" else -0.003)), 6)
    unemployment = round(0.039 + (-0.002 if scenario == "Growth Rebound" else (0.004 if scenario == "Rate Shock" else 0.0)), 6)
    inflation = round(0.028 + (0.002 if scenario == "Rate Shock" else -0.001), 6)
    credit_conditions = round(0.5 + (0.2 if scenario == "Rate Shock" else (-0.1 if scenario == "Growth Rebound" else 0.0)), 6)

    # vacancy / rent index base values (roughly anchored to OC Q2 2026)
    base_vacancy = {
        "Industrial": 0.055,
        "Office": 0.133,
        "Multifamily": 0.036,
        "Retail": 0.065,
    }
    base_rent_index = {
        "Industrial": 1.49,
        "Office": 2.89,
        "Multifamily": 2944.0,
        "Retail": 3.05,
    }

    vacancy: Dict[str, float] = {}
    asking_rent_index: Dict[str, float] = {}
    cap_rate: Dict[str, float] = {}
    new_supply_pressure: Dict[str, float] = {}

    for ptype in ["Industrial", "Office", "Multifamily", "Retail"]:
        ng, capd = deltas[ptype]
        prev_vac = base_vacancy[ptype]
        # vacancy moves opposite to NOI growth direction, plus noise
        vac_shift = -ng * 1.2 + rng.normal(0, 0.002)
        new_vac = round(max(0.005, min(0.35, prev_vac + vac_shift)), 6)
        vacancy[ptype] = new_vac
        # rent index moves with NOI growth plus noise
        rent_shift = ng * 0.6 + rng.normal(0, 0.03 if ptype == "Multifamily" else 0.02)
        asking_rent_index[ptype] = round(base_rent_index[ptype] * (1 + rent_shift), 4)
        # cap rate starts from plausible OC base and shifts by scenario
        cap_base = {
            "Industrial": 0.055,
            "Office": 0.072,
            "Multifamily": 0.052,
            "Retail": 0.065,
        }[ptype]
        cap_shift = capd + (0.002 if scenario == "Rate Shock" else (-0.001 if scenario == "Growth Rebound" else 0.0))
        cap_rate[ptype] = round(max(0.03, cap_base + cap_shift + rng.normal(0, 0.0008)), 6)
        # new supply pressure: higher vacancy or weaker demand => more pressure
        new_supply_pressure[ptype] = round(max(0.0, min(1.0, new_vac * 3 + 0.2)), 6)

    return WorldState(
        round_index=round_index,
        scenario=scenario,
        policy_rate=policy_rate,
        unemployment=unemployment,
        employment_growth=employment_growth,
        inflation=inflation,
        vacancy=vacancy,
        asking_rent_index=asking_rent_index,
        cap_rate=cap_rate,
        new_supply_pressure=new_supply_pressure,
        credit_conditions=credit_conditions,
        seed=seed,
    )


def resolve_property_round(
    prop: "PropertyCase",
    world: WorldState,
    noi_growth_forecast: float,
    exit_cap_forecast: float,
) -> RoundResolution:
    """
    Resolve one property for one round given the hidden world state and the
    student's forecasts (used for scoring later, not for outcome generation).
    Outcome depends on world state + idiosyncratic noise, NOT on student forecasts.
    """
    deltas = SCENARIO_DELTAS[world.scenario][prop.property_type]
    rng = world._rng
    # idiosyncratic NOI growth noise
    idio = rng.normal(0, 0.012)
    noi_growth = round(deltas[0] + idio, 6)
    # cap rate delta: scenario delta + noise + small property quality effect
    cap_shift = round(deltas[1] + rng.normal(0, 0.0008) + (0.0005 if prop.property_quality < 0.5 else -0.0003), 6)
    exit_noi = round(prop.current_noi * (1 + noi_growth), 6)
    exit_cap = round(max(0.03, prop.current_cap + cap_shift), 6)
    exit_value = round(exit_noi / exit_cap, 6)
    exit_cash_flow = round(exit_noi - (prop.current_debt_service if prop.current_debt_service else 0), 6)
    exit_equity_value = round(exit_value - prop.loan_amount, 6)
    if prop.equity_invested > 0:
        levered_return = round((exit_equity_value + exit_cash_flow - prop.equity_invested) / prop.equity_invested, 6)
    else:
        levered_return = float("nan")
    if prop.asking_price > 0:
        unlevered_return = round((exit_value + exit_cash_flow - prop.asking_price) / prop.asking_price, 6)
    else:
        unlevered_return = float("nan")
    occ_change = round(-noi_growth * 0.5 + rng.normal(0, 0.003), 6)
    occupancy_change = max(-0.2, min(0.1, occ_change))
    # market comment
    remarks: List[str] = []
    if world.vacancy[prop.property_type] > 0.10:
        remarks.append(f"{prop.property_type} vacancy rose to {world.vacancy[prop.property_type]*100:.1f}%")
    elif world.vacancy[prop.property_type] < 0.05:
        remarks.append(f"{prop.property_type} vacancy stayed tight at {world.vacancy[prop.property_type]*100:.1f}%")
    if world.policy_rate > 0.06:
        remarks.append("higher policy rates pressured cap rates")
    if world.employment_growth > 0.008:
        remarks.append("employment growth supported demand")
    market_comment = "; ".join(remarks) if remarks else "market broadly stable"
    return RoundResolution(
        property_id=prop.property_id,
        property_type=prop.property_type,
        noi_growth_actual=noi_growth,
        cap_delta_actual=cap_shift,
        exit_noi=exit_noi,
        exit_cap=exit_cap,
        exit_value=exit_value,
        exit_cash_flow=exit_cash_flow,
        exit_equity_value=exit_equity_value,
        levered_return=levered_return,
        unlevered_return=unlevered_return,
        occupancy_change=occupancy_change,
        market_comment=market_comment,
    )
