"""
Game Adjudicator - Explicit Rules Engine

Following Professor Frenzel's architectural principle:
The game must have an explicit, inspectable ADJUDICATOR / RULES ENGINE.
No LLM or opaque model determines bids, winners, prices, or constraints.
All important rules are traceable to explicit code/configuration.

Maintains separation between:
- FULL WORLD STATE (instructor/system only)
- PLAYER OBSERVATION STATE (only information teams are permitted to see)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import date
import hashlib
import numpy as np
from enum import Enum


def _stable_seed(base_seed: int, salt: str, modifier: int = 0) -> int:
    """Deterministic cross-process seed from hashable inputs."""
    digest = hashlib.sha256(f"{base_seed}:{salt}:{modifier}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


# ── MARKET BASELINES AND ECONOMIC COEFFICIENTS ────────────────────────────
#
# These constants are the game's economic rules. They are declared here, in one
# place, so that a reviewer can read every number that determines an outcome.
# The student game packet imports them too, which guarantees that a model trained
# on the packet's historical data is learning the same process the game runs.

PROPERTY_TYPES: Tuple[str, ...] = ("Industrial", "Office", "Multifamily", "Retail")

# Starting market conditions per property type (round 0 of a Base Case game).
BASE_VACANCY: Dict[str, float] = {
    "Industrial": 0.055,
    "Office": 0.133,
    "Multifamily": 0.036,
    "Retail": 0.065,
}
BASE_CAP_RATE: Dict[str, float] = {
    "Industrial": 0.055,
    "Office": 0.072,
    "Multifamily": 0.052,
    "Retail": 0.065,
}
BASE_RENT_INDEX: Dict[str, float] = {
    "Industrial": 1.49,
    "Office": 2.89,
    "Multifamily": 2944.0,
    "Retail": 3.05,
}

# Starting macro environment.
BASE_POLICY_RATE = 0.053
BASE_UNEMPLOYMENT = 0.039
BASE_EMPLOYMENT_GROWTH = 0.006
BASE_INFLATION = 0.028
BASE_CREDIT_CONDITIONS = 0.5

# NOI growth: a base rate per year, plus a bonus when the market is tight.
NOI_GROWTH_BASE = 0.020
NOI_GROWTH_TIGHT_VACANCY_BONUS = 0.010
TIGHT_VACANCY_THRESHOLD = 0.08
NOI_GROWTH_SIGMA = 0.015
MIN_NOI_GROWTH = -0.10
MAX_NOI_GROWTH = 0.15

# Cap-rate noise and bounds.
CAP_NOISE_SIGMA = 0.0005
MIN_CAP_RATE = 0.03
MAX_CAP_RATE = 0.12

# Scenario deltas (rate environment, employment growth).
SCENARIO_DELTAS: Dict[str, Dict[str, float]] = {
    "Base Case": {"rate_delta": 0.0, "growth_delta": 0.0},
    "Rate Shock": {"rate_delta": 0.02, "growth_delta": -0.01},
    "Growth Rebound": {"rate_delta": -0.005, "growth_delta": 0.015},
}


def realized_year_outcome(
    property_id: str,
    property_type: str,
    noi: float,
    market_vacancy: float,
    market_cap_rate: float,
    seed: int,
    round_number: int,
) -> Dict[str, float]:
    """One simulated year for a single property. Pure and reproducible.

    This is the ONLY place a property's NOI growth, cap rate and value are
    determined. Portfolio revaluation and the round-feedback figures both call
    it, so what a team is told happened is exactly what the engine applied.

    Rules
    -----
    noi_growth   = NOI_GROWTH_BASE (+ tight-vacancy bonus) + seeded noise,
                   clipped to [MIN_NOI_GROWTH, MAX_NOI_GROWTH]
    cap_rate     = market cap rate for the type + seeded noise,
                   clipped to [MIN_CAP_RATE, MAX_CAP_RATE]
    next_noi     = noi * (1 + noi_growth)
    value        = next_noi / cap_rate
    """
    rng = np.random.default_rng(_stable_seed(seed, property_id, round_number))

    base_growth = NOI_GROWTH_BASE + (
        NOI_GROWTH_TIGHT_VACANCY_BONUS if market_vacancy <= TIGHT_VACANCY_THRESHOLD else 0.0
    )
    noi_growth = float(
        np.clip(base_growth + rng.normal(0, NOI_GROWTH_SIGMA), MIN_NOI_GROWTH, MAX_NOI_GROWTH)
    )
    cap_rate = float(
        np.clip(market_cap_rate + rng.normal(0, CAP_NOISE_SIGMA), MIN_CAP_RATE, MAX_CAP_RATE)
    )
    next_noi = noi * (1 + noi_growth)

    return {
        "property_id": property_id,
        "property_type": property_type,
        "noi_growth": noi_growth,
        "cap_rate": cap_rate,
        "next_noi": next_noi,
        "value": next_noi / cap_rate,
        # Occupancy drifts with NOI performance; used for narrative feedback only.
        "occupancy_change": float(
            np.clip(-noi_growth * 0.5 + rng.normal(0, 0.003), -0.05, 0.05)
        ),
    }


class RoundState(Enum):
    """Round state machine."""
    NOT_STARTED = "not_started"
    OPEN = "open"
    LOCKED = "locked"
    RESOLVED = "resolved"


class BidStatus(Enum):
    """Bid validation status."""
    VALID = "valid"
    INSUFFICIENT_EQUITY = "insufficient_equity"
    EXCEEDS_MAX_LTV = "exceeds_max_ltv"
    ROUND_NOT_OPEN = "round_not_open"
    INVALID_BID_AMOUNT = "invalid_bid_amount"
    INVALID_LTV = "invalid_ltv"
    PROPERTY_NOT_AVAILABLE = "property_not_available"


@dataclass
class TeamState:
    """Team's financial state and portfolio."""
    team_id: str
    team_name: str
    cash: float  # in millions
    equity_capital: float  # starting equity, constant
    properties: Dict[str, PropertyHolding] = field(default_factory=dict)
    debt: float = 0.0
    nav: float = 0.0
    cumulative_return: float = 0.0
    # Model predictions (uploaded before game)
    model_predictions: Dict[str, ModelPrediction] = field(default_factory=dict)
    # Human override tracking
    override_history: List[OverrideRecord] = field(default_factory=list)

    # Cumulative cash-flow channels. These make the NAV decomposition exact:
    #     NAV - starting_equity == sum(current_value - purchase_price)
    #                             + cumulative_income
    #                             - cumulative_interest
    # which is what lets the debrief answer "did leverage create or destroy value"
    # with arithmetic instead of opinion.
    cumulative_income: float = 0.0
    cumulative_interest: float = 0.0
    cumulative_purchase_price: float = 0.0


@dataclass
class ModelPrediction:
    """A team's model prediction for a property."""
    property_id: str
    predicted_fair_value: float
    predicted_noi_growth: float
    probability_of_downside: Optional[float]
    max_bid: float
    target_ltv: float
    model_name: str
    confidence: Optional[float] = None
    predicted_exit_cap: Optional[float] = None


@dataclass
class PropertyHolding:
    """A property held by a team."""
    property_id: str
    purchase_price: float
    purchase_round: int
    equity_invested: float
    debt_amount: float
    debt_rate: float
    amortization_years: int
    current_noi: float
    current_value: float
    property_type: str
    submarket: str


@dataclass
class OverrideRecord:
    """Record of human override vs model recommendation."""
    property_id: str
    round_number: int
    model_max_bid: float
    actual_bid: float
    model_target_ltv: float
    actual_ltv: float
    bid_override: float
    ltv_override: float


@dataclass
class Bid:
    """A team's bid for a property."""
    team_id: str
    property_id: str
    bid_price: float
    ltv: float
    round_number: int
    timestamp: str
    confidence: Optional[float] = None


@dataclass
class AuctionResult:
    """Result of a sealed-bid auction for one property."""
    property_id: str
    winning_team_id: Optional[str]
    winning_bid: Optional[float]
    winning_ltv: Optional[float]
    all_bids: List[Bid]
    reserve_price: float
    sold: bool
    reason: str


@dataclass
class MarketState:
    """Market environment for a round."""
    round_number: int
    policy_rate: float
    unemployment: float
    employment_growth: float
    inflation: float
    vacancy: Dict[str, float]  # by property type
    asking_rent_index: Dict[str, float]
    cap_rate: Dict[str, float]
    credit_conditions: float
    seed: int


@dataclass
class PropertyMarket:
    """Property available in a round."""
    property_id: str
    property_name: str
    property_type: str
    submarket: str
    asking_price: float
    current_noi: float
    current_cap: float
    occupancy: float
    building_sf: float
    year_built: int
    max_ltv: float
    debt_rate: float
    amortization_years: int
    reserve_price: float  # hidden from players


@dataclass
class RoundResult:
    """Results after resolving a round."""
    round_number: int
    auction_results: Dict[str, AuctionResult]
    portfolio_updates: Dict[str, TeamState]
    market_state: MarketState
    property_outcomes: Dict[str, PropertyOutcome]


@dataclass
class PropertyOutcome:
    """Outcome for a property after a round."""
    property_id: str
    noi_growth_actual: float
    cap_rate_actual: float
    exit_value: float
    exit_noi: float
    occupancy_change: float


class Adjudicator:
    """
    Explicit rules engine for game adjudication.
    
    All game rules are implemented as inspectable Python functions.
    No opaque models or LLMs determine outcomes.
    """

    def __init__(self, seed: int = 20240331):
        self.seed = seed
        self.rng = np.random.default_rng(seed)

    def validate_bid(
        self,
        bid: Bid,
        team: TeamState,
        property_market: PropertyMarket,
        round_state: RoundState,
    ) -> Tuple[BidStatus, str]:
        """
        Validate a bid against game constraints.
        
        Rules:
        - Round must be OPEN
        - Bid must be > 0
        - LTV must be between 0 and property max LTV
        - Team must have sufficient equity (cash >= bid * (1 - LTV))
        - Property must be available in this round
        """
        if round_state != RoundState.OPEN:
            return BidStatus.ROUND_NOT_OPEN, "Round is not open for submissions"
        
        if bid.bid_price <= 0:
            return BidStatus.INVALID_BID_AMOUNT, "Bid must be greater than 0"
        
        if bid.ltv <= 0 or bid.ltv > property_market.max_ltv:
            return BidStatus.INVALID_LTV, f"LTV must be between 0 and {property_market.max_ltv}"
        
        equity_required = bid.bid_price * (1 - bid.ltv)
        if team.cash < equity_required:
            return BidStatus.INSUFFICIENT_EQUITY, f"Insufficient cash: need ${equity_required:.2f}M, have ${team.cash:.2f}M"
        
        return BidStatus.VALID, "Bid is valid"

    def resolve_auction(
        self,
        property_id: str,
        bids: List[Bid],
        property_market: PropertyMarket,
        teams: Dict[str, TeamState],
        round_number: int = 0,
    ) -> AuctionResult:
        """
        Resolve a sealed-bid auction.
        
        Rules:
        - Highest VALID bid wins
        - Winner pays their submitted price
        - If highest bid < reserve price, property does not sell
        - Tie-breaking: lower LTV (higher equity) wins
        - If still tied, deterministic seeded tie-breaker
        """
        # Filter valid bids
        valid_bids = []
        for bid in bids:
            team = teams[bid.team_id]
            status, reason = self.validate_bid(bid, team, property_market, RoundState.OPEN)
            if status == BidStatus.VALID:
                valid_bids.append(bid)
        
        if not valid_bids:
            return AuctionResult(
                property_id=property_id,
                winning_team_id=None,
                winning_bid=None,
                winning_ltv=None,
                all_bids=bids,
                reserve_price=property_market.reserve_price,
                sold=False,
                reason="No valid bids received",
            )
        
        # Sort by bid price (descending), then by LTV (ascending for tie-break)
        valid_bids.sort(key=lambda b: (-b.bid_price, b.ltv))
        
        winning_bid = valid_bids[0]
        
        # Check reserve price
        if winning_bid.bid_price < property_market.reserve_price:
            return AuctionResult(
                property_id=property_id,
                winning_team_id=None,
                winning_bid=None,
                winning_ltv=None,
                all_bids=bids,
                reserve_price=property_market.reserve_price,
                sold=False,
                reason=f"Highest bid ${winning_bid.bid_price:.2f}M below reserve ${property_market.reserve_price:.2f}M",
            )
        
        # Tie-break, in the documented order:
        #   1. lowest LTV (highest certainty of close)
        #   2. then a seeded deterministic draw
        # `valid_bids` is already sorted by (-bid_price, ltv), so any exact price
        # tie is led by the lowest-LTV bid.
        tied_bids = [b for b in valid_bids if abs(b.bid_price - winning_bid.bid_price) < 0.001]
        if len(tied_bids) > 1:
            lowest_ltv = tied_bids[0].ltv
            certainty_group = [
                b for b in tied_bids if abs(b.ltv - lowest_ltv) < 1e-9
            ]
            if len(certainty_group) > 1:
                # Still tied on price AND leverage: SHA-256-derived seeded draw.
                tie_seed = _stable_seed(self.seed, property_id, round_number)
                tie_rng = np.random.default_rng(tie_seed)
                winning_bid = certainty_group[int(tie_rng.integers(0, len(certainty_group)))]
            else:
                winning_bid = certainty_group[0]
        else:
            winning_bid = tied_bids[0]
        
        return AuctionResult(
            property_id=property_id,
            winning_team_id=winning_bid.team_id,
            winning_bid=winning_bid.bid_price,
            winning_ltv=winning_bid.ltv,
            all_bids=bids,
            reserve_price=property_market.reserve_price,
            sold=True,
            reason=f"Awarded to {winning_bid.team_id}",
        )

    def update_team_portfolio(
        self,
        team: TeamState,
        auction_result: AuctionResult,
        property_market: PropertyMarket,
        round_number: int,
        opening_noi: Optional[float] = None,
    ) -> TeamState:
        """
        Update team's portfolio after auction resolution.
        
        Rules:
        - If won: deduct equity, add debt, add property to portfolio
        - If lost: no change
        - Track human override vs model prediction

        ``opening_noi`` is the property's NOI at the START of the round. It is
        passed explicitly because the market loop has already advanced the
        property's NOI to year-end by the time portfolios are updated; without
        it a newly acquired asset would be revalued twice in its first year.
        """
        if not auction_result.sold or auction_result.winning_team_id != team.team_id:
            return team
        
        # Calculate equity and debt
        equity_invested = auction_result.winning_bid * (1 - auction_result.winning_ltv)
        debt_amount = auction_result.winning_bid * auction_result.winning_ltv
        
        # Update cash
        team.cash -= equity_invested
        team.debt += debt_amount
        team.cumulative_purchase_price += auction_result.winning_bid
        
        # Add property to portfolio
        holding = PropertyHolding(
            property_id=property_market.property_id,
            purchase_price=auction_result.winning_bid,
            purchase_round=round_number,
            equity_invested=equity_invested,
            debt_amount=debt_amount,
            debt_rate=property_market.debt_rate,
            amortization_years=property_market.amortization_years,
            current_noi=(
                opening_noi if opening_noi is not None else property_market.current_noi
            ),
            current_value=property_market.asking_price,
            property_type=property_market.property_type,
            submarket=property_market.submarket,
        )
        team.properties[property_market.property_id] = holding
        
        # Track override if model prediction exists
        if property_market.property_id in team.model_predictions:
            model = team.model_predictions[property_market.property_id]
            override = OverrideRecord(
                property_id=property_market.property_id,
                round_number=round_number,
                model_max_bid=model.max_bid,
                actual_bid=auction_result.winning_bid,
                model_target_ltv=model.target_ltv,
                actual_ltv=auction_result.winning_ltv,
                bid_override=auction_result.winning_bid - model.max_bid,
                ltv_override=auction_result.winning_ltv - model.target_ltv,
            )
            team.override_history.append(override)
        
        return team

    def advance_market(
        self,
        previous_market: Optional[MarketState],
        round_number: int,
        scenario: str,
    ) -> MarketState:
        """
        Advance market state to next round.
        
        Rules:
        - Macro variables evolve based on scenario + seeded noise
        - Property-type specific vacancy, rent, cap rates evolve
        - All randomness is seeded and reproducible
        """
        delta = SCENARIO_DELTAS.get(scenario, SCENARIO_DELTAS["Base Case"])
        
        if previous_market is None:
            # Initialize base market
            policy_rate = BASE_POLICY_RATE
            unemployment = BASE_UNEMPLOYMENT
            employment_growth = BASE_EMPLOYMENT_GROWTH
            inflation = BASE_INFLATION
            credit_conditions = BASE_CREDIT_CONDITIONS
        else:
            # Evolve from previous
            policy_rate = max(0.01, previous_market.policy_rate + delta["rate_delta"] + self.rng.normal(0, 0.002))
            unemployment = max(0.02, min(0.15, previous_market.unemployment + self.rng.normal(0, 0.001)))
            employment_growth = previous_market.employment_growth + delta["growth_delta"] + self.rng.normal(0, 0.002)
            inflation = max(0.01, min(0.10, previous_market.inflation + self.rng.normal(0, 0.001)))
            credit_conditions = max(0.0, min(1.0, previous_market.credit_conditions + self.rng.normal(0, 0.05)))
        
        # Property-type specific market conditions
        vacancy = {}
        cap_rate = {}
        asking_rent_index = {}
        
        for ptype in PROPERTY_TYPES:
            if previous_market is None:
                vacancy[ptype] = BASE_VACANCY[ptype]
                cap_rate[ptype] = BASE_CAP_RATE[ptype]
                asking_rent_index[ptype] = BASE_RENT_INDEX[ptype]
            else:
                # Evolve with scenario influence + noise
                vac_change = -delta["growth_delta"] * 0.5 + self.rng.normal(0, 0.005)
                vacancy[ptype] = max(0.01, min(0.30, previous_market.vacancy[ptype] + vac_change))
                
                cap_change = delta["rate_delta"] * 0.3 + self.rng.normal(0, 0.001)
                cap_rate[ptype] = max(MIN_CAP_RATE, min(MAX_CAP_RATE, previous_market.cap_rate[ptype] + cap_change))
                
                rent_change = delta["growth_delta"] * 0.4 + self.rng.normal(0, 0.02)
                asking_rent_index[ptype] = BASE_RENT_INDEX[ptype] * (1 + rent_change)
        
        return MarketState(
            round_number=round_number,
            policy_rate=round(policy_rate, 6),
            unemployment=round(unemployment, 6),
            employment_growth=round(employment_growth, 6),
            inflation=round(inflation, 6),
            vacancy=vacancy,
            asking_rent_index=asking_rent_index,
            cap_rate=cap_rate,
            credit_conditions=round(credit_conditions, 6),
            seed=self.seed + round_number,
        )

    def update_property_values(
        self,
        team: TeamState,
        market_state: MarketState,
        round_number: int,
    ) -> TeamState:
        """
        Revalue a team's holdings for the round.

        Delegates to :func:`realized_year_outcome`, the same pure function that
        produces the reported round feedback, so a holding's new value and the
        "current realized value" shown to the student are always identical.
        """
        for prop_id, holding in team.properties.items():
            ptype = holding.property_type
            outcome = realized_year_outcome(
                property_id=prop_id,
                property_type=ptype,
                noi=holding.current_noi,
                market_vacancy=market_state.vacancy[ptype],
                market_cap_rate=market_state.cap_rate[ptype],
                seed=self.seed,
                round_number=round_number,
            )
            holding.current_noi = outcome["next_noi"]
            holding.current_value = outcome["value"]

        return team

    def collect_property_income(self, team: TeamState) -> TeamState:
        """Credit a year of net operating income from every holding to cash.

        Rules
        -----
        income       = sum of each holding's current_noi
        team.cash   += income

        Every holding is credited, including one bought this round, so the rule is
        straightforward to state and to audit: *each year, each property you own
        pays its NOI.*

        Why this exists: an acquisition's return is the NOI yield plus any
        appreciation, and the cost of financing is a real drag. Without income the
        only credit was appraisal, so any borrowing at the loan rate destroyed
        value and leverage swamped every other decision in the game. With income
        modelled, a team that wins an asset below fair value earns its yield and
        can carry debt; a team that overpays does not.
        """
        income = sum(holding.current_noi for holding in team.properties.values())
        team.cash += income
        team.cumulative_income += income
        return team

    def accrue_debt_interest(self, team: TeamState) -> TeamState:
        """Charge one year of interest on each holding's outstanding debt.

        Rules
        -----
        interest      = sum over holdings of (debt_amount * debt_rate)
        team.cash    -= interest

        Debt is interest-only; there is no amortization in the MVP.

        Why this exists: NAV is ``cash + property values - debt``, and debt is
        otherwise a static offset, so leverage would be exactly NAV-neutral and
        the question "did borrowing create or destroy value?" would have no
        answer in the data. Charging interest makes the trade-off real and
        explicit: borrowing at the loan rate only adds value when the asset's
        return on purchase price exceeds that rate. A team that pays close to the
        asking price and levers up therefore destroys value, while a team that
        wins near the seller's reserve and levers up creates it.
        """
        interest = sum(
            holding.debt_amount * holding.debt_rate
            for holding in team.properties.values()
        )
        team.cash -= interest
        team.cumulative_interest += interest
        return team

    def calculate_nav(self, team: TeamState) -> float:
        """
        Calculate team's Net Asset Value.
        
        NAV = Cash + Property Values - Debt
        """
        property_values = sum(h.current_value for h in team.properties.values())
        nav = team.cash + property_values - team.debt
        return round(nav, 6)

    def calculate_cumulative_return(self, team: TeamState) -> float:
        """
        Calculate cumulative return on equity.
        
        Return = (NAV - Starting Equity) / Starting Equity
        """
        nav = self.calculate_nav(team)
        if team.equity_capital <= 0:
            return 0.0
        return round((nav - team.equity_capital) / team.equity_capital, 6)

    def resolve_round(
        self,
        round_number: int,
        teams: Dict[str, TeamState],
        properties: Dict[str, PropertyMarket],
        bids: List[Bid],
        previous_market: Optional[MarketState],
        scenario: str,
    ) -> RoundResult:
        """
        Resolve a complete round.

        Process:
        1. Advance market state
        2. Resolve auctions for all properties
        3. Update team portfolios (SKIPPED for practice rounds)
        4. Update property values (SKIPPED for practice rounds)
        5. Calculate NAV and returns
        """
        is_practice = round_number < 0
        # Advance market
        market_state = self.advance_market(previous_market, round_number, scenario)
        
        # Resolve auctions
        auction_results = {}
        property_outcomes = {}
        # NOI at the start of the round, captured before the market advances.
        opening_noi: Dict[str, float] = {}
        
        for prop_id, prop_market in properties.items():
            opening_noi[prop_id] = prop_market.current_noi
            prop_bids = [b for b in bids if b.property_id == prop_id]
            auction_result = self.resolve_auction(prop_id, prop_bids, prop_market, teams)
            
            # Practice rounds don't actually award properties
            # Keep the auction results for UI display but mark as unsold
            if is_practice:
                auction_result = type(auction_result)(
                    property_id=auction_result.property_id,
                    winning_team_id=None,
                    winning_bid=None,
                    winning_ltv=None,
                    all_bids=auction_result.all_bids,
                    reserve_price=auction_result.reserve_price,
                    sold=False,
                    reason="Practice round — no actual transactions",
                )
            
            auction_results[prop_id] = auction_result
            
            # One pure function determines this property's year. It is the same
            # function that revalues any team's holding of this property, so the
            # market's view and the owner's books cannot drift apart.
            ptype = prop_market.property_type
            outcome = realized_year_outcome(
                property_id=prop_id,
                property_type=ptype,
                noi=prop_market.current_noi,
                market_vacancy=market_state.vacancy[ptype],
                market_cap_rate=market_state.cap_rate[ptype],
                seed=self.seed,
                round_number=round_number,
            )
            
            property_outcomes[prop_id] = PropertyOutcome(
                property_id=prop_id,
                noi_growth_actual=round(outcome["noi_growth"], 6),
                cap_rate_actual=round(outcome["cap_rate"], 6),
                exit_value=round(outcome["value"], 6),
                exit_noi=round(outcome["next_noi"], 6),
                occupancy_change=round(outcome["occupancy_change"], 6),
            )
            
            # Advance the market's own NOI for this property into next year.
            if not is_practice:
                prop_market.current_noi = outcome["next_noi"]
        
        # Update team portfolios (skip for practice)
        updated_teams = {}
        for team_id, team in teams.items():
            updated_team = team
            if not is_practice:
                # Calculate total equity needed across all wins for this team
                total_equity_needed = 0.0
                for prop_id, auction_result in auction_results.items():
                    if (auction_result.sold and 
                        auction_result.winning_team_id == team_id and 
                        prop_id in properties):
                        eq = auction_result.winning_bid * (1 - auction_result.winning_ltv)
                        total_equity_needed += eq

                # If team can't afford all wins, mark excess wins as unsold
                if total_equity_needed > team.cash:
                    # Sort wins by bid price descending, unsell the most expensive first
                    wins_to_unsell = []
                    equity_deducted = 0.0
                    for prop_id, auction_result in auction_results.items():
                        if (auction_result.sold and 
                            auction_result.winning_team_id == team_id and 
                            prop_id in properties and
                            auction_result.winning_ltv is not None):
                            eq = auction_result.winning_bid * (1 - auction_result.winning_ltv)
                            if equity_deducted + eq > team.cash:
                                wins_to_unsell.append(prop_id)
                        if prop_id not in wins_to_unsell and auction_result.winning_ltv is not None:
                            equity_deducted += auction_result.winning_bid * (1 - auction_result.winning_ltv)

                    for unsold_prop in wins_to_unsell:
                        auction_results[unsold_prop] = type(auction_results[unsold_prop])(
                            property_id=auction_results[unsold_prop].property_id,
                            winning_team_id=None,
                            winning_bid=None,
                            winning_ltv=None,
                            all_bids=auction_results[unsold_prop].all_bids,
                            reserve_price=auction_results[unsold_prop].reserve_price,
                            sold=False,
                            reason=f"Insufficient cash to complete purchase",
                        )

                for prop_id, auction_result in auction_results.items():
                    if prop_id in properties:
                        updated_team = self.update_team_portfolio(
                            updated_team,
                            auction_result,
                            properties[prop_id],
                            round_number,
                            opening_noi=opening_noi.get(prop_id),
                        )
                # Order matters and is deliberate:
                #   1. collect this year's NOI at the NOI the asset carried
                #   2. then revalue (which advances each holding's NOI to next year)
                #   3. then pay interest on the debt that financed it
                updated_team = self.collect_property_income(updated_team)
                updated_team = self.update_property_values(updated_team, market_state, round_number)
                updated_team = self.accrue_debt_interest(updated_team)
                # Calculate NAV and returns
                updated_team.nav = self.calculate_nav(updated_team)
                updated_team.cumulative_return = self.calculate_cumulative_return(updated_team)
            else:
                # For practice, keep team state unchanged
                updated_team.nav = team.nav
                updated_team.cumulative_return = team.cumulative_return
            updated_teams[team_id] = updated_team
        
        return RoundResult(
            round_number=round_number,
            auction_results=auction_results,
            portfolio_updates=updated_teams,
            market_state=market_state,
            property_outcomes=property_outcomes,
        )

    def get_player_observation(
        self,
        team_id: str,
        full_world_state: RoundResult,
        team_model_predictions: Dict[str, ModelPrediction],
    ) -> Dict:
        """
        Generate player-visible observation state.
        
        This is what a team is allowed to see.
        Full world state (including other teams' bids, reserve prices, etc.)
        remains hidden.
        """
        team_state = full_world_state.portfolio_updates.get(team_id)
        if team_state is None:
            return {}
        
        # Filter auction results to show only what this team needs to know
        visible_auctions = {}
        for prop_id, result in full_world_state.auction_results.items():
            visible_auctions[prop_id] = {
                "property_id": result.property_id,
                "sold": result.sold,
                "winning_team_id": result.winning_team_id if result.winning_team_id == team_id else None,
                "winning_bid": result.winning_bid if result.winning_team_id == team_id else None,
                "your_bid": next((b.bid_price for b in result.all_bids if b.team_id == team_id), None),
                "reason": result.reason if not result.sold else None,
            }
        
        # Property outcomes (only for properties this team owns or bid on)
        visible_outcomes = {}
        for prop_id, outcome in full_world_state.property_outcomes.items():
            if prop_id in team_state.properties or any(
                b.property_id == prop_id for b in full_world_state.auction_results[prop_id].all_bids if b.team_id == team_id
            ):
                visible_outcomes[prop_id] = outcome
        
        # Market state (fully visible to all)
        market_obs = {
            "policy_rate": full_world_state.market_state.policy_rate,
            "unemployment": full_world_state.market_state.unemployment,
            "employment_growth": full_world_state.market_state.employment_growth,
            "inflation": full_world_state.market_state.inflation,
            "vacancy": full_world_state.market_state.vacancy,
            "cap_rate": full_world_state.market_state.cap_rate,
            "credit_conditions": full_world_state.market_state.credit_conditions,
        }
        
        return {
            "team_id": team_id,
            "cash": team_state.cash,
            "nav": team_state.nav,
            "cumulative_return": team_state.cumulative_return,
            "properties": {pid: {
                "property_id": h.property_id,
                "purchase_price": h.purchase_price,
                "current_value": h.current_value,
                "current_noi": h.current_noi,
                "property_type": h.property_type,
                "submarket": h.submarket,
            } for pid, h in team_state.properties.items()},
            "model_predictions": team_model_predictions,
            "auction_results": visible_auctions,
            "property_outcomes": visible_outcomes,
            "market_state": market_obs,
            "override_history": team_state.override_history,
        }
