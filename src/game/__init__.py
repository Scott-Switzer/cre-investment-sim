"""
Game module for multi-round simulation.

Contains:
- adjudicator.py: Explicit rules engine for bid validation, auction resolution, market evolution
- manager.py: Game lifecycle and round state machine
"""

from src.game.adjudicator import (
    Adjudicator,
    RoundState,
    BidStatus,
    TeamState,
    ModelPrediction,
    PropertyHolding,
    OverrideRecord,
    Bid,
    AuctionResult,
    MarketState,
    PropertyMarket,
    RoundResult,
)

from src.game.manager import (
    GameManager,
    GameConfig,
    RoundConfig,
    create_demo_game,
)

__all__ = [
    "Adjudicator",
    "RoundState",
    "BidStatus",
    "TeamState",
    "ModelPrediction",
    "PropertyHolding",
    "OverrideRecord",
    "Bid",
    "AuctionResult",
    "MarketState",
    "PropertyMarket",
    "RoundResult",
    "GameManager",
    "GameConfig",
    "RoundConfig",
    "create_demo_game",
]
