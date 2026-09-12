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

from src.game.adjudicator import Adjudicator, RoundState, BidStatus, TeamState, Bid, PropertyMarket, MarketState, RoundResult, ModelPrediction, PropertyOutcome
from src.data.properties import generate_properties


@dataclass
class GameConfig:
    """Game configuration."""
    seed: int = 20240331
    starting_equity: float = 100.0  # in millions
    total_rounds: int = 4
    properties_per_round: int = 4
    practice_round: bool = True
    scenario: str = "Base Case"


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
        self.adjudicator = Adjudicator(seed=config.seed)
        
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
                building_sf=row.get("building_sf", 100000),
                year_built=row.get("year_built", 1995),
                max_ltv=row["max_ltv"],
                debt_rate=row["debt_rate"],
                amortization_years=row["amortization_years"],
                reserve_price=reserve_price,
            )
    
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
        """Get the current leaderboard ranked by NAV."""
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
        
        leaderboard.sort(key=lambda x: x["nav"], reverse=True)
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
