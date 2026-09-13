#!/usr/bin/env python3
"""
Economic dominance test.

The release-candidate question is whether **capital deployment automatically
beats analysis**. If a team can win by buying as much as possible at any price,
the course's central claim -- that a better model and better decisions produce an
advantage -- is false in the scoreboard.

This harness answers that with evidence rather than opinion, using two separate
experiments because they answer two different questions and a single design
cannot answer both honestly.

Experiment A -- pure economics ("does deploying capital earn anything?")
----------------------------------------------------------------------
Every strategy plays its own game with **no opponents**. The only thing that can
reject a bid is the seller's reserve. This isolates the return on capital: with
the same seed, the same property pool and the same market path, the difference in
ending NAV is attributable to the strategy alone. This is the experiment that
measures whether MORE ASSETS IS AUTOMATICALLY BETTER, because crowding-out cannot
contaminate it.

Experiment B -- competition ("who wins when they all compete?")
--------------------------------------------------------------
All strategies play in **one shared game**, head to head, so the property pool,
the seller reserves and the market path are identical across arms. This measures
auction win rates under direct competition. It is deliberately reported second,
because in a sealed-bid auction the highest bidder wins by construction -- the
competitive result says more about bid ordering than about returns.

Strategy arms
-------------
    ALL_PASS                 never bids
    BUY_EVERYTHING           bids 5% over the ask on every deal, at max LTV
    MAX_LTV                  bids the ask, always at the lender's maximum leverage
    RANDOM_VALID             random subset, random price, random leverage
    MODEL_DISCIPLINED        bids its own ceiling, never above the ask
    VALUE_SELECTIVE          only deals its model calls cheap, prices hard
    STRONG_DISCIPLINED       best model + disciplined pricing
    WEAK_AGGRESSIVE          worst model + chases every deal at max LTV
    WEAK_DISCIPLINED         worst model + disciplined pricing (diagnostic arm)

``WEAK_DISCIPLINED`` is not in the briefed list. It exists because the briefed A/B
(strong+disciplined versus weak+aggressive) changes two things at once, and a
one-arm-per-variable comparison is what actually tells us whether the MODEL or
the POLICY is doing the work:

    WEAK_DISCIPLINED -> STRONG_DISCIPLINED   isolates MODEL quality
    WEAK_DISCIPLINED -> WEAK_AGGRESSIVE      isolates DEPLOYMENT policy

How a model of a given quality is constructed
---------------------------------------------
Each arm is handed predictions with a controlled error, applied to the property's
true first-year value:

    predicted_fair_value = true_value * (1 + Normal(0, sigma_arm))

That is deliberate. The point of this study is to isolate the effect of forecast
accuracy on ending NAV, so accuracy must be a dial rather than an accident. The
realised outcomes themselves are never perturbed -- they come from the game's own
adjudicator, unchanged.

Run:

    uv run python scripts/balance_harness.py                 # 100 seeds, both experiments
    uv run python scripts/balance_harness.py --seeds 300
    uv run python scripts/balance_harness.py --experiment A
    uv run python scripts/balance_harness.py --json out.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402

from src.game.adjudicator import (  # noqa: E402
    ACQUISITION_COST_RATE,
    BASE_CAP_RATE,
    BASE_VACANCY,
    CAPITAL_RESERVE_RATE,
    Bid,
    ModelPrediction,
    equity_required_for,
    realized_year_outcome,
)
from src.game.analytics import assess_attempts, compute_team_analytics, fund_channels  # noqa: E402
from src.game.manager import GameConfig, GameManager  # noqa: E402

# Model error as a fraction of true value. Calibrated against the skill gradient:
# ORACLE ~1.4%, STRONG ~2.3%, BASIC ~3.1% of asset value, a weak model far worse.
SIGMA_STRONG = 0.025
SIGMA_MEDIUM = 0.055
SIGMA_WEAK = 0.140

# Policy constants, shared across arms that should differ only in model quality.
REQUIRED_MARGIN = 0.03
DISCIPLINED_LTV = 0.60
SELECTIVE_EDGE = 0.03


@dataclass
class Arm:
    """One strategy under test."""

    key: str
    label: str
    sigma: float
    policy: str
    family: str  # for grouping in the report

    def bids(self, prediction, prop, cash: float, rng: np.random.Generator) -> dict:
        """Return {'should_bid', 'price', 'ltv'} for one property.

        ``cash`` is the equity budget for *this* property, not the team's whole
        cash balance: callers hand out a per-property slice so a strategy cannot
        over-commit and be rejected for a reason unrelated to its policy.
        """
        ask = prop.asking_price
        fv = prediction.predicted_fair_value
        max_bid = prediction.max_bid
        edge = (fv - ask) / ask if ask > 0 else 0.0
        p = self.policy

        if p == "pass":
            return {"should_bid": False, "price": 0.0, "ltv": 0.0}

        if p == "buy_everything":
            # Chase every deal at any price the rules allow.
            price, ltv = ask * 1.05, prop.max_ltv

        elif p == "max_ltv":
            # Pay a fair price, but always at the maximum allowed leverage.
            price, ltv = ask, prop.max_ltv

        elif p == "random_valid":
            if rng.random() > 0.5:
                return {"should_bid": False, "price": 0.0, "ltv": 0.0}
            price = ask * float(rng.uniform(0.90, 1.02))
            ltv = float(rng.uniform(0.40, prop.max_ltv))

        elif p == "model_disciplined":
            price = min(max_bid, ask * 0.99)
            ltv = min(prediction.target_ltv, prop.max_ltv)

        elif p == "value_selective":
            if edge < SELECTIVE_EDGE:
                return {"should_bid": False, "price": 0.0, "ltv": 0.0}
            price = min(max_bid * 0.98, ask * 0.96)
            ltv = min(prediction.target_ltv, DISCIPLINED_LTV, prop.max_ltv)

        elif p == "disciplined":
            # Never bid on a deal the model does not think is worth owning, and
            # never pay above the ask for one it does.
            if edge < 0.0:
                return {"should_bid": False, "price": 0.0, "ltv": 0.0}
            price = min(max_bid, ask)
            ltv = min(prediction.target_ltv, prop.max_ltv)

        elif p == "weak_aggressive":
            price, ltv = ask * 1.04, prop.max_ltv

        elif p == "ref_ask":
            price, ltv = ask, 0.60

        elif p == "ref_value":
            if edge < 0.0:
                return {"should_bid": False, "price": 0.0, "ltv": 0.0}
            price, ltv = min(max_bid, ask * 0.97), 0.60

        else:  # pragma: no cover - defensive
            return {"should_bid": False, "price": 0.0, "ltv": 0.0}

        ltv = float(max(0.05, min(ltv, prop.max_ltv)))
        if price <= 0 or equity_required_for(price, ltv) > cash:
            # Scale down to what the budget allows rather than emit a bid the
            # engine will reject -- otherwise the arm is measured on a rejection,
            # not on its policy.
            if cash <= 0 or ltv >= 1.0:
                return {"should_bid": False, "price": 0.0, "ltv": 0.0}
            price = cash / (1.0 - ltv + ACQUISITION_COST_RATE)
        if price <= 0:
            return {"should_bid": False, "price": 0.0, "ltv": 0.0}
        return {"should_bid": True, "price": float(price), "ltv": float(ltv)}


ARMS: list[Arm] = [
    Arm("ALL_PASS", "All pass", SIGMA_STRONG, "pass", "baseline"),
    Arm("BUY_EVERYTHING", "Buy everything at max valid price",
        SIGMA_MEDIUM, "buy_everything", "aggressive"),
    Arm("MAX_LTV", "Maximum LTV", SIGMA_MEDIUM, "max_ltv", "aggressive"),
    Arm("RANDOM_VALID", "Random valid", SIGMA_MEDIUM, "random_valid", "baseline"),
    Arm("MODEL_DISCIPLINED", "Model disciplined",
        SIGMA_MEDIUM, "model_disciplined", "disciplined"),
    Arm("VALUE_SELECTIVE", "Value selective",
        SIGMA_STRONG, "value_selective", "disciplined"),
    Arm("STRONG_DISCIPLINED", "Strong model + disciplined bidding",
        SIGMA_STRONG, "disciplined", "disciplined"),
    Arm("WEAK_AGGRESSIVE", "Weak model + aggressive deployment",
        SIGMA_WEAK, "weak_aggressive", "aggressive"),
    Arm("WEAK_DISCIPLINED", "Weak model + disciplined bidding (diagnostic)",
        SIGMA_WEAK, "disciplined", "diagnostic"),
]

# Fixed opponents used only in Experiment B, so that every arm faces identical
# competition rather than a field that changes with the arm.
REFERENCE_FIELD: list[Arm] = [
    Arm("REF_ASK", "Reference: bids the ask at 60% LTV", SIGMA_MEDIUM, "ref_ask", "reference"),
    Arm("REF_VALUE", "Reference: model-disciplined at 60% LTV",
        SIGMA_STRONG, "ref_value", "reference"),
]

ARMS_BY_KEY = {a.key: a for a in ARMS}


# ── model construction ───────────────────────────────────────────────────

def build_predictions(
    property_ids: list[str],
    pool: dict,
    sigma: float,
    seed: int,
) -> dict[str, ModelPrediction]:
    """Predictions of a specified accuracy against the property's true value."""
    rng = np.random.default_rng(seed * 7919 + 13)
    out: dict[str, ModelPrediction] = {}
    for pid in property_ids:
        prop = pool[pid]
        truth = realized_year_outcome(
            property_id=pid,
            property_type=prop.property_type,
            noi=prop.current_noi,
            market_vacancy=BASE_VACANCY[prop.property_type],
            market_cap_rate=BASE_CAP_RATE[prop.property_type],
            seed=seed,
            round_number=0,
        )["value"]
        fv = truth * (1.0 + float(rng.normal(0, sigma)))
        growth = 0.02 + float(rng.normal(0, sigma / 2))
        out[pid] = ModelPrediction(
            property_id=pid,
            predicted_fair_value=fv,
            predicted_noi_growth=growth,
            probability_of_downside=float(np.clip(0.2 + rng.normal(0, 0.1), 0.02, 0.95)),
            max_bid=fv * (1.0 - REQUIRED_MARGIN),
            target_ltv=DISCIPLINED_LTV,
            model_name=f"arm_sigma_{sigma}",
            confidence=0.7,
        )
    return out


# ── one game ─────────────────────────────────────────────────────────────

@dataclass
class ArmResult:
    arm: str
    seed: int
    nav: float
    cumulative_return: float
    assets: int
    gross_ltv: float
    premium_to_ask: float          # mean (price - ask)/ask on acquisitions
    premium_to_value: float        # mean (price - realised value)/value
    valuation_mae: float
    decision_quality: float        # share of attempts judged good ex ante
    bid_discipline: float          # share of winning bids judged good ex ante
    selection_quality: float       # mean realised return on acquisitions
    # The three channels that sum exactly to NAV - starting equity.
    value_channel: float
    noi_income: float
    interest_paid: float
    cost_basis: float
    acquisition_costs: float
    reserves: float


def play_game(seed: int, arm: Arm, opponents: list[Arm]) -> ArmResult:
    """Play one full game and return ``arm``'s result.

    ``opponents`` may be empty (Experiment A: solo, reserve-only) or a list of
    competing strategies (Experiment B: shared game).
    """
    cfg = GameConfig(seed=seed, starting_equity=100.0, total_rounds=4,
                     properties_per_round=4, practice_round=True,
                     scenario="Base Case")
    gm = GameManager(cfg)

    participants = [arm] + [o for o in opponents if o.key != arm.key]
    for a in participants:
        gm.add_team(
            a.key, a.label,
            build_predictions(list(gm.all_properties.keys()), gm.all_properties,
                              a.sigma, seed),
        )

    gm.start_game()
    gm.lock_round()
    gm.resolve_round()          # practice, unscored
    gm.advance_round()

    rng = np.random.default_rng(seed * 104729 + 7)

    for _r in range(cfg.total_rounds):
        for a in participants:
            team = gm.teams[a.key]
            predictions = team.model_predictions
            remaining_equity = team.cash
            n_props = len(gm.current_properties)
            for i, (pid, prop) in enumerate(gm.current_properties.items()):
                pred = predictions.get(pid)
                if pred is None:
                    continue
                budget = remaining_equity / max(1, n_props - i)
                plan = a.bids(pred, prop, budget, rng)
                if not plan["should_bid"]:
                    continue
                equity = equity_required_for(plan["price"], plan["ltv"])
                if equity > team.cash:
                    continue
                try:
                    gm.submit_bid(Bid(a.key, pid, plan["price"], plan["ltv"],
                                      gm.current_round, f"harness_{a.key}"))
                    remaining_equity -= equity
                except (ValueError, RuntimeError):
                    continue
        gm.lock_round()
        gm.resolve_round()
        gm.advance_round()

    return _measure(gm, arm, seed)


def _measure(gm: GameManager, arm: Arm, seed: int) -> ArmResult:
    """Turn a finished game into this arm's measured result."""
    team = gm.teams[arm.key]
    channels = fund_channels(gm, arm.key)
    analytics = compute_team_analytics(gm, arm.key)
    attempts = assess_attempts(gm)

    prices, asks, values = [], [], []
    for pid, holding in team.properties.items():
        prices.append(holding.purchase_price)
        prop = gm.all_properties[pid]
        asks.append(prop.asking_price)
        values.append(holding.current_value)

    prem_ask = float(np.mean([(p - a) / a for p, a in zip(prices, asks)])) if prices else 0.0
    prem_val = float(np.mean([(p - v) / v for p, v in zip(prices, values)])) if prices else 0.0
    realized = float(np.mean([(v - p) / p for p, v in zip(prices, values)])) if prices else 0.0

    mine = [a for a in attempts if a.team_id == arm.key]
    won_attempts = [a for a in mine if a.won]
    decision_quality = (
        float(np.mean([1.0 if a.decision_label == "GOOD_DECISION" else 0.0 for a in mine]))
        if mine else 0.0
    )
    bid_discipline = (
        float(np.mean([1.0 if a.decision_label == "GOOD_DECISION" else 0.0 for a in won_attempts]))
        if won_attempts else 0.0
    )

    return ArmResult(
        arm=arm.key,
        seed=seed,
        nav=float(team.nav),
        cumulative_return=float(team.cumulative_return),
        assets=len(team.properties),
        gross_ltv=float(channels.gross_ltv or 0.0),
        premium_to_ask=prem_ask,
        premium_to_value=prem_val,
        valuation_mae=float(analytics.valuation_mae or 0.0),
        decision_quality=decision_quality,
        bid_discipline=bid_discipline,
        selection_quality=realized,
        value_channel=float(channels.value_channel),
        noi_income=float(channels.noi_income),
        interest_paid=float(channels.interest_paid),
        cost_basis=float(team.cumulative_purchase_price),
        acquisition_costs=float(team.cumulative_acquisition_costs),
        reserves=float(team.cumulative_reserves),
    )


# ── reporting ────────────────────────────────────────────────────────────

def _fmt_row(label: str, sub: list[ArmResult]) -> str:
    def m(fn) -> float:
        return statistics.mean(fn(r) for r in sub)

    return (
        f"{label[:33]:<34}"
        f"{m(lambda r: r.nav):>9.2f}"
        f"{statistics.median([r.nav for r in sub]):>9.2f}"
        f"{sum(1 for r in sub if r.cumulative_return > 0) / len(sub):>9.0%}"
        f"{m(lambda r: r.assets):>8.2f}"
        f"{m(lambda r: r.gross_ltv):>7.0%}"
        f"{m(lambda r: r.premium_to_ask):>+9.2%}"
        f"{m(lambda r: r.premium_to_value):>+9.2%}"
        f"{m(lambda r: r.valuation_mae):>8.2f}"
        f"{m(lambda r: r.decision_quality):>6.0%}"
        f"{m(lambda r: r.selection_quality):>+7.1%}"
    )


HEADER = (
    f"{'STRATEGY':<34}{'meanNAV':>9}{'medNAV':>9}{'winRate':>9}{'assets':>8}"
    f"{'LTV':>7}{'prem/ask':>9}{'prem/val':>9}{'valMAE':>8}{'decQ':>6}{'selQ':>7}"
)


def _banner(text: str) -> None:
    print("\n" + "=" * 118)
    print(text)
    print("=" * 118)


def report_outcomes(rows: list[ArmResult], title: str) -> None:
    _banner(title)
    print(HEADER)
    print("-" * 118)
    for arm in ARMS:
        sub = [r for r in rows if r.arm == arm.key]
        if sub:
            print(_fmt_row(arm.label, sub))


def report_channels(rows: list[ArmResult]) -> None:
    """Where the NAV change came from, per strategy.

    This is the diagnostic that says *why* deployment does or does not dominate:
    appreciation relative to the price paid, the income the assets throw off, or
    the cost of the debt used to buy them. The three channels sum exactly to
    ``NAV - starting equity``.
    """
    _banner("NAV DECOMPOSITION  (per arm, mean over seeds, $M)")
    print(f"{'STRATEGY':<30}{'NAV-100':>9}{'assets':>7}{'cost':>9}{'value ch':>10}"
          f"{'NOI inc':>9}{'interest':>9}{'acq cost':>9}{'reserve':>9}"
          f"{'ROC':>8}{'vs debt':>10}")
    print("-" * 118)
    for arm in ARMS:
        sub = [r for r in rows if r.arm == arm.key]
        if not sub:
            continue
        m = lambda fn: statistics.mean(fn(r) for r in sub)  # noqa: E731
        vc, inc = m(lambda r: r.value_channel), m(lambda r: r.noi_income)
        interest, acq = m(lambda r: r.interest_paid), m(lambda r: r.acquisition_costs)
        reserve, cost = m(lambda r: r.reserves), m(lambda r: r.cost_basis)
        gross = m(lambda r: r.gross_ltv)
        roc = (vc + inc - reserve) / cost if cost > 0 else 0.0
        # The honest leverage test: unlevered return on cost vs the debt rate.
        debt_rate = 0.0640  # pool mean, see docs/GAME_ECONOMICS.md
        verdict = "n/a" if gross <= 0 else ("accretive" if roc > debt_rate else "dilutive")
        print(
            f"{arm.label[:29]:<30}{m(lambda r: r.nav) - 100.0:>9.2f}"
            f"{m(lambda r: r.assets):>7.2f}{cost:>9.2f}{vc:>10.2f}{inc:>9.2f}"
            f"{interest:>9.2f}{acq:>9.2f}{reserve:>9.2f}"
            f"{roc:>7.1%}{verdict:>10}"
        )


def report_correlations(rows: list[ArmResult], title: str) -> None:
    """How much of ending NAV each behaviour explains, across every arm-seed run."""
    _banner(title)
    nav = np.array([r.nav for r in rows], dtype=float)

    def corr(series: np.ndarray) -> float:
        if series.std() == 0 or nav.std() == 0:
            return float("nan")
        return float(np.corrcoef(series, nav)[0, 1])

    checks = [
        ("assets acquired", lambda r: r.assets),
        ("gross LTV", lambda r: r.gross_ltv),
        ("valuation MAE (worse = higher)", lambda r: r.valuation_mae),
        ("decision quality (ex ante)", lambda r: r.decision_quality),
        ("bid discipline on wins", lambda r: r.bid_discipline),
        ("selection quality (realised)", lambda r: r.selection_quality),
        ("premium paid to ask", lambda r: r.premium_to_ask),
        ("cost basis deployed", lambda r: r.cost_basis),
    ]
    for label, fn in checks:
        series = np.array([fn(r) for r in rows], float)
        print(f"  corr(NAV, {label:<32}) = {corr(series):+.3f}")

    print("\n  Note: a pooled correlation across arms mixes strategy effects with")
    print("  within-strategy dispersion. The paired decomposition below separates them.")

    # Between-arm vs within-arm variance: is NAV driven by what the strategy did,
    # or by which seed it drew?
    groups = {a.key: np.array([r.nav for r in rows if r.arm == a.key], float) for a in ARMS}
    groups = {k: v for k, v in groups.items() if len(v) > 1}
    within = np.mean([v.var() for v in groups.values()])
    between = float(np.var([v.mean() for v in groups.values()]))
    print(f"\n  variance of NAV  between strategies = {between:7.3f}")
    print(f"  variance of NAV  within  strategies = {within:7.3f}")
    print(f"  share of NAV variance explained by strategy choice = "
          f"{between / (between + within) if (between + within) > 0 else float('nan'):.1%}")


def report_head_to_head(rows: list[ArmResult]) -> None:
    """Paired win rate of one arm against another, across identical games."""
    _banner("HEAD-TO-HEAD (paired: same game, same seed)")
    from scipy.stats import spearmanr

    def navs(arm: str) -> list[float]:
        return [r.nav for r in rows if r.arm == arm]

    comparisons = [
        ("STRONG_DISCIPLINED", "WEAK_AGGRESSIVE"),
        ("STRONG_DISCIPLINED", "WEAK_DISCIPLINED"),
        ("STRONG_DISCIPLINED", "BUY_EVERYTHING"),
        ("STRONG_DISCIPLINED", "MAX_LTV"),
        ("STRONG_DISCIPLINED", "ALL_PASS"),
        ("WEAK_DISCIPLINED", "WEAK_AGGRESSIVE"),
        ("VALUE_SELECTIVE", "BUY_EVERYTHING"),
        ("MODEL_DISCIPLINED", "MAX_LTV"),
    ]
    for a, b in comparisons:
        ps = list(zip(navs(a), navs(b)))
        if not ps:
            continue
        a_wins = sum(1 for x, y in ps if x > y + 1e-9)
        ties = sum(1 for x, y in ps if abs(x - y) <= 1e-9)
        print(f"  {a:<22} beats {b:<20} in {a_wins:>3}/{len(ps)} games "
              f"({ties} tied), mean NAV edge {statistics.mean(x - y for x, y in ps):+.2f}M")

    # Top-of-field win rate: how often each arm finishes highest NAV in the game.
    by_seed: dict[int, list[ArmResult]] = {}
    for r in rows:
        by_seed.setdefault(r.seed, []).append(r)
    if by_seed and len(next(iter(by_seed.values()))) > 1:
        print("\n  SEED WIN RATE (highest NAV of the whole field):")
        counts = {a.key: 0 for a in ARMS}
        for seed_rows in by_seed.values():
            best = max(seed_rows, key=lambda r: r.nav)
            counts[best.arm] += 1
        for arm in ARMS:
            if counts[arm.key] or any(r.arm == arm.key for r in rows):
                print(f"    {arm.label[:40]:<42} {counts[arm.key]:>4}/{len(by_seed)}"
                      f"  ({counts[arm.key] / len(by_seed):>5.0%})")

    # Paired rank correlation: which behaviour tracks NAV within the same game.
    if by_seed:
        nav_all, assets, ltv, mae, decq, selq = [], [], [], [], [], []
        for seed_rows in by_seed.values():
            for r in seed_rows:
                nav_all.append(r.nav)
                assets.append(r.assets)
                ltv.append(r.gross_ltv)
                mae.append(r.valuation_mae)
                decq.append(r.decision_quality)
                selq.append(r.selection_quality)
        print("\n  Within-seed (paired) rank correlation — removes seed luck:")
        for label, series in [("assets", assets), ("ltv", ltv), ("valMAE", mae),
                              ("decQ", decq), ("selQ", selq)]:
            rho = spearmanr(series, nav_all).statistic
            print(f"    rho(NAV, {label:<8}) = {rho:+.3f}")


def report_verdict(rows: list[ArmResult]) -> dict:
    _banner("VERDICT")

    def mean_nav(arm: str) -> float:
        sub = [r for r in rows if r.arm == arm]
        return statistics.mean(r.nav for r in sub) if sub else float("nan")

    def win_rate(arm: str) -> float:
        sub = [r for r in rows if r.arm == arm]
        return sum(1 for r in sub if r.cumulative_return > 0) / len(sub) if sub else float("nan")

    assets = np.array([r.assets for r in rows], float)
    nav = np.array([r.nav for r in rows], float)
    corr_assets = float(np.corrcoef(assets, nav)[0, 1]) if assets.std() else float("nan")

    for key in ["ALL_PASS", "BUY_EVERYTHING", "MAX_LTV", "BUY_EVERYTHING",
                "WEAK_AGGRESSIVE", "WEAK_DISCIPLINED", "STRONG_DISCIPLINED",
                "VALUE_SELECTIVE", "MODEL_DISCIPLINED"]:
        if any(r.arm == key for r in rows):
            print(f"  {key:<22} mean NAV ${mean_nav(key):7.2f}M   "
                  f"profitable {win_rate(key):>5.0%}")

    print(f"\n  corr(NAV, assets acquired) = {corr_assets:+.3f}")
    print(f"  strong+disciplined minus weak+aggressive    = "
          f"${mean_nav('STRONG_DISCIPLINED') - mean_nav('WEAK_AGGRESSIVE'):+.2f}M")
    print(f"  strong+disciplined minus weak+disciplined   = "
          f"${mean_nav('STRONG_DISCIPLINED') - mean_nav('WEAK_DISCIPLINED'):+.2f}M  "
          f"(pure MODEL-quality effect)")
    print(f"  weak+aggressive minus weak+disciplined      = "
          f"${mean_nav('WEAK_AGGRESSIVE') - mean_nav('WEAK_DISCIPLINED'):+.2f}M  "
          f"(pure DEPLOYMENT effect)")

    deployment_dominates = corr_assets > 0.70 and mean_nav("BUY_EVERYTHING") >= mean_nav(
        "STRONG_DISCIPLINED")
    mixed = corr_assets > 0.50
    verdict = "YES" if deployment_dominates else ("PARTLY" if mixed else "NO")
    print(f"\n  MORE ASSETS = AUTOMATICALLY BETTER ? {verdict}")
    print(f"  CAPITAL DEPLOYMENT DOMINATES       : {verdict}")

    return {
        "corr_nav_assets": corr_assets,
        "mean_nav": {a.key: mean_nav(a.key) for a in ARMS},
        "profitable_rate": {a.key: win_rate(a.key) for a in ARMS},
        "deployment_dominates": deployment_dominates,
    }


def run_experiment_a(seeds: list[int], quiet: bool = False) -> tuple[list[ArmResult], dict]:
    """Solo games: pure economics, no crowding."""
    rows: list[ArmResult] = []
    for seed in seeds:
        for arm in ARMS:
            rows.append(play_game(seed, arm, opponents=[]))
    if not quiet:
        report_outcomes(rows, "EXPERIMENT A — PURE ECONOMICS (each strategy alone, "
                              "reserve is the only gate)")
        report_channels(rows)
        report_correlations(rows, "EXPERIMENT A — CORRELATION WITH ENDING NAV")
    summary = report_verdict(rows) if not quiet else {}
    return rows, summary


def run_experiment_b(seeds: list[int], quiet: bool = False) -> tuple[list[ArmResult], dict]:
    """One shared game per seed: direct competition."""
    rows: list[ArmResult] = []
    for seed in seeds:
        for arm in ARMS:
            opponents = [a for a in ARMS if a.key != arm.key] + REFERENCE_FIELD
            rows.append(play_game(seed, arm, opponents=opponents))
    if not quiet:
        report_outcomes(rows, "EXPERIMENT B — COMPETITION (all strategies in one game, "
                              "same pool and reserves)")
        report_head_to_head(rows)
    return rows, {}


# ── Experiment C: the actual classroom game ──────────────────────────────
#
# Experiments A and B use synthetic arms. Experiment C uses the game students
# will actually play: the three demo bot funds (Value / Growth / Risk) plus one
# human seat whose model quality and bidding policy is the variable under test.
# This is the design that answers the release question in the form it will be
# asked -- "if a student deploys capital aggressively, do they win?"

CLASSROOM_POLICIES: list[Arm] = [
    Arm("H_PASS", "Human: never bids", SIGMA_MEDIUM, "pass", "classroom"),
    Arm("H_FOLLOW_WEAK", "Human: weak model, follows ceiling",
        SIGMA_WEAK, "disciplined", "classroom"),
    Arm("H_FOLLOW", "Human: medium model, follows ceiling",
        SIGMA_MEDIUM, "disciplined", "classroom"),
    Arm("H_FOLLOW_STRONG", "Human: strong model, follows ceiling",
        SIGMA_STRONG, "disciplined", "classroom"),
    Arm("H_SELECTIVE", "Human: strong model, only cheap deals",
        SIGMA_STRONG, "value_selective", "classroom"),
    Arm("H_ASK_MAXLTV", "Human: meets the ask at max LTV",
        SIGMA_MEDIUM, "max_ltv", "classroom"),
    Arm("H_AGGRESSIVE", "Human: 5% over ask at max LTV (medium model)",
        SIGMA_MEDIUM, "buy_everything", "classroom"),
    Arm("H_AGGRESSIVE_WEAK", "Human: 5% over ask at max LTV (weak model)",
        SIGMA_WEAK, "buy_everything", "classroom"),
]


@dataclass
class ClassroomResult:
    policy: str
    seed: int
    nav: float
    rank: int
    field_size: int
    assets: int
    gross_ltv: float
    premium_to_ask: float
    valuation_mae: float
    bot_navs: dict

    @property
    def won(self) -> bool:
        return self.rank == 1


def play_classroom_game(seed: int, human: Arm) -> ClassroomResult:
    """Run the real demo game with a human whose model quality/policy is set."""
    from src.game.bots import submit_bot_bids
    from src.game.demo_setup import HUMAN_TEAM_ID, build_demo_game

    gm = build_demo_game(seed=seed)
    # Replace the shipped human model with one built against THIS pool, so the
    # experiment is aligned by construction and can vary the model's quality.
    if human.policy != "pass":
        gm.teams[HUMAN_TEAM_ID].model_predictions = build_predictions(
            list(gm.all_properties.keys()), gm.all_properties, human.sigma, seed
        )
    else:
        gm.teams[HUMAN_TEAM_ID].model_predictions = {}

    gm.start_game()
    gm.lock_round()
    gm.resolve_round()          # practice
    gm.advance_round()

    rng = np.random.default_rng(seed * 31337 + 11)

    for _r in range(gm.config.total_rounds):
        team = gm.teams[HUMAN_TEAM_ID]
        predictions = team.model_predictions
        remaining = team.cash
        n_props = len(gm.current_properties)
        for i, (pid, prop) in enumerate(gm.current_properties.items()):
            pred = predictions.get(pid)
            if pred is None:
                continue
            budget = remaining / max(1, n_props - i)
            plan = human.bids(pred, prop, budget, rng)
            if not plan["should_bid"]:
                continue
            equity = equity_required_for(plan["price"], plan["ltv"])
            if equity > team.cash:
                continue
            try:
                gm.submit_bid(Bid(HUMAN_TEAM_ID, pid, plan["price"], plan["ltv"],
                                  gm.current_round, "classroom"))
                remaining -= equity
            except (ValueError, RuntimeError):
                continue

        submit_bot_bids(gm, HUMAN_TEAM_ID)
        gm.lock_round()
        gm.resolve_round()
        gm.advance_round()

    navs = {tid: t.nav for tid, t in gm.teams.items()}
    ranked = sorted(navs.values(), reverse=True)
    human_nav = navs[HUMAN_TEAM_ID]
    rank = ranked.index(human_nav) + 1

    channels = fund_channels(gm, HUMAN_TEAM_ID)
    analytics = compute_team_analytics(gm, HUMAN_TEAM_ID)
    team = gm.teams[HUMAN_TEAM_ID]
    prices = [h.purchase_price for h in team.properties.values()]
    asks = [gm.all_properties[pid].asking_price for pid in team.properties]
    prem = float(np.mean([(p - a) / a for p, a in zip(prices, asks)])) if prices else 0.0

    return ClassroomResult(
        policy=human.key,
        seed=seed,
        nav=human_nav,
        rank=rank,
        # Ties count as joint; ranked.index() gives the best rank, which is right.
        field_size=len(navs),
        assets=len(team.properties),
        gross_ltv=float(channels.gross_ltv or 0.0),
        premium_to_ask=prem,
        valuation_mae=float(analytics.valuation_mae or 0.0),
        bot_navs={k: v for k, v in navs.items() if k != HUMAN_TEAM_ID},
    )


def run_experiment_c(seeds: list[int], quiet: bool = False) -> tuple[list[ClassroomResult], dict]:
    rows: list[ClassroomResult] = []
    for seed in seeds:
        for policy in CLASSROOM_POLICIES:
            rows.append(play_classroom_game(seed, policy))

    if quiet:
        return rows, {}

    _banner("EXPERIMENT C — THE CLASSROOM GAME (3 demo bot funds + 1 human seat)")
    print(f"{'HUMAN STRATEGY':<44}{'meanNAV':>9}{'winRate':>9}{'top2':>7}"
          f"{'assets':>8}{'LTV':>7}{'prem/ask':>9}{'valMAE':>8}")
    print("-" * 118)
    summary = {}
    for policy in CLASSROOM_POLICIES:
        sub = [r for r in rows if r.policy == policy.key]
        if not sub:
            continue
        wins = sum(1 for r in sub if r.won)
        top2 = sum(1 for r in sub if r.rank <= 2)
        mean_nav = statistics.mean(r.nav for r in sub)
        print(
            f"{policy.label[:43]:<44}{mean_nav:>9.2f}{wins / len(sub):>9.0%}"
            f"{top2 / len(sub):>7.0%}"
            f"{statistics.mean(r.assets for r in sub):>8.2f}"
            f"{statistics.mean(r.gross_ltv for r in sub):>7.0%}"
            f"{statistics.mean(r.premium_to_ask for r in sub):>+9.2%}"
            f"{statistics.mean(r.valuation_mae for r in sub):>8.2f}"
        )
        summary[policy.key] = {
            "mean_nav": mean_nav,
            "win_rate": wins / len(sub),
            "top2_rate": top2 / len(sub),
            "assets": statistics.mean(r.assets for r in sub),
            "premium_to_ask": statistics.mean(r.premium_to_ask for r in sub),
            "valuation_mae": statistics.mean(r.valuation_mae for r in sub),
        }

    # The bot field is fixed, so any NAV difference is the human's own doing.
    _banner("EXPERIMENT C — DOES DEPLOYMENT OR ANALYSIS DECIDE THE HUMAN'S RESULT?")
    nav = np.array([r.nav for r in rows], float)

    def corr(fn) -> float:
        series = np.array([fn(r) for r in rows], float)
        if series.std() == 0 or nav.std() == 0:
            return float("nan")
        return float(np.corrcoef(series, nav)[0, 1])

    print(f"  corr(NAV, assets acquired)     = {corr(lambda r: r.assets):+.3f}")
    print(f"  corr(NAV, gross LTV)           = {corr(lambda r: r.gross_ltv):+.3f}")
    print(f"  corr(NAV, valuation MAE)       = {corr(lambda r: r.valuation_mae):+.3f}")
    print(f"  corr(NAV, premium paid to ask) = {corr(lambda r: r.premium_to_ask):+.3f}")

    def mean_nav(key: str) -> float:
        sub = [r for r in rows if r.policy == key]
        return statistics.mean(r.nav for r in sub) if sub else float("nan")

    def win_rate(key: str) -> float:
        sub = [r for r in rows if r.policy == key]
        return sum(1 for r in sub if r.won) / len(sub) if sub else float("nan")

    print(f"\n  disciplined (medium model)   NAV ${mean_nav('H_FOLLOW'):7.2f}M  "
          f"win {win_rate('H_FOLLOW'):>5.0%}")
    print(f"  disciplined (strong model)   NAV ${mean_nav('H_FOLLOW_STRONG'):7.2f}M  "
          f"win {win_rate('H_FOLLOW_STRONG'):>5.0%}")
    print(f"  aggressive deployment        NAV ${mean_nav('H_AGGRESSIVE'):7.2f}M  "
          f"win {win_rate('H_AGGRESSIVE'):>5.0%}")
    print(f"  aggressive + weak model      NAV ${mean_nav('H_AGGRESSIVE_WEAK'):7.2f}M  "
          f"win {win_rate('H_AGGRESSIVE_WEAK'):>5.0%}")
    print(f"  never bid                    NAV ${mean_nav('H_PASS'):7.2f}M  "
          f"win {win_rate('H_PASS'):>5.0%}")

    deployment = mean_nav("H_AGGRESSIVE") - mean_nav("H_FOLLOW")
    analysis = mean_nav("H_FOLLOW_STRONG") - mean_nav("H_FOLLOW_WEAK")
    print(f"\n  deployment effect (aggressive minus disciplined) = ${deployment:+.2f}M")
    print(f"  analysis   effect (strong minus weak model)      = ${analysis:+.2f}M")
    print(f"\n  CAPITAL DEPLOYMENT DOMINATES THE CLASSROOM GAME ? "
          f"{'YES' if deployment > abs(analysis) and deployment > 0 else 'NO'}")
    summary["_deployment_effect"] = deployment
    summary["_analysis_effect"] = analysis
    return rows, summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=100)
    ap.add_argument("--start", type=int, default=20240331)
    ap.add_argument("--experiment", choices=["A", "B", "C", "both", "all"], default="all")
    ap.add_argument("--json", type=str, default=None)
    args = ap.parse_args()
    args.experiment = args.experiment.upper()

    seeds = [args.start + i for i in range(args.seeds)]

    _banner("ECONOMIC DOMINANCE TEST")
    print(f"seeds          : {args.seeds} (from {args.start})")
    print(f"strategy arms  : {len(ARMS)}")
    print(f"design         : A = solo (pure economics); B = shared game (competition);")
    print(f"                 C = the real classroom game (3 bots + 1 human)")
    print(f"model error    : strong sigma={SIGMA_STRONG:.1%}  medium={SIGMA_MEDIUM:.1%}  "
          f"weak={SIGMA_WEAK:.1%} of true value")
    print("verdict rule   : deployment DOMINATES only if corr(NAV, assets) > 0.70 AND")
    print("                 'buy everything' reaches the top disciplined arm's NAV")

    payload: dict = {"seeds": args.seeds, "start": args.start}

    if args.experiment in ("A", "ALL", "BOTH"):
        rows_a, summary_a = run_experiment_a(seeds)
        payload["experiment_a"] = summary_a
        payload["rows_a"] = [r.__dict__ for r in rows_a]

    if args.experiment in ("B", "ALL", "BOTH"):
        rows_b, _ = run_experiment_b(seeds)
        payload["rows_b"] = [r.__dict__ for r in rows_b]

    if args.experiment in ("C", "ALL", "BOTH"):
        rows_c, summary_c = run_experiment_c(seeds)
        payload["experiment_c"] = summary_c
        payload["rows_c"] = [r.__dict__ for r in rows_c]

    if args.json:
        Path(args.json).write_text(json.dumps(payload, indent=2))
        print(f"\n  raw results written to {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
