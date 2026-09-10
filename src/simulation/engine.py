"""
Game engine.

A game contains at least 3 rounds. The engine holds the hidden world state
and resolves outcomes only after the instructor advances the round.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional
import uuid

from src.simulation.world import WorldState, RoundResolution, build_world_state, resolve_property_round, SCENARIOS
import uuid


def create_game(seed: int = 20240331, count: int = 30) -> Game:
    '''Create a game preloaded with a deterministic property set.'''
    from src.data.properties import generate_properties
    props = generate_properties(seed=seed, count=count)
    game = Game(game_id=str(uuid.uuid4()), name='Demo Game', base_seed=seed)
    for _, r in props.iterrows():
        game.add_property(PropertyCase(
            property_id=r['property_id'],
            property_name=r['property_name'],
            property_type=r['type'],
            submarket=r['submarket'],
            asking_price=r['asking_price'],
            current_noi=r['current_noi'],
            current_cap=r['going_in_cap'],
            occupancy=r['occupancy'],
            walt=r['walt'],
            in_place_rent=r['in_place_rent'],
            rent_units=r['lease_expiry_profile'],
            debt_rate=r['debt_rate'],
            amortization_years=r['amortization_years'],
            max_ltv=r['max_ltv'],
            property_quality=r['property_quality'],
            tenant_concentration=r['tenant_concentration'],
            primary_risk=f"{r['type']} submarket {r['submarket']} risk profile",
        ))
    return game


@dataclass
class PropertyCase:
    """A property available for investment in the game."""
    property_id: str
    property_name: str
    property_type: str
    submarket: str
    asking_price: float
    current_noi: float
    current_cap: float
    occupancy: float
    walt: float
    in_place_rent: str
    rent_units: str
    debt_rate: float
    amortization_years: int
    max_ltv: float
    property_quality: float
    tenant_concentration: float
    primary_risk: str
    # internal
    loan_amount: float = 0.0
    equity_invested: float = 0.0
    current_debt_service: float = 0.0
    # resolved later
    resolutions: List[RoundResolution] = field(default_factory=list)


@dataclass
class StudentDecision:
    decision_id: str
    round_index: int
    timestamp: datetime
    property_id: str
    decision: str  # BUY / PASS
    bid: float
    ltv: float
    noi_growth_forecast: float
    exit_cap_forecast: float
    confidence: float
    probability_of_loss: Optional[float]
    investment_thesis: str
    key_assumption: str
    falsification_test: str
    locked: bool = False
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    predicted_value: Optional[float] = None
    predicted_noi: Optional[float] = None


@dataclass
class GameRound:
    round_index: int
    decision_date: date
    scenario: str
    world: WorldState
    decisions: List[StudentDecision] = field(default_factory=list)
    resolutions: Dict[str, RoundResolution] = field(default_factory=dict)
    locked: bool = False
    revealed: bool = False


@dataclass
class Game:
    game_id: str
    name: str
    base_seed: int
    rounds: List[GameRound] = field(default_factory=list)
    start_cash: float = 150.0
    round_index: int = 0
    started: bool = False
    current_scenario: Optional[str] = None
    property_cases: List[PropertyCase] = field(default_factory=list)

    def add_property(self, prop: PropertyCase) -> None:
        self.property_cases.append(prop)

    def start_game(self, scenario: str, decision_date: date) -> None:
        if self.started:
            raise RuntimeError("game already started")
        self.started = True
        self.current_scenario = scenario
        self.rounds = []
        seed = self.base_seed
        for r in range(3):
            ws = build_world_state(r, scenario, previous_state=None if r == 0 else self.rounds[r-1].world, seed=seed + r)
            self.rounds.append(GameRound(round_index=r, decision_date=decision_date, scenario=scenario, world=ws))
        self.round_index = 0

    def current_round(self) -> Optional[GameRound]:
        if not self.rounds:
            return None
        idx = min(self.round_index, len(self.rounds) - 1)
        return self.rounds[idx]

    def add_decision(self, decision: StudentDecision) -> None:
        cr = self.current_round()
        if cr is None:
            raise RuntimeError("no active round")
        cr.decisions.append(decision)

    def lock_round(self) -> None:
        cr = self.current_round()
        if cr is None:
            raise RuntimeError("no active round")
        cr.locked = True

    def reveal_round(self) -> None:
        cr = self.current_round()
        if cr is None or not cr.locked:
            raise RuntimeError("round must be locked before reveal")
        cr.revealed = True
        for d in cr.decisions:
            prop = next((p for p in self.property_cases if p.property_id == d.property_id), None)
            if prop is None:
                continue
            prop.loan_amount = d.bid * d.ltv
            prop.equity_invested = d.bid - prop.loan_amount
            prop.current_debt_service = round(prop.loan_amount * d.debt_rate / 12 * 12 if False else 0, 6)
            # compute debt service properly
            from src.finance.calculations import annual_debt_service as ads
            prop.current_debt_service = ads(prop.loan_amount, d.debt_rate, 25 if prop.property_type == "Multifamily" else 25)
            res = resolve_property_round(
                prop,
                cr.world,
                d.noi_growth_forecast,
                d.exit_cap_forecast,
            )
            cr.resolutions[d.property_id] = res
            prop.resolutions.append(res)

    def advance_round(self) -> None:
        if self.round_index + 1 >= len(self.rounds):
            raise RuntimeError("no more rounds")
        self.round_index += 1

    def portfolio(self) -> Dict:
        """Compute portfolio-level rollup across revealed rounds for the determined property cases."""
        cr = self.current_round()
        if cr is None:
            return {}
        # Aggregate only BUY decisions in the current round
        buys: List[PropertyCase] = []
        for d in cr.decisions:
            if d.decision != "BUY":
                continue
            prop = next((p for p in self.property_cases if p.property_id == d.property_id), None)
            if prop is None:
                continue
            # apply the round resolution to the property for rollup
            res = cr.resolutions.get(d.property_id)
            buys.append(prop)
        return {
            "round_index": cr.round_index,
            "scenario": cr.scenario,
            "cash": self.start_cash,
            "decisions": cr.decisions,
            "resolutions": cr.resolutions,
        }
