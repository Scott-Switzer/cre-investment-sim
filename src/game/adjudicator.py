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

# ── transaction economics ─────────────────────────────────────────────────
#
# Two real costs of owning commercial property that the engine used to ignore.
# Both are standard, inspectable rules rather than penalties:
#
# ACQUISITION_COST_RATE -- legal, diligence, title and financing fees paid on
#   every purchase. Lenders do not finance closing costs, so this comes out of
#   the buyer's cash on day one and reduces NAV immediately. It is what makes
#   "buy at any price" cost something: every acquisition starts behind.
#
# CAPITAL_RESERVE_RATE -- the recurring capital a building consumes for tenant
#   improvements, leasing commissions, and replacement reserves. It scales with
#   the asset, not with the loan, so leverage multiplies it. Office and retail
#   roll more space and consume more capital than NNN industrial.
#
# Together these are the reason a fairly-priced, fully-levered asset earns
# roughly its cost of debt instead of a free lunch -- which is what makes the
# PRICE paid, and therefore the quality of the analysis, decide the outcome.
ACQUISITION_COST_RATE = 0.020
CAPITAL_RESERVE_RATE: Dict[str, float] = {
    "Industrial": 0.006,
    "Office": 0.018,
    "Multifamily": 0.010,
    "Retail": 0.015,
}

# ── asset management (V2, September 18 direction) ────────────────────────
#
# A fund sets one MANAGEMENT STANCE per owned building each round, in the same
# decision window as its bids. The stance is a real operating posture, not a
# bonus:
#
#   RUN LEAN             defer maintenance and hold costs down. Cheaper in a
#                        calm year; a vacancy shock hits harder when it comes.
#   STANDARD             the neutral posture. Identical to the pre-V2
#                        economics, so existing sessions, packets and balance
#                        evidence carry over unchanged.
#   INVEST & PROTECT     protect the income: higher recurring capital spend,
#                        but a tenant shock is far less likely and costs less
#                        when it does land.
#
# Costs flow through the EXISTING reserve and NOI channels -- there is no
# parallel ledger and no double counting (docs/V2_PRODUCT_SPEC.md §2.3).
STANCES: Tuple[str, ...] = ("RUN LEAN", "STANDARD", "INVEST & PROTECT")
STANCE_DEFAULT = "STANDARD"

# Recurring protection cost of the INVEST stance, as an ADDITIONAL capital
# reserve rate. Applied through charge_capital_reserves on the holding's value,
# so a levered fund pays it on the whole asset -- protection is not free.
MANAGEMENT_INVEST_RESERVE_ADDER = 0.010

# A RUN LEAN fund defers upkeep, so it avoids the recurring protection cost but
# not the reserve itself. There is no lean reserve discount: the lean trade is
# paid for in shock risk, not in cash. Documented here so its absence is a
# decision, not an oversight.

# Vacancy-shock probability by property type under the STANDARD stance, before
# market pressure. Office rolls the most space and carries the most tenant risk;
# NNN industrial the least. Multifamily's short leases churn constantly but
# re-lease quickly. Office's base vacancy (13.3%) already exceeds the tight
# threshold, so its pressure multiplier is always >= 1.2 and its base rate is
# set so a calm year lands near a 1-in-4 chance.
MANAGEMENT_SHOCK_PROBABILITY: Dict[str, float] = {
    "Industrial": 0.08,
    "Office": 0.20,
    "Multifamily": 0.12,
    "Retail": 0.18,
}
# Probability multipliers by stance.
MANAGEMENT_STANCE_SHOCK_MULTIPLIER: Dict[str, float] = {
    "RUN LEAN": 1.75,
    "STANDARD": 1.00,
    "INVEST & PROTECT": 0.45,
}
# NOI haircut when a vacancy shock lands, by stance. RUN LEAN loses more
# because deferred upkeep shows up as a deeper re-leasing hit.
MANAGEMENT_STANCE_SHOCK_NOI_IMPACT: Dict[str, float] = {
    "RUN LEAN": 0.12,
    "STANDARD": 0.08,
    "INVEST & PROTECT": 0.03,
}
# A maintenance shock charges this fraction of the holding's value, by stance.
MANAGEMENT_STANCE_MAINTENANCE_RATE: Dict[str, float] = {
    "RUN LEAN": 0.020,
    "STANDARD": 0.012,
    "INVEST & PROTECT": 0.006,
}
# Cap on the market-rent-miss haircut, by stance (share of the year's NOI).
MANAGEMENT_STANCE_RENT_MISS_MAX: Dict[str, float] = {
    "RUN LEAN": 0.10,
    "STANDARD": 0.06,
    "INVEST & PROTECT": 0.02,
}
# Market pressure scales the shock draw: one share point of type-level vacancy
# above the tight-vacancy threshold multiplies the shock probability by this.
MANAGEMENT_VACANCY_PRESSURE_SCALE = 0.04

# Scenario deltas (rate environment, employment growth).
SCENARIO_DELTAS: Dict[str, Dict[str, float]] = {
    "Base Case": {"rate_delta": 0.0, "growth_delta": 0.0},
    "Rate Shock": {"rate_delta": 0.02, "growth_delta": -0.01},
    "Growth Rebound": {"rate_delta": -0.005, "growth_delta": 0.015},
}


def equity_required_for(bid_price: float, ltv: float) -> float:
    """Cash a team must have on hand to close a bid: equity plus closing costs.

    One function, used by bid validation, by the affordability guard in
    ``resolve_round`` and by the bot policy, so the rule cannot drift between
    the check and the charge.
    """
    if bid_price <= 0:
        return 0.0
    return bid_price * (1.0 - ltv) + bid_price * ACQUISITION_COST_RATE


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


def resolve_operating_year(
    property_id: str,
    property_type: str,
    property_value: float,
    noi: float,
    market_vacancy: float,
    stance: str,
    seed: int,
    round_number: int,
) -> Dict[str, object]:
    """Resolve one managed operating year for an owned building. Pure and reproducible.

    The management counterpart to :func:`realized_year_outcome`: same seeding
    discipline (``_stable_seed`` over ``seed:property_id:round_number``), same
    rule that the only place an outcome is decided is one inspectable function.

    What it decides
    ---------------        A vacancy shock may land (Bernoulli), upkeep always lands in expectation
    (Bernoulli over a rate), and a market rent miss may clip the year's income.
    All three are drawn from ONE generator in ONE fixed order, so a replay
    reproduces the year exactly.

    What it does NOT decide
    -----------------------
    NOI growth, cap rates and value. Those stay with ``realized_year_outcome``,
    so the asset stays on the market path and the round feedback a team sees is
    exactly what the engine applied. The shortfall returned here is a cash-flow
    event (this year's uncollected income), which ``apply_management_year``
    nets against the income the fund collects. There is no second scoring path
    and no double counting (docs/V2_PRODUCT_SPEC.md §2.3).
    """
    if stance not in STANCES:
        stance = STANCE_DEFAULT

    rng = np.random.default_rng(_stable_seed(seed, f"{property_id}:ops", round_number))

    # Market pressure: vacancy above the tight threshold makes tenant shocks
    # more likely for everyone, regardless of stance.
    pressure = max(0.0, market_vacancy - TIGHT_VACANCY_THRESHOLD)
    pressure_multiplier = 1.0 + MANAGEMENT_VACANCY_PRESSURE_SCALE * pressure * 100.0

    base_probability = MANAGEMENT_SHOCK_PROBABILITY.get(property_type, 0.15)
    shock_probability = min(
        0.9,
        base_probability
        * MANAGEMENT_STANCE_SHOCK_MULTIPLIER[stance]
        * pressure_multiplier,
    )
    shock_hit = bool(rng.random() < shock_probability)

    # Maintenance: a Bernoulli draw over a per-type rate, stance-adjusted. The
    # expected charge equals the rate, so RUN LEAN pays more often precisely
    # because it defers upkeep.
    maintenance_rate = MANAGEMENT_STANCE_MAINTENANCE_RATE[stance]
    maintenance_hit = bool(rng.random() < 0.5)
    maintenance_charge = property_value * maintenance_rate if maintenance_hit else 0.0

    # Market rent miss: worst-case haircut on the year's NOI, drawn up to the
    # stance cap. Rarely binding under INVEST.
    rent_miss_max = MANAGEMENT_STANCE_RENT_MISS_MAX[stance]
    rent_miss_hit = bool(rng.random() < 0.35)
    rent_miss_rate = float(rng.uniform(0.0, rent_miss_max)) if rent_miss_hit else 0.0

    shock_noi_impact = (
        noi * MANAGEMENT_STANCE_SHOCK_NOI_IMPACT[stance] if shock_hit else 0.0
    )
    rent_miss_impact = noi * rent_miss_rate

    return {
        "property_id": property_id,
        "stance": stance,
        "shock_hit": shock_hit,
        "shock_probability": round(shock_probability, 6),
        "shock_noi_impact": round(shock_noi_impact, 6),
        "maintenance_hit": maintenance_hit,
        "maintenance_charge": round(maintenance_charge, 6),
        "rent_miss": round(rent_miss_impact, 6),
        "total_noi_impact": round(shock_noi_impact + rent_miss_impact, 6),
        "total_cash_impact": round(
            shock_noi_impact + rent_miss_impact + maintenance_charge, 6
        ),
    }


class RoundState(Enum):
    """Round state machine."""
    NOT_STARTED = "not_started"
    OPEN = "open"
    LOCKED = "locked"
    RESOLVED = "resolved"


@dataclass
class OperatingYearResult:
    """One managed operating year for one owned holding.

    Produced by :func:`resolve_operating_year`, stored on the team so the round
    feedback can show what the year did to each building, and reproducible from
    stored state because the inputs (seed, ids, stance, market vacancy) are all
    persisted. The asset's NOI and value are NOT part of this record: management
    moves cash, the market moves value (see ``apply_management_year``).
    """
    property_id: str
    stance: str
    shock_hit: bool
    shock_probability: float
    shock_noi_impact: float
    maintenance_hit: bool
    # Upkeep actually paid this year: the type's maintenance charge plus, under
    # INVEST & PROTECT, the protection premium on the holding's value.
    maintenance_charge: float
    rent_miss: float
    # Income the fund failed to collect this year (shock + rent miss), and the
    # holding's total cash cost (that shortfall plus the upkeep paid).
    total_noi_impact: float
    total_cash_impact: float


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
    # Management stances for the CURRENT round, by property id (V2). One stance
    # per owned building per round; defaults to STANDARD when absent, which is
    # byte-identical to the pre-V2 economics.
    management_decisions: Dict[str, str] = field(default_factory=dict)
    # The resolved operating year per holding, by round (V2). Keyed by the round
    # number as a string, because canonical JSON sorts object keys to strings and
    # this dict must survive a snapshot round trip identically. Kept on the team
    # so feedback and the debrief can narrate what the year did to each building
    # without recomputing it.
    operating_history: Dict[str, List[OperatingYearResult]] = field(default_factory=dict)

    # Cumulative cash-flow channels. These make the NAV decomposition exact:
    #     NAV - starting_equity == sum(current_value - purchase_price)
    #                             + cumulative_income
    #                             - cumulative_interest
    # which is what lets the debrief answer "did leverage create or destroy value"
    # with arithmetic instead of opinion.
    cumulative_income: float = 0.0
    cumulative_interest: float = 0.0
    cumulative_purchase_price: float = 0.0
    cumulative_acquisition_costs: float = 0.0
    cumulative_reserves: float = 0.0


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
    """Property available in a round.

    This is the ONE authoritative in-game representation of a building. The
    underwriting fields below are carried straight from the deterministic
    generator so the game never has to consult a CSV, which previously meant two
    representations of the same asset that could disagree.

    Descriptive vs charged
    ----------------------
    ``indicative_capex_exposure`` is the generator's per-property ``capex_need``.
    It is an *analytical feature describing building condition* and is NOT a cash
    charge in this simulation. The recurring cash charge the engine actually
    levies is ``CAPITAL_RESERVE_RATE``, by property type, applied to value. The
    two are deliberately named differently so a practitioner cannot mistake one
    for the other. See docs/CRE_DATA_VISIBILITY.md.
    """
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
    # ── underwriting context (descriptive) ──
    units: Optional[int] = None
    market_rent: Optional[float] = None
    in_place_rent: Optional[float] = None
    walt: Optional[float] = None
    tenant_concentration: Optional[float] = None
    opex_ratio: Optional[float] = None
    lease_expiry_profile: Optional[str] = None
    property_quality: Optional[float] = None
    primary_risk: Optional[str] = None
    indicative_capex_exposure: Optional[float] = None


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

    def __init__(self, seed: int = 20240331, management_enabled: bool = True):
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        # V2 course tiering: a course mode that declares no management layer
        # (605 and 220 by default) resolves rounds byte-identically to pre-V2.
        self.management_enabled = management_enabled

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
        
        # Closing costs are paid in cash and are not financeable, so a bid is only
        # valid if the team can fund equity *and* transaction costs.
        equity_required = equity_required_for(bid.bid_price, bid.ltv)
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
        
        # Calculate equity and debt. Closing costs are cash, not debt.
        equity_invested = auction_result.winning_bid * (1 - auction_result.winning_ltv)
        debt_amount = auction_result.winning_bid * auction_result.winning_ltv
        acquisition_cost = auction_result.winning_bid * ACQUISITION_COST_RATE
        
        # Update cash
        team.cash -= equity_invested + acquisition_cost
        team.debt += debt_amount
        team.cumulative_purchase_price += auction_result.winning_bid
        team.cumulative_acquisition_costs += acquisition_cost
        
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
        for prop_id, holding in sorted(team.properties.items()):
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

    def collect_property_income(
        self, team: TeamState, noi_shortfall: float = 0.0
    ) -> TeamState:
        """Credit a year of net operating income from every holding to cash.

        Rules
        -----
        income       = sum of each holding's current_noi
                       - noi_shortfall (V2: this year's operating interruption)
        team.cash   += income

        The V2 operating shortfall is netted here rather than carried as a
        separate ledger so the fund's cash identity stays exactly five channels
        (income, interest, reserves, deal costs, equity) and the debrief's NAV
        bridge keeps reconciling without a new term.

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
        # Holdings are summed in property-id order, never in dict order. A state
        # restored from JSON has its keys re-sorted, so an order-dependent sum
        # drifts by an ULP between a replay and the run that produced it. Round
        # resolution has to be reproducible from stored state, so every holding
        # sum in this file iterates sorted.
        income = sum(
            holding.current_noi
            for _, holding in sorted(team.properties.items())
        )
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
            for _, holding in sorted(team.properties.items())
        )
        team.cash -= interest
        team.cumulative_interest += interest
        return team

    def charge_capital_reserves(self, team: TeamState) -> TeamState:
        """Charge one year of capital reserve on every holding.

        Rules
        -----
        reserve      = sum over holdings of (current value * rate for its type)
        team.cash   -= reserve

        Tenant improvements, leasing commissions and replacement reserves are a
        real, recurring cost of owning a building. They scale with the asset, so
        leverage multiplies them -- which is why maximum leverage stops being a
        free lunch once the reserve is charged.

        V2 note: a fund's annual *management* spend (upkeep under the year's
        stance, including the INVEST & PROTECT protection premium) is charged by
        :meth:`apply_management_year`, which is the one place stances are
        consumed, and lands in this same ``cumulative_reserves`` channel. It is
        deliberately not charged here: this method resolves a round's base
        carrying cost, and reading stances twice would let one decision be paid
        for twice.
        """
        reserve = sum(
            holding.current_value * CAPITAL_RESERVE_RATE.get(holding.property_type, 0.012)
            for _, holding in sorted(team.properties.items())
        )
        team.cash -= reserve
        team.cumulative_reserves += reserve
        return team

    def apply_management_year(
        self,
        team: TeamState,
        market_state: MarketState,
        round_number: int,
    ) -> float:
        """Resolve and apply one managed operating year to a fund's holdings (V2).

        Returns the year's total operating income shortfall (vacancy shock plus
        market rent miss), which the caller nets against the income credited by
        :meth:`collect_property_income`.

        Design (docs/V2_PRODUCT_SPEC.md §2.3) -- management is a *cash flow*
        story, not a re-underwriting of the asset:

        * An operating interruption costs this year's income, so it is netted
          out of the income the fund collects. It does not rewrite the holding's
          NOI basis, and it does not move the asset's value: the building is
          still worth what the market says it is worth, and the fund simply did
          not collect a full year's rent.
        * Upkeep (including the INVEST & PROTECT protection premium) is a
          recurring capital cost, so it is charged to cash and booked to
          ``cumulative_reserves`` alongside the base reserve.

        Why this shape: ``update_property_values`` and the reported round
        feedback both read the *market* year for a property, so a holding's NOI
        and value must stay on the market path (tests/test_game_submission.py::
        TestRoundFeedbackConsistency asserts exactly that). Expressing
        management as cash keeps "what a team is told happened is what the
        engine applied" true, keeps the five-channel cash and NAV identities
        exact, and keeps a replay of a seed identical.

        Stances come from ``team.management_decisions`` and are consumed here:
        the dict is cleared after resolution so last round's stance can never
        silently apply to a building the fund has not re-decided.
        """
        if not team.properties:
            team.management_decisions = {}
            return 0.0

        results: List[OperatingYearResult] = []
        total_shortfall = 0.0
        for prop_id, holding in sorted(team.properties.items()):
            stance = team.management_decisions.get(prop_id, STANCE_DEFAULT)
            resolved = resolve_operating_year(
                property_id=prop_id,
                property_type=holding.property_type,
                property_value=holding.current_value,
                noi=holding.current_noi,
                market_vacancy=market_state.vacancy.get(holding.property_type, 0.0),
                stance=stance,
                seed=self.seed,
                round_number=round_number,
            )
            shortfall = float(resolved["total_noi_impact"])
            upkeep = float(resolved["maintenance_charge"])
            if stance == "INVEST & PROTECT":
                upkeep += holding.current_value * MANAGEMENT_INVEST_RESERVE_ADDER

            # Income the fund failed to collect this year, and the upkeep it
            # spent: both are real cash, both land in their existing channels.
            total_shortfall += shortfall
            if upkeep > 0.0:
                team.cash -= upkeep
                team.cumulative_reserves += upkeep

            results.append(
                OperatingYearResult(
                    property_id=prop_id,
                    stance=stance,
                    shock_hit=bool(resolved["shock_hit"]),
                    shock_probability=float(resolved["shock_probability"]),
                    shock_noi_impact=float(resolved["shock_noi_impact"]),
                    maintenance_hit=bool(resolved["maintenance_hit"]),
                    maintenance_charge=round(upkeep, 6),
                    rent_miss=float(resolved["rent_miss"]),
                    total_noi_impact=round(shortfall, 6),
                    total_cash_impact=round(shortfall + upkeep, 6),
                )
            )

        team.operating_history[str(round_number)] = results
        team.management_decisions = {}
        return total_shortfall

    def calculate_nav(self, team: TeamState) -> float:
        """
        Calculate team's Net Asset Value.
        
        NAV = Cash + Property Values - Debt
        """
        property_values = sum(
            holding.current_value for _, holding in sorted(team.properties.items())
        )
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
                        eq = equity_required_for(
                            auction_result.winning_bid, auction_result.winning_ltv
                        )
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
                            eq = equity_required_for(
                                auction_result.winning_bid, auction_result.winning_ltv
                            )
                            if equity_deducted + eq > team.cash:
                                wins_to_unsell.append(prop_id)
                        if prop_id not in wins_to_unsell and auction_result.winning_ltv is not None:
                            equity_deducted += equity_required_for(
                                auction_result.winning_bid, auction_result.winning_ltv
                            )

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
                #   1. resolve this year's management outcomes: the operating
                #      shortfall (netted out of income in step 2) and the upkeep
                #      the fund spent (charged to cash and reserves here) (V2)
                #   2. collect this year's NOI, less that shortfall
                #   3. then revalue, which advances each holding's NOI to next
                #      year on the same market path the round feedback reports
                #   4. then fund the base capital reserve on the revalued asset
                #   5. then pay interest on the debt that financed it
                operating_shortfall = 0.0
                if self.management_enabled:
                    operating_shortfall = self.apply_management_year(
                        updated_team, market_state, round_number
                    )
                updated_team = self.collect_property_income(
                    updated_team, noi_shortfall=operating_shortfall
                )
                updated_team = self.update_property_values(updated_team, market_state, round_number)
                updated_team = self.charge_capital_reserves(updated_team)
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
            # V2: this fund's resolved operating years, newest last, so round
            # feedback can show what the year did to each building. It is the
            # fund's own record — no other fund's appears here.
            "operating_history": [
                {
                    "round": round_number,
                    "results": [
                        {
                            "property_id": r.property_id,
                            "stance": r.stance,
                            "shock_hit": r.shock_hit,
                            "shock_probability": r.shock_probability,
                            "shock_noi_impact": r.shock_noi_impact,
                            "maintenance_charge": r.maintenance_charge,
                            "rent_miss": r.rent_miss,
                            "total_noi_impact": r.total_noi_impact,
                            "total_cash_impact": r.total_cash_impact,
                        }
                        for r in results
                    ],
                }
                for round_number, results in sorted(
                    team_state.operating_history.items()
                )
            ],
        }
