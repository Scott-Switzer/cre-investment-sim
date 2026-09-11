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
        
        # Handle exact bid price ties with deterministic seed
        tied_bids = [b for b in valid_bids if abs(b.bid_price - winning_bid.bid_price) < 0.001]
        if len(tied_bids) > 1:
            # Use SHA-256-derived seed for deterministic cross-process tie-break
            tie_seed = _stable_seed(self.seed, property_id, round_number)
            tie_rng = np.random.default_rng(tie_seed)
            winning_bid = tied_bids[tie_rng.integers(0, len(tied_bids))]
        
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
    ) -> TeamState:
        """
        Update team's portfolio after auction resolution.
        
        Rules:
        - If won: deduct equity, add debt, add property to portfolio
        - If lost: no change
        - Track human override vs model prediction
        """
        if not auction_result.sold or auction_result.winning_team_id != team.team_id:
            return team
        
        # Calculate equity and debt
        equity_invested = auction_result.winning_bid * (1 - auction_result.winning_ltv)
        debt_amount = auction_result.winning_bid * auction_result.winning_ltv
        
        # Update cash
        team.cash -= equity_invested
        team.debt += debt_amount
        
        # Add property to portfolio
        holding = PropertyHolding(
            property_id=property_market.property_id,
            purchase_price=auction_result.winning_bid,
            purchase_round=round_number,
            equity_invested=equity_invested,
            debt_amount=debt_amount,
            debt_rate=property_market.debt_rate,
            amortization_years=property_market.amortization_years,
            current_noi=property_market.current_noi,
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
        # Scenario-based deltas (simplified for MVP)
        scenario_deltas = {
            "Base Case": {"rate_delta": 0.0, "growth_delta": 0.0},
            "Rate Shock": {"rate_delta": 0.02, "growth_delta": -0.01},
            "Growth Rebound": {"rate_delta": -0.005, "growth_delta": 0.015},
        }
        
        delta = scenario_deltas.get(scenario, scenario_deltas["Base Case"])
        
        if previous_market is None:
            # Initialize base market
            policy_rate = 0.053
            unemployment = 0.039
            employment_growth = 0.006
            inflation = 0.028
            credit_conditions = 0.5
        else:
            # Evolve from previous
            policy_rate = max(0.01, previous_market.policy_rate + delta["rate_delta"] + self.rng.normal(0, 0.002))
            unemployment = max(0.02, min(0.15, previous_market.unemployment + self.rng.normal(0, 0.001)))
            employment_growth = previous_market.employment_growth + delta["growth_delta"] + self.rng.normal(0, 0.002)
            inflation = max(0.01, min(0.10, previous_market.inflation + self.rng.normal(0, 0.001)))
            credit_conditions = max(0.0, min(1.0, previous_market.credit_conditions + self.rng.normal(0, 0.05)))
        
        # Property-type specific market conditions
        base_vacancy = {"Industrial": 0.055, "Office": 0.133, "Multifamily": 0.036, "Retail": 0.065}
        base_cap_rate = {"Industrial": 0.055, "Office": 0.072, "Multifamily": 0.052, "Retail": 0.065}
        base_rent_index = {"Industrial": 1.49, "Office": 2.89, "Multifamily": 2944.0, "Retail": 3.05}
        
        vacancy = {}
        cap_rate = {}
        asking_rent_index = {}
        
        for ptype in ["Industrial", "Office", "Multifamily", "Retail"]:
            if previous_market is None:
                vacancy[ptype] = base_vacancy[ptype]
                cap_rate[ptype] = base_cap_rate[ptype]
                asking_rent_index[ptype] = base_rent_index[ptype]
            else:
                # Evolve with scenario influence + noise
                vac_change = -delta["growth_delta"] * 0.5 + self.rng.normal(0, 0.005)
                vacancy[ptype] = max(0.01, min(0.30, previous_market.vacancy[ptype] + vac_change))
                
                cap_change = delta["rate_delta"] * 0.3 + self.rng.normal(0, 0.001)
                cap_rate[ptype] = max(0.03, min(0.12, previous_market.cap_rate[ptype] + cap_change))
                
                rent_change = delta["growth_delta"] * 0.4 + self.rng.normal(0, 0.02)
                asking_rent_index[ptype] = base_rent_index[ptype] * (1 + rent_change)
        
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
        Update property values based on market evolution.
        
        Rules:
        - NOI changes based on property type + market conditions + idiosyncratic noise
        - Cap rates update based on market state
        - Property values = NOI / Cap Rate
        - All randomness is seeded
        """
        for prop_id, holding in team.properties.items():
            # Get property-type specific market conditions
            ptype = holding.property_type
            market_vacancy = market_state.vacancy[ptype]
            market_cap = market_state.cap_rate[ptype]
            market_rent_growth = market_state.asking_rent_index[ptype]
            
            # NOI growth: market conditions + idiosyncratic noise
            rng = np.random.default_rng(_stable_seed(self.seed, prop_id, round_number))
            base_noi_growth = 0.02 + (0.0 if market_vacancy > 0.08 else 0.01)
            noi_growth = base_noi_growth + rng.normal(0, 0.015)
            noi_growth = max(-0.10, min(0.15, noi_growth))
            
            # Update NOI
            holding.current_noi = holding.current_noi * (1 + noi_growth)
            
            # Update cap rate (market cap + small property-specific noise)
            prop_cap = market_cap + rng.normal(0, 0.0005)
            prop_cap = max(0.03, min(0.12, prop_cap))
            
            # Update value
            holding.current_value = holding.current_noi / prop_cap
        
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
        
        for prop_id, prop_market in properties.items():
            prop_bids = [b for b in bids if b.property_id == prop_id]
            auction_result = self.resolve_auction(prop_id, prop_bids, prop_market, teams)
            auction_results[prop_id] = auction_result
            
            # Generate property outcome
            rng = np.random.default_rng(_stable_seed(self.seed, prop_id, round_number))
            ptype = prop_market.property_type
            noi_growth = 0.02 + rng.normal(0, 0.015)
            cap_rate = market_state.cap_rate[ptype] + rng.normal(0, 0.0005)
            exit_noi = prop_market.current_noi * (1 + noi_growth)
            exit_value = exit_noi / cap_rate
            
            property_outcomes[prop_id] = PropertyOutcome(
                property_id=prop_id,
                noi_growth_actual=round(noi_growth, 6),
                cap_rate_actual=round(cap_rate, 6),
                exit_value=round(exit_value, 6),
                exit_noi=round(exit_noi, 6),
                occupancy_change=round(-noi_growth * 0.5 + rng.normal(0, 0.003), 6),
            )
        
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
                            prop_id in properties):
                            eq = auction_result.winning_bid * (1 - auction_result.winning_ltv)
                            if equity_deducted + eq > team.cash:
                                wins_to_unsell.append(prop_id)
                        if prop_id not in wins_to_unsell:
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
                            updated_team, auction_result, properties[prop_id], round_number
                        )
                # Update property values for existing holdings
                updated_team = self.update_property_values(updated_team, market_state, round_number)
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
