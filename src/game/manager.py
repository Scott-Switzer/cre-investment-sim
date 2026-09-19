"""
Game_manager - Round state machine and game flow orchestration.

Manages the complete game lifecycle:
- Practice round (non-scored)
- 4 scored rounds
- Round state transitions (NOT_STARTED -> OPEN -> LOCKED -> RESOLVED)
- Property selection for each round
- Bid collection
- Adjudication
- Portfolio persistence across rounds
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
import numpy as np

from src.game.adjudicator import (
    Adjudicator,
    RoundState,
    BidStatus,
    TeamState,
    Bid,
    PropertyMarket,
    MarketState,
    RoundResult,
    ModelPrediction,
    PropertyOutcome,
    STANCES,
    STANCE_DEFAULT,
)
from src.data.properties import generate_properties, synthetic_year_built


def _opt_float(value):
    """A generator cell as an optional float, treating NaN as "not applicable".

    The property generator leaves genuine blanks (``units`` on an office building)
    rather than filling them, so NaN must become ``None``. Without this, a missing
    cell reads as present and a pool of offices cannot be constructed at all.
    """
    if value is None:
        return None
    try:
        if value != value:  # NaN, the only value that is not equal to itself
            return None
    except (TypeError, ValueError):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _opt_int(value):
    as_float = _opt_float(value)
    return None if as_float is None else int(as_float)


def _opt_str(value):
    if value is None:
        return None
    try:
        if value != value:
            return None
    except (TypeError, ValueError):
        return None
    return str(value)


@dataclass(frozen=True)
class CourseProfile:
    """What one instructional tier turns on. Data, not a code path.

    Course tiering exists so one engine serves REAL 605, 310 and 220 without three
    applications. A tier is therefore a *declaration*: how many models the packet
    requires, whether the operating year is simulated at all, and which management
    stances a fund may set. Gameplay logic reads these fields and nothing else, so
    adding a tier is adding a row here plus a bundle that names it
    (docs/V2_PRODUCT_SPEC.md §3).
    """

    course_mode: str
    label: str
    # The model ladder the packet asks for, weakest first. Guidance text derives
    # from this; 605 is deliberately the valuation-only tier.
    required_models: tuple
    # When False the operating year is never simulated: round resolution is
    # byte-identical to pre-V2 economics. 605 ships this way.
    management_enabled: bool
    # The stances this tier accepts. A single-stance tier shows no stance surface.
    stances: tuple

    @property
    def has_stance_choice(self) -> bool:
        return len(self.stances) > 1


# The three tiers. 605 first because it is the published classroom tier and the
# engine default: the simplest game, one model, no management layer.
COURSE_PROFILES: Dict[str, CourseProfile] = {
    "605": CourseProfile(
        course_mode="605",
        label="REAL 605 — valuation only (classroom stress test)",
        required_models=("valuation",),
        management_enabled=False,
        stances=(STANCE_DEFAULT,),
    ),
    "310": CourseProfile(
        course_mode="310",
        label="REAL 310 — full model ladder with the management layer",
        required_models=("valuation", "vacancy", "income"),
        management_enabled=True,
        stances=STANCES,
    ),
    "220": CourseProfile(
        course_mode="220",
        label="REAL 220 — simplified regression tier, operating year at STANDARD",
        required_models=("valuation",),
        management_enabled=True,
        stances=(STANCE_DEFAULT,),
    ),
}

DEFAULT_COURSE_MODE = "605"


def course_profile(course_mode: str) -> CourseProfile:
    """Resolve a tier by name. An unknown tier is an error, never a default."""
    try:
        return COURSE_PROFILES[course_mode]
    except KeyError:
        known = ", ".join(sorted(COURSE_PROFILES))
        raise ValueError(
            f"unknown course_mode '{course_mode}'; known tiers: {known}"
        ) from None


@dataclass
class GameConfig:
    """Game configuration.

    V2 adds the course-mode seam (docs/V2_PRODUCT_SPEC.md §3): one engine, the
    instructional tier declared as data. `course_mode` selects a
    :class:`CourseProfile`; it introduces no code forks beyond what that profile
    declares, and the 605 tier reproduces the pre-V2 economics exactly.
    """
    seed: int = 20240331
    starting_equity: float = 100.0  # in millions
    total_rounds: int = 4
    properties_per_round: int = 4
    practice_round: bool = True
    scenario: str = "Base Case"
    # The published classroom tier. Sessions that want the V2 management layer
    # name 310; the tier, not this file, decides what the layer does.
    course_mode: str = DEFAULT_COURSE_MODE
    # Escape hatch for engineering sessions (balance harnesses, a lab build that
    # wants the management layer on a 605 pool). `None` means "whatever the
    # course profile declares", which is the only sane default: two independent
    # switches for one behaviour is exactly how a classroom ends up running a
    # configuration nobody chose. Stance legality still follows the profile.
    management_enabled: Optional[bool] = None

    @property
    def profile(self) -> CourseProfile:
        return course_profile(self.course_mode)

    @property
    def management_active(self) -> bool:
        """Does round resolution simulate the operating year?"""
        if self.management_enabled is None:
            return self.profile.management_enabled
        return bool(self.management_enabled)


@dataclass
class ClassroomTiming:
    """Classroom time budget for a preset. Advisory only -- there are no timers.

    The instructor opens and locks rounds manually; these numbers exist so the
    game can print a realistic agenda and so the two class formats are explicit
    configuration rather than tribal knowledge.
    """
    name: str
    practice_minutes: int
    round_minutes: int
    debrief_minutes: int
    total_rounds: int

    @property
    def scored_minutes(self) -> int:
        return self.round_minutes * self.total_rounds

    @property
    def total_minutes(self) -> int:
        return (
            5  # rules / briefing
            + self.practice_minutes
            + self.scored_minutes
            + self.debrief_minutes
        )


CLASSROOM_TIMINGS: Dict[str, ClassroomTiming] = {
    "QUICK CLASS": ClassroomTiming(
        name="QUICK CLASS",
        practice_minutes=6,
        round_minutes=9,
        debrief_minutes=18,
        total_rounds=4,
    ),
    "EXTENDED CLASS": ClassroomTiming(
        name="EXTENDED CLASS",
        practice_minutes=8,
        round_minutes=12,
        debrief_minutes=25,
        total_rounds=6,
    ),
}

DEFAULT_TIMING_PRESET = "QUICK CLASS"


def game_stage(game_manager) -> str:
    """The single authoritative label for where a game currently is.

    Used by the instructor progress bar and the live screen so both always agree
    on whether the class is in practice, in round N, or in the debrief.
    """
    if getattr(game_manager, "game_complete", False):
        return "DEBRIEF"
    if game_manager.current_round < 0:
        return "PRACTICE"
    return f"ROUND {game_manager.current_round + 1}"


def stage_steps(game_manager) -> List[str]:
    """The full ordered agenda for this game."""
    steps: List[str] = []
    if game_manager.config.practice_round:
        steps.append("PRACTICE")
    steps.extend(f"ROUND {i + 1}" for i in range(game_manager.config.total_rounds))
    steps.append("DEBRIEF")
    return steps


def game_config_for_timing(
    preset: str = DEFAULT_TIMING_PRESET,
    seed: int = 20240331,
    starting_equity: float = 100.0,
    scenario: str = "Base Case",
) -> GameConfig:
    """Build a GameConfig for a named classroom timing preset."""
    timing = CLASSROOM_TIMINGS[preset]
    return GameConfig(
        seed=seed,
        starting_equity=starting_equity,
        total_rounds=timing.total_rounds,
        properties_per_round=4,
        practice_round=True,
        scenario=scenario,
    )


@dataclass
class RoundConfig:
    """Configuration for a single round."""
    round_number: int
    is_practice: bool
    property_ids: List[str]
    duration_minutes: int = 8


class GameManager:
    """
    Manages the complete game lifecycle and round state machine.
    
    Responsibilities:
    - Initialize teams with starting capital
    - Select properties for each round
    - Manage round state transitions
    - Collect bids from teams
    - Run adjudication
    - Update portfolios
    - Track game history
    """
    
    def __init__(self, config: GameConfig):
        self.config = config
        self.adjudicator = Adjudicator(
            seed=config.seed, management_enabled=config.management_active
        )
        
        # Game state
        self.teams: Dict[str, TeamState] = {}
        self.current_round: int = 0
        self.round_state: RoundState = RoundState.NOT_STARTED
        self.game_started: bool = False
        self.game_complete: bool = False
        
        # Round-specific state
        self.current_properties: Dict[str, PropertyMarket] = {}
        self.submitted_bids: List[Bid] = []
        self.current_round_result: Optional[RoundResult] = None
        
        # History
        self.round_history: Dict[int, RoundResult] = {}
        self.market_history: List[MarketState] = []

        # Human-readable event log. Instructors use it to see what happened
        # without reading state, and it is the audit trail for round control.
        self.event_log: List[Dict[str, object]] = []
        
        # Property pool
        self.all_properties: Dict[str, PropertyMarket] = {}
        self._generate_property_pool()
    
    def _generate_property_pool(self):
        """Generate the pool of properties for the game."""
        # Generate properties using existing property generator
        props_df = generate_properties(seed=self.config.seed, count=120)
        
        # Use a seeded RNG for deterministic reserve prices
        rng = np.random.default_rng(self.config.seed)
        
        for _, row in props_df.iterrows():
            # Calculate reserve price (90-95% of asking price) - deterministic
            reserve_price = row["asking_price"] * rng.uniform(0.90, 0.95)
            
            self.all_properties[row["property_id"]] = PropertyMarket(
                property_id=row["property_id"],
                property_name=row["property_name"],
                property_type=row["type"],
                submarket=row["submarket"],
                asking_price=row["asking_price"],
                current_noi=row["current_noi"],
                current_cap=row["going_in_cap"],
                occupancy=row["occupancy"],
                # The generator column is `size_sf`; `building_sf` is accepted only
                # as a fallback so no caller silently gets a defaulted size.
                building_sf=_opt_float(row.get("size_sf"))
                or _opt_float(row.get("building_sf"))
                or 100000.0,
                year_built=_opt_int(row.get("year_built"))
                or synthetic_year_built(
                    row["property_id"], _opt_float(row.get("property_quality")) or 0.5
                ),
                max_ltv=row["max_ltv"],
                debt_rate=row["debt_rate"],
                amortization_years=row["amortization_years"],
                reserve_price=reserve_price,
                # Underwriting context, carried from the same generator row that
                # produced every other field, so there is one representation of
                # this building rather than a rich CSV and a thin pool object.
                units=_opt_int(row.get("units")),
                market_rent=_opt_float(row.get("market_rent")),
                in_place_rent=_opt_float(row.get("in_place_rent")),
                walt=_opt_float(row.get("walt")),
                tenant_concentration=_opt_float(row.get("tenant_concentration")),
                opex_ratio=_opt_float(row.get("opex_ratio")),
                lease_expiry_profile=_opt_str(row.get("lease_expiry_profile")),
                property_quality=_opt_float(row.get("property_quality")),
                primary_risk=_opt_str(row.get("primary_risk")),
                # Named for what it is: descriptive, not a NAV charge.
                indicative_capex_exposure=_opt_float(row.get("capex_need")),
            )
    
    def log(self, message: str, **details) -> None:
        """Append an entry to the game's event log.

        Deliberately simple: an inspectable, ordered record of what the operator
        did and when, so a round control action can always be traced.
        """
        self.event_log.append({
            "round": self.current_round,
            "state": self.round_state.value,
            "message": message,
            "at": datetime.now().isoformat(timespec="seconds"),
            **details,
        })

    def add_team(self, team_id: str, team_name: str, model_predictions: Optional[Dict[str, ModelPrediction]] = None):
        """Add a team to the game."""
        self.teams[team_id] = TeamState(
            team_id=team_id,
            team_name=team_name,
            cash=self.config.starting_equity,
            equity_capital=self.config.starting_equity,
            nav=self.config.starting_equity,
            model_predictions=model_predictions or {},
        )
    
    def start_game(self):
        """Start the game and initialize the first round."""
        if self.game_started:
            raise RuntimeError("Game already started")
        
        self.game_started = True
        self.current_round = 0
        
        if self.config.practice_round:
            self._setup_practice_round()
        else:
            self._setup_scored_round(0)
    
    def _setup_practice_round(self):
        """Setup the practice round (non-scored)."""
        self.round_state = RoundState.OPEN
        
        # Select 1 property for practice
        property_ids = list(self.all_properties.keys())[:1]
        self.current_properties = {
            pid: self.all_properties[pid]
            for pid in property_ids
        }
        
        self.current_round = -1  # Practice round is -1
    
    def _setup_scored_round(self, round_number: int):
        """Setup a scored round."""
        self.round_state = RoundState.OPEN
        self.current_round = round_number
        
        # Select properties for this round
        # Use different properties for each round
        start_idx = round_number * self.config.properties_per_round
        end_idx = start_idx + self.config.properties_per_round
        property_ids = list(self.all_properties.keys())[start_idx:end_idx]
        
        self.current_properties = {
            pid: self.all_properties[pid]
            for pid in property_ids
        }
    
    def set_management_stances(self, team_id: str, stances: Dict[str, str]) -> None:
        """Record this fund's management stance for each owned building (V2).

        Legal only while the round is open — stances are decisions, decided in
        the same window as bids and consumed at resolution. A stance for a
        building the fund does not own is refused rather than stored, so the
        decision surface cannot drift away from the actual book.
        """
        if self.round_state != RoundState.OPEN:
            raise RuntimeError("Round is not open for submissions")
        team = self.teams.get(team_id)
        if team is None:
            raise ValueError(f"Team {team_id} not in game")
        # Legal stances come from the course tier, not from the caller. A tier
        # that does not simulate the operating year accepts none of them -- storing
        # one would record a decision that can never be honoured -- and a tier with
        # no stance choice accepts only its default.
        if not self.config.management_active:
            raise ValueError(
                f"course tier {self.config.course_mode} does not simulate the "
                "operating year, so no management stance is accepted"
            )
        allowed = set(self.config.profile.stances)
        for prop_id, stance in stances.items():
            if prop_id not in team.properties:
                raise ValueError(f"Property {prop_id} is not in this fund's portfolio")
            if stance not in allowed:
                raise ValueError(f"Unknown management stance '{stance}'")
        team.management_decisions = dict(stances)

    def submit_bid(self, bid: Bid) -> bool:
        """Submit a bid for the current round."""
        if self.round_state != RoundState.OPEN:
            raise RuntimeError("Round is not open for submissions")
        
        if bid.round_number != self.current_round:
            raise RuntimeError("Bid round number does not match current round")
        
        if bid.team_id not in self.teams:
            raise ValueError(f"Team {bid.team_id} not in game")
        
        # Validate bid
        property_market = self.current_properties.get(bid.property_id)
        if property_market is None:
            raise ValueError(f"Property {bid.property_id} not in current round")
        
        team = self.teams[bid.team_id]
        status, reason = self.adjudicator.validate_bid(bid, team, property_market, self.round_state)
        
        if status != BidStatus.VALID:
            raise ValueError(f"Invalid bid: {reason}")
        
        # Prevent duplicate bids for same team+property+round
        for existing_bid in self.submitted_bids:
            if (existing_bid.team_id == bid.team_id and
                existing_bid.property_id == bid.property_id and
                existing_bid.round_number == bid.round_number):
                raise RuntimeError("Already submitted a bid for this property in this round")
        
        self.submitted_bids.append(bid)
        return True
    
    def lock_round(self):
        """Lock the round and close submissions."""
        if self.round_state != RoundState.OPEN:
            raise RuntimeError("Round is not open")
        
        self.round_state = RoundState.LOCKED
    
    def resolve_round(self) -> RoundResult:
        """Resolve the current round using the adjudicator."""
        if self.round_state != RoundState.LOCKED:
            raise RuntimeError("Round must be locked before resolution")
        
        # Get previous market state
        previous_market = self.market_history[-1] if self.market_history else None
        
        # Resolve the round
        result = self.adjudicator.resolve_round(
            round_number=self.current_round,
            teams=self.teams,
            properties=self.current_properties,
            bids=self.submitted_bids,
            previous_market=previous_market,
            scenario=self.config.scenario,
        )
        
        # Store result
        self.current_round_result = result
        if self.current_round >= 0:  # Only store scored rounds
            self.round_history[self.current_round] = result
        
        # Update market history
        self.market_history.append(result.market_state)
        
        # Update team states from result
        for team_id, updated_team in result.portfolio_updates.items():
            self.teams[team_id] = updated_team
        
        # Clear bids for next round
        self.submitted_bids = []
        
        # Update round state
        self.round_state = RoundState.RESOLVED
        
        return result
    
    def advance_round(self):
        """Advance to the next round."""
        if self.round_state != RoundState.RESOLVED:
            raise RuntimeError("Current round must be resolved before advancing")
        
        # Check if practice round just completed
        if self.current_round == -1:
            # Move to Round 1
            self._setup_scored_round(0)
        elif self.current_round < self.config.total_rounds - 1:
            # Move to next scored round
            self._setup_scored_round(self.current_round + 1)
        else:
            # Game complete
            self.game_complete = True
            self.round_state = RoundState.NOT_STARTED
    
    def get_team_observation(self, team_id: str) -> Dict:
        """Get the player-visible observation for a team."""
        if team_id not in self.teams:
            raise ValueError(f"Team {team_id} not in game")
        
        team = self.teams[team_id]
        
        if self.current_round_result:
            return self.adjudicator.get_player_observation(
                team_id,
                self.current_round_result,
                team.model_predictions,
            )
        else:
            # Return basic team state if no round result yet
            return {
                "team_id": team_id,
                "cash": team.cash,
                "nav": team.nav,
                "cumulative_return": team.cumulative_return,
                "properties": {
                    pid: {
                        "property_id": h.property_id,
                        "purchase_price": h.purchase_price,
                        "current_value": h.current_value,
                        "current_noi": h.current_noi,
                        "property_type": h.property_type,
                        "submarket": h.submarket,
                    }
                    for pid, h in team.properties.items()
                },
                "model_predictions": team.model_predictions,
            }
    
    def get_leaderboard(self) -> List[Dict]:
        """Get the current leaderboard ranked by NAV, ties broken by team id.

        The tie-break is not decoration. Funds start level at the same NAV, so a
        leaderboard sorted on NAV alone is ordered entirely by iteration order at
        the start of the game -- and that order is not preserved by a round trip
        through canonical JSON, which sorts object keys.
        """
        leaderboard = []
        for team_id, team in self.teams.items():
            leaderboard.append({
                "team_id": team_id,
                "team_name": team.team_name,
                "nav": team.nav,
                "cash": team.cash,
                "debt": team.debt,
                "properties": len(team.properties),
                "cumulative_return": team.cumulative_return,
            })

        leaderboard.sort(key=lambda x: (-x["nav"], x["team_id"]))
        return leaderboard
    
    def get_game_summary(self) -> Dict:
        """Get a summary of the complete game."""
        return {
            "config": {
                "seed": self.config.seed,
                "starting_equity": self.config.starting_equity,
                "total_rounds": self.config.total_rounds,
                "properties_per_round": self.config.properties_per_round,
                "scenario": self.config.scenario,
            },
            "game_started": self.game_started,
            "game_complete": self.game_complete,
            "current_round": self.current_round,
            "round_state": self.round_state.value,
            "teams": {
                team_id: {
                    "team_name": team.team_name,
                    "nav": team.nav,
                    "cumulative_return": team.cumulative_return,
                    "properties": len(team.properties),
                }
                for team_id, team in self.teams.items()
            },
            "round_history": {
                round_num: {
                    "market_state": {
                        "policy_rate": result.market_state.policy_rate,
                        "unemployment": result.market_state.unemployment,
                        "employment_growth": result.market_state.employment_growth,
                    },
                    "auction_results": {
                        prop_id: {
                            "sold": result.sold,
                            "winning_team_id": result.winning_team_id,
                            "winning_bid": result.winning_bid,
                        }
                        for prop_id, result in result.auction_results.items()
                    },
                }
                for round_num, result in self.round_history.items()
            },
        }


def create_demo_game(seed: int = 20240331) -> GameManager:
    """Create a demo game with 4 pre-seeded teams."""
    config = GameConfig(seed=seed, starting_equity=100.0, total_rounds=4)
    game = GameManager(config)
    
    # Add 4 demo teams with different model archetypes
    game.add_team("Value Model", "Value Model")
    game.add_team("Growth Model", "Growth Model")
    game.add_team("Risk Model", "Risk Model")
    game.add_team("Noisy Model", "Noisy Model")
    
    return game
