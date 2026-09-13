"""
Deterministic demo-bot policies.

These are NOT AI agents. They are fixed, inspectable strategies used to populate
a demonstration game so an instructor can watch a multi-team market without four
people in the room. They are also useful in tests because they are reproducible.

Four archetypes, matching the demo team spread:

    Value Fund    good valuations, disciplined bids
    Growth Fund   optimistic NOI, aggressive bids
    Risk Fund     conservative downside view, low leverage
    Noisy Model   weak, high-variance predictions

Why bids are anchored to the asking price
-----------------------------------------
A bot whose bid is a fraction of its *own* max bid will never transact when the
seller's hidden reserve sits near the asking price: conservative bidders simply
lose every auction, never test their model, and finish at exactly their starting
NAV. That makes for a flat, uninformative demo.

Real bidders see the ask and bid relative to it, capped by their own model. So
each policy computes an ask-anchored bid and then takes the MINIMUM with the
model's max bid. The model still disciplines the bidder -- it just does so as a
ceiling rather than as a starting point.
"""

from __future__ import annotations

from typing import Optional

from src.game.adjudicator import ModelPrediction, equity_required_for

# How much above/below the asking price each archetype is willing to reach.
# These are the *contested* bid levels: they decide who wins when more than one
# fund wants the same asset. They are deliberately close together -- a demo in
# which one archetype outbids everyone on every deal teaches nothing about
# analysis, only about aggression.
VALUE_ASK_MULTIPLE = 0.99
GROWTH_ASK_MULTIPLE = 1.03
RISK_ASK_MULTIPLE = 0.955

# Minimum model edge (discount to ask) before the archetype will act at all.
# These are conviction filters, so each fund sits out deals it cannot price.
# They are kept comparable: the archetypes should disagree about *which* assets
# are attractive, not about whether to participate in the market at all.
VALUE_MIN_EDGE = -0.03
GROWTH_MIN_EDGE = -0.02
RISK_MIN_EDGE = -0.02
RISK_MAX_DOWNSIDE = 0.45

LTV_CAP_VALUE = 0.70
LTV_CAP_RISK = 0.60

# Absolute leverage ceiling for a bot when the asset's own limit is unknown.
LTV_CEILING_DEFAULT = 0.75
MIN_LTV = 0.05


def _as_float(value) -> Optional[float]:
    """Coerce to float only when the value really is a number.

    Model stubs and mocks may carry non-numeric sentinel attributes; treating
    those as a leverage limit would silently produce absurd LTVs.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def bot_strategy(
    team_id: str,
    prediction: ModelPrediction,
    asking_price: float,
    property_max_ltv: Optional[float] = None,
) -> dict:
    """Decide whether and how a demo bot bids on one property.

    ``property_max_ltv`` is the lender ceiling for THIS asset. It must be passed:
    leverage that exceeds it is rejected by the adjudicator, so a bot that ignores
    it would simply never transact.

    Returns a dict with ``should_bid``, ``bid_price``, ``ltv`` and ``confidence``.
    """
    fair_value = prediction.predicted_fair_value
    max_bid = prediction.max_bid
    edge = fair_value - asking_price
    edge_pct = edge / asking_price if asking_price > 0 else 0.0
    downside = prediction.probability_of_downside
    ltv_ceiling = _as_float(property_max_ltv)

    def cap_ltv(value: float) -> float:
        value = min(value, LTV_CEILING_DEFAULT)
        if ltv_ceiling is not None:
            value = min(value, ltv_ceiling)
        return max(value, MIN_LTV)

    if "Value" in team_id:
        if edge_pct < VALUE_MIN_EDGE:
            return _pass()
        price = min(max_bid, asking_price * VALUE_ASK_MULTIPLE)
        ltv = cap_ltv(min(prediction.target_ltv, LTV_CAP_VALUE))
        confidence = 0.85

    elif "Growth" in team_id:
        if edge_pct < GROWTH_MIN_EDGE:
            return _pass()
        # Willing to chase, but never beyond what it thinks the asset is worth.
        price = min(max_bid, asking_price * GROWTH_ASK_MULTIPLE, fair_value * 0.99)
        ltv = cap_ltv(prediction.target_ltv + 0.05)
        confidence = 0.75

    elif "Risk" in team_id:
        if edge_pct < RISK_MIN_EDGE:
            return _pass()
        if downside is not None and downside > RISK_MAX_DOWNSIDE:
            return _pass()
        price = min(max_bid, asking_price * RISK_ASK_MULTIPLE)
        ltv = cap_ltv(min(prediction.target_ltv - 0.10, LTV_CAP_RISK))
        confidence = 0.90

    else:
        # Unknown archetype: moderately disciplined.
        if edge_pct < 0:
            return _pass()
        price = min(max_bid, asking_price * 0.97)
        ltv = cap_ltv(prediction.target_ltv)
        confidence = 0.80

    if price <= 0:
        return _pass()

    return {
        "should_bid": True,
        "bid_price": float(price),
        "ltv": float(ltv),
        "confidence": float(confidence),
    }


def _pass() -> dict:
    return {"should_bid": False, "bid_price": 0.0, "ltv": 0.0, "confidence": 0.0}


def is_bot(team_id: str, human_team_id: str) -> bool:
    """The human team never has its bids generated for it."""
    return team_id != human_team_id


def affordable(
    bid_price: float,
    ltv: float,
    cash: float,
    property_max_ltv: float,
    already_submitted: bool = False,
) -> bool:
    """Apply the same constraints the adjudicator will apply.

    Bots obey the rules; they are not privileged. A bot that ignores the capital
    constraint would make the demo dishonest.
    """
    if already_submitted:
        return False
    if bid_price <= 0:
        return False
    if ltv <= 0 or ltv > property_max_ltv:
        return False
    # Equity plus closing costs, exactly as the adjudicator will require it.
    return cash >= equity_required_for(bid_price, ltv)


def submit_bot_bids(
    game_manager,
    human_team_id: str,
    valid_property_ids: Optional[list[str]] = None,
) -> int:
    """Submit bids for every non-human team. Returns the number accepted."""
    submitted = 0
    for team_id, team in list(game_manager.teams.items()):
        if not is_bot(team_id, human_team_id):
            continue
        predictions = team.model_predictions or {}
        if not predictions:
            continue

        for prop_id, prop in game_manager.current_properties.items():
            if valid_property_ids is not None and prop_id not in valid_property_ids:
                continue
            prediction = predictions.get(prop_id)
            if prediction is None:
                continue

            plan = bot_strategy(
                team_id, prediction, prop.asking_price, prop.max_ltv
            )
            if not plan["should_bid"]:
                continue

            already = any(
                b.team_id == team_id
                and b.property_id == prop_id
                and b.round_number == game_manager.current_round
                for b in game_manager.submitted_bids
            )
            if not affordable(
                plan["bid_price"], plan["ltv"], team.cash,
                prop.max_ltv, already_submitted=already,
            ):
                continue

            from src.game.adjudicator import Bid

            try:
                game_manager.submit_bid(
                    Bid(
                        team_id=team_id,
                        property_id=prop_id,
                        bid_price=plan["bid_price"],
                        ltv=plan["ltv"],
                        round_number=game_manager.current_round,
                        timestamp="bot",
                        confidence=plan["confidence"],
                    )
                )
                submitted += 1
            except (ValueError, RuntimeError):
                continue
    return submitted
