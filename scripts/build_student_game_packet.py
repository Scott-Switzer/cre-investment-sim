#!/usr/bin/env python3
"""
Build the pre-class student game packet.

Students receive this packet BEFORE class, build a model externally
(Excel / Python / R / anything), and bring their predictions into the live game.

Outputs (written to ``student_packet/``):

    historical_training.csv             observations with KNOWN outcomes
    game_candidates.csv                 the properties the game will actually offer,
                                        with NO future outcomes exposed
    data_dictionary.csv                 column-by-column documentation
    prediction_submission_template.csv  the contract students fill in
    GAME_RULES.md                       rules the students are playing under

Why this file matters
---------------------
The whole instructional claim is *analytical model -> property forecast ->
investment policy -> decision -> realized result -> feedback*. That claim only
holds if the dataset a student models is the dataset the game plays with.

So this script does NOT invent its own properties. It calls the same
:func:`src.data.properties.generate_properties` the game engine calls, and it
computes training targets with the same :func:`src.game.adjudicator.realized_year_outcome`
function the adjudicator uses to revalue assets. A model trained on this packet
is therefore learning the process the game actually runs.

Determinism: fully seeded. Re-running produces byte-identical output.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.macro import MACRO_SERIES
from src.data.properties import generate_properties, synthetic_year_built
from src.game.adjudicator import (
    BASE_CAP_RATE,
    BASE_POLICY_RATE,
    BASE_VACANCY,
    PROPERTY_TYPES,
    realized_year_outcome,
)

# ── CONFIGURATION ─────────────────────────────────────────────────────────

GAME_SEED = 20240331
GAME_CANDIDATE_COUNT = 120
DEFAULT_OUTPUT_DIR = Path("student_packet")

# Historical vintages. Each vintage is a separate call to the same generator,
# standing in for "transactions that already closed in prior years".
HISTORICAL_VINTAGES: list[tuple[int, int]] = [
    (2019, 400),
    (2020, 400),
    (2021, 400),
    (2022, 400),
    (2023, 400),
    (2024, 400),
]

# Shared feature columns present in BOTH the training set and the candidates.
FEATURE_COLUMNS: list[str] = [
    "property_id",
    "property_type",
    "submarket",
    "building_sf",
    "year_built",
    "occupancy",
    "noi",
    "market_rent",
    "in_place_rent",
    "going_in_cap",
    "opex_ratio",
    "walt",
    "tenant_concentration",
    "capex_need",
    "property_quality",
    "units",
    "primary_risk",
    "employment_density",
    "treasury_rate",
    "market_vacancy",
]

# Outcome columns: present ONLY in the historical training set.
TARGET_COLUMNS: list[str] = [
    "transaction_cap_rate",
    "transaction_price",
    "noi_growth_realized",
    "next_year_noi",
    "next_year_cap_rate",
    "next_year_value",
]

# Columns exposed ONLY for game candidates (current market terms).
CANDIDATE_COLUMNS: list[str] = [
    "property_name",
    "asking_price",
    "debt_rate",
    "max_ltv",
    "amortization_years",
    "data_tag",
]


def _treasury_schedule() -> list[tuple[str, float]]:
    """Real 10-year Treasury observations from the cached FRED sample.

    Used to give each historical vintage a genuine public rate environment
    instead of a made-up number.
    """
    df = MACRO_SERIES[MACRO_SERIES["series"] == "DGS10"].copy()
    if df.empty:
        # Fall back to the game's opening policy rate if the cache is absent.
        return [("2024-03-31", float(BASE_POLICY_RATE))]
    df["observation_date"] = pd.to_datetime(df["observation_date"])
    df = df.sort_values("observation_date")
    return [
        (d.strftime("%Y-%m-%d"), float(v))
        for d, v in zip(df["observation_date"], df["value"])
    ]


def _employment_density(submarket: str) -> float:
    try:
        from src.geo.features import employment_density_proxy

        return float(employment_density_proxy(submarket))
    except Exception:
        return float("nan")


def _base_frame(properties: pd.DataFrame) -> pd.DataFrame:
    """Map the generator's columns onto the shared packet schema."""
    out = pd.DataFrame(
        {
            "property_id": properties["property_id"].astype(str),
            "property_name": properties["property_name"],
            "property_type": properties["type"],
            "submarket": properties["submarket"],
            "building_sf": properties["size_sf"],
            "year_built": [
                synthetic_year_built(pid, q)
                for pid, q in zip(properties["property_id"], properties["property_quality"])
            ],
            "occupancy": properties["occupancy"],
            "noi": properties["current_noi"],
            "market_rent": properties["market_rent"],
            "in_place_rent": properties["in_place_rent"],
            "going_in_cap": properties["going_in_cap"],
            "opex_ratio": properties["opex_ratio"],
            "walt": properties["walt"],
            "tenant_concentration": properties["tenant_concentration"],
            "capex_need": properties["capex_need"],
            "property_quality": properties["property_quality"],
            "units": properties["units"],
            "primary_risk": properties["primary_risk"],
            "employment_density": [
                _employment_density(sm) for sm in properties["submarket"]
            ],
        }
    )
    return out


def build_game_candidates(count: int = GAME_CANDIDATE_COUNT) -> pd.DataFrame:
    """The exact properties the live game will offer, without future outcomes."""
    properties = generate_properties(seed=GAME_SEED, count=count)
    frame = _base_frame(properties)

    # Market state the game opens with (round 0). These are market-level, not
    # property-level, and are documented as such in the data dictionary.
    frame["treasury_rate"] = float(BASE_POLICY_RATE)
    frame["market_vacancy"] = [float(BASE_VACANCY[t]) for t in frame["property_type"]]

    frame["asking_price"] = properties["asking_price"].to_numpy()
    frame["debt_rate"] = properties["debt_rate"].to_numpy()
    frame["max_ltv"] = properties["max_ltv"].to_numpy()
    frame["amortization_years"] = properties["amortization_years"].to_numpy()
    frame["data_tag"] = "REAL PUBLIC CONTEXT / SYNTHETIC OPERATING CASE"

    ordered = FEATURE_COLUMNS + CANDIDATE_COLUMNS
    return frame[ordered].sort_values("property_id").reset_index(drop=True)


def build_historical_training(vintages: list[tuple[int, int]] | None = None) -> pd.DataFrame:
    """Historical transactions with outcomes computed by the game's own rules.

    For each vintage we generate a fresh cross-section with the game's generator,
    then apply :func:`realized_year_outcome` -- the identical function the
    adjudicator uses -- to produce the realized next-year NOI, cap rate and value.
    """
    vintages = vintages or HISTORICAL_VINTAGES
    treasury = _treasury_schedule()
    rows: list[pd.DataFrame] = []

    for i, (year, count) in enumerate(vintages):
        props = generate_properties(seed=GAME_SEED + 1000 + i, count=count)
        frame = _base_frame(props)

        date_label, rate = treasury[i % len(treasury)]
        frame["date"] = f"{year}-06-30"
        frame["treasury_rate"] = float(rate)

        # Market vacancy for the vintage: the game's per-type baseline plus a
        # seeded deviation so the training set actually contains variation.
        vint_rng = np.random.default_rng(GAME_SEED + 5000 + i)
        frame["market_vacancy"] = [
            float(np.clip(BASE_VACANCY[t] + vint_rng.normal(0, 0.012), 0.01, 0.30))
            for t in frame["property_type"]
        ]

        outcomes = [
            realized_year_outcome(
                property_id=pid,
                property_type=ptype,
                noi=noi,
                market_vacancy=vac,
                market_cap_rate=BASE_CAP_RATE[ptype],
                seed=GAME_SEED,
                round_number=i,
            )
            for pid, ptype, noi, vac in zip(
                frame["property_id"],
                frame["property_type"],
                frame["noi"],
                frame["market_vacancy"],
            )
        ]

        frame["transaction_cap_rate"] = frame["going_in_cap"].round(4)
        frame["transaction_price"] = (frame["noi"] / frame["going_in_cap"]).round(4)
        frame["noi_growth_realized"] = [round(o["noi_growth"], 5) for o in outcomes]
        frame["next_year_noi"] = [round(o["next_noi"], 4) for o in outcomes]
        frame["next_year_cap_rate"] = [round(o["cap_rate"], 5) for o in outcomes]
        frame["next_year_value"] = [round(o["value"], 4) for o in outcomes]

        rows.append(frame)

    combined = pd.concat(rows, ignore_index=True)
    ordered = ["date"] + FEATURE_COLUMNS + TARGET_COLUMNS
    return combined[ordered].sort_values(["date", "property_id"]).reset_index(drop=True)


def build_data_dictionary() -> pd.DataFrame:
    """Document every column the student will see."""
    entries = [
        ("property_id", "Unique property identifier", "string", "Historical and candidates", "Matches the ids the live game offers"),
        ("date", "Vintage / transaction date", "date", "Historical only", "Historical rows represent transactions that already closed"),
        ("property_type", "Asset class", "category", "Historical and candidates", "Industrial | Office | Multifamily | Retail"),
        ("submarket", "Orange County submarket", "category", "Historical and candidates", "Anaheim | Irvine | Newport Beach | Orange | Santa Ana | Costa Mesa | Fullerton"),
        ("building_sf", "Rentable building area", "numeric", "Historical and candidates", "Square feet"),
        ("year_built", "Synthetic construction year", "integer", "Historical and candidates", "SYNTHETIC DERIVED - not produced by the generator; derived from property id and quality"),
        ("occupancy", "Current occupancy rate", "numeric", "Historical and candidates", "Decimal 0-1"),
        ("noi", "Current annual net operating income", "numeric", "Historical and candidates", "Millions of dollars"),
        ("market_rent", "Market rent", "numeric", "Historical and candidates", "$/SF/month, or $/unit/month for Multifamily"),
        ("in_place_rent", "Contract in-place rent", "numeric", "Historical and candidates", "Same units as market_rent"),
        ("going_in_cap", "Cap rate implied by the current asking price", "numeric", "Historical and candidates", "Decimal - equals noi / asking_price"),
        ("opex_ratio", "Operating expense ratio", "numeric", "Historical and candidates", "Decimal share of gross revenue"),
        ("walt", "Weighted average lease term", "numeric", "Historical and candidates", "Years"),
        ("tenant_concentration", "Largest-tenant revenue share", "numeric", "Historical and candidates", "Decimal 0-1"),
        ("capex_need", "Estimated near-term capital need", "numeric", "Historical and candidates", "Millions of dollars"),
        ("property_quality", "Generated quality score", "numeric", "Historical and candidates", "Decimal 0-1; higher is better"),
        ("units", "Number of units", "numeric", "Historical and candidates", "Populated for Multifamily only"),
        ("primary_risk", "Generator's labelled principal risk", "category", "Historical and candidates", "Market / Lease-up Risk, etc."),
        ("employment_density", "Submarket employment density", "numeric", "Historical and candidates", "DERIVED FEATURE - jobs per square mile, submarket level"),
        ("treasury_rate", "10-year Treasury rate at the observation date", "numeric", "Historical and candidates", "REAL PUBLIC DATA (FRED DGS10). For candidates this is the game's opening market rate"),
        ("market_vacancy", "Market vacancy for the property type", "numeric", "Historical and candidates", "SIMULATED MARKET STATE - per-type baseline plus seeded deviation"),
        ("transaction_cap_rate", "Cap rate the property traded at", "numeric", "Historical only - TARGET", "Decimal"),
        ("transaction_price", "Price the property transacted at", "numeric", "Historical only - TARGET", "Millions of dollars"),
        ("noi_growth_realized", "Realized following-year NOI growth", "numeric", "Historical only - TARGET", "Decimal; the quantity the game rewards you for forecasting"),
        ("next_year_noi", "NOI one year after the transaction", "numeric", "Historical only - TARGET", "Millions of dollars"),
        ("next_year_cap_rate", "Cap rate one year after the transaction", "numeric", "Historical only - TARGET", "Decimal"),
        ("next_year_value", "Value one year after the transaction", "numeric", "Historical only - TARGET", "Millions of dollars; the analogue of realized game value"),
        ("asking_price", "Current asking price", "numeric", "Candidates only", "Millions of dollars - what the seller is asking NOW, not a future value"),
        ("debt_rate", "All-in debt interest rate offered on the asset", "numeric", "Candidates only", "Decimal"),
        ("max_ltv", "Lender maximum loan-to-value for this asset", "numeric", "Candidates only", "Decimal; a binding game constraint"),
        ("amortization_years", "Loan amortization term", "integer", "Candidates only", "Years"),
        ("property_name", "Display name", "string", "Candidates only", "Descriptor only, not a model feature"),
        ("data_tag", "Provenance tag", "string", "Candidates only", "Real public context layered over a synthetic operating case"),
    ]
    return pd.DataFrame(entries, columns=["column", "description", "type", "appears_in", "notes"])


def build_prediction_template(candidates: pd.DataFrame) -> pd.DataFrame:
    """The authoritative submission contract (see src.game.submission).

    Required columns ship with sentinel zeros so an unfinished template fails
    validation loudly and points at the column the student still owes. Optional
    columns ship BLANK, because writing zeros there would silently assert
    "I predict a 0% exit cap", which the validator would reject.
    """
    blank = np.nan
    return pd.DataFrame(
        {
            "team_id": "",
            "property_id": candidates["property_id"].tolist(),
            "model_name": "",
            "predicted_fair_value": 0.0,
            "predicted_noi_growth": 0.0,
            "probability_of_downside": blank,
            "max_bid": 0.0,
            "target_ltv": 0.0,
            "predicted_noi": blank,
            "predicted_exit_cap": blank,
            "confidence": blank,
            "model_version": "1.0",
            "notes": "",
        }
    )


def build_game_rules(candidate_count: int, historical_count: int) -> str:
    return f"""# REAL 605 — CRE Investment Committee: Game Rules

## The idea

You build the model. The game is the decision environment.

The game does **not** perform analytics for you. Before class you receive a
dataset, build whatever model you like outside the game (Excel, Python, R,
gradient boosting — your choice), and convert your analysis into an explicit
investment policy. Then you bring that policy into a live, competitive market.

```
analytical model -> property forecast -> investment policy -> capital allocation decision
    -> realized result -> feedback
```

## Before class

1. Download this packet.
2. `historical_training.csv` — {historical_count:,} observations with **known outcomes**.
3. `game_candidates.csv` — {candidate_count} properties the game will offer, with **no future outcomes**.
4. Build a model. Predict for every candidate property.
5. Fill in `prediction_submission_template.csv` and upload it at **Model Check-In**.

### Required submission columns

| Column | Meaning | Units |
| --- | --- | --- |
| `team_id` | Your team / fund name | text |
| `property_id` | Must match a candidate id exactly | text |
| `model_name` | Name of your model | text |
| `predicted_fair_value` | Your model's valuation | $M |
| `predicted_noi_growth` | Expected next-year NOI growth | decimal |
| `probability_of_downside` | Probability the investment underperforms | 0-1 |
| `max_bid` | The most your model says you should pay | $M |
| `target_ltv` | Leverage your model recommends | decimal |

Optional: `predicted_noi`, `predicted_exit_cap`, `confidence`, `model_version`, `notes`.

`max_bid` is the important one. It is where analysis becomes a **policy**. Deciding
max bid before you see the seller's asking price or your rivals is the entire point.

The game validates your submission structure but will **never** tell you whether your
predictions are accurate. Accuracy is revealed only as rounds resolve.

## During class

| Stage | Time |
| --- | --- |
| Rules briefing | 5 min |
| Practice round (not scored) | 5-8 min |
| Round 1 | 8 min |
| Round 2 | 8 min |
| Round 3 | 8 min |
| Round 4 | 8 min |
| Final debrief | 15-20 min |

One scored round is one simulated year.

## Capital

Every team starts with **$100M equity**. This is configurable by the instructor.

Capital is scarce. You cannot bid aggressively on everything, and money you spend in
Round 1 is gone in Rounds 2-4.

## Acquiring property

Each round, every team sees the **same** properties. You choose **PASS** or **BID**.

If you bid, you submit:

- `bid_price`
- `ltv`

That's it. Your analytical work already happened; the game will not make you fill in
a thesis form on a timer.

### Auction rules (sealed bid)

1. Highest **valid** bid wins the property.
2. The winner pays its own submitted price.
3. A bid is valid only if: bid > 0; LTV within the asset's `max_ltv`; the round is
   open; and you have enough equity, `cash >= bid_price x (1 - ltv)`.
4. The seller has a **hidden reserve price**. If the highest bid is below the reserve,
   the property does not sell.
5. **Tie-break:** if two bids are exactly equal, the lower LTV (more equity) wins.
   If still tied, a seeded deterministic tie-break decides.

Every one of these rules lives in `src/game/adjudicator.py`. No language model or
opaque score decides who wins a property.

## Your model during play

Beside each deal you will see a private **YOUR MODEL** panel:

```
YOUR MODEL
Fair Value:          $54.2M
Ask:                 $49.0M
Predicted NOI Growth: +3.1%
Downside Probability: 18%
Max Bid:             $50.5M
Target LTV:          60%
```

These are **your own uploaded numbers**. The game is reminding you what your analysis
said — it is not computing predictions. No other team can see your panel.

## Human overrides

The game records when your bid departs from your own policy:

```
model max bid   = $48.0M
your actual bid = $52.0M
manager_override = +$4.0M
```

and separately for leverage:

```
target_lTV = 55%    actual LTV = 65%    leverage_override = +10pp
```

You are **not** punished for overriding your model. Overriding is recorded, then
discussed. The interesting question — the graduate-level one — is *when* a human
should trust a model and when they should overrule it.

## Market evolution

Each round advances the market by one year:

- Treasury and financing environment change
- Employment growth and vacancy move
- Property NOI grows or falls
- Cap rates shift
- Your holdings are revalued

NOI growth follows an explicit function: a base rate, a bonus when market vacancy is
tight, plus seeded idiosyncratic noise. There are no arbitrary "recession card" events.
All randomness is seeded and reproducible, so the same seed replays the same game.

Properties you buy in Round 1 stay in your portfolio through Round 4 and are revalued
every year. Overpaying in Round 1 has consequences you live with.

## What owning a property actually costs

Every year, each property you own produces and consumes cash:

| Line | Rule |
| --- | --- |
| **NOI income** | Each property pays its net operating income in cash. |
| **Interest** | Each property pays interest on its own loan: `debt x debt_rate`. Interest-only; there is no amortisation. |
| **Capital reserve** | Tenant improvements, leasing commissions and replacement reserves, charged as a percentage of the property's value per year: Industrial 0.6%, Office 1.8%, Multifamily 1.0%, Retail 1.5%. |

And when you buy:

| Line | Rule |
| --- | --- |
| **Deal costs** | Legal, diligence, title and financing fees equal to **2.0% of the purchase price**, paid in cash on closing. Lenders do not finance closing costs, so you need equity **plus** deal costs available or your bid is rejected. |

These are the rules that make the price you pay matter. A property bought near the
asking price and financed at maximum loan-to-value roughly earns its cost of debt.
The money is made by buying assets your model says are cheap, not by buying the most
assets. Buying a good building at a bad price destroys value.

## How you win

Two separate boards — deliberately not blended into one opaque score.

### Game leaderboard (who wins the game)

**Ending fund NAV.** Also shown: cumulative return, cash, debt, portfolio LTV.

```
NAV = cash + property values - debt
```

Every dollar of NAV change comes from one of five channels, and they reconcile exactly:

```
NAV - starting equity
    = (property values - what you paid for them)
    + NOI income received
    - interest paid
    - deal costs paid
    - capital reserves funded
```

### Analytics leaderboard (how good the analysis was)

- Valuation MAE
- NOI forecast MAE
- Brier score / downside calibration
- Value added over a naive benchmark
- Contribution of human overrides

A good model with poor decision discipline can lose. A mediocre model with excellent
discipline can win. That separation is the point.

## The debrief: model vs manager vs luck

For each major investment attempt the debrief separates:

- **Model quality** — was the prediction any good?
- **Manager quality** — did you follow or override your model, and was that sensible *ex ante*?
- **Outcome** — what actually happened?

Cases are classified as good/bad on each axis, including the uncomfortable ones:
*good model, good decision, bad outcome* and *bad model, bad decision, lucky win*.

Decision quality is judged against the ex-ante expected-value distribution, **not**
against what the dice happened to do.

## Data honesty

| Tag | Meaning |
| --- | --- |
| REAL PUBLIC DATA | FRED macro series, Orange County parcel context |
| DERIVED FEATURE | employment density |
| SIMULATED MARKET STATE | per-type vacancy and cap rates |
| SYNTHETIC OPERATING CASE | property NOI, rents, prices |

Property operating cases are transparent synthetic teaching data calibrated to real
Orange County anchors. This game does not forecast the actual Orange County market,
and nothing here is investment advice.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the student game packet")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--candidates", type=int, default=GAME_CANDIDATE_COUNT)
    args = parser.parse_args()

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    print("Building student game packet...")

    candidates = build_game_candidates(args.candidates)
    candidates.to_csv(out / "game_candidates.csv", index=False)
    print(f"  game_candidates.csv            {len(candidates):>6,} rows "
          f"({candidates['property_id'].nunique()} unique properties)")

    historical = build_historical_training()
    historical.to_csv(out / "historical_training.csv", index=False)
    print(f"  historical_training.csv        {len(historical):>6,} rows "
          f"({historical['date'].nunique()} vintages)")

    dictionary = build_data_dictionary()
    dictionary.to_csv(out / "data_dictionary.csv", index=False)
    print(f"  data_dictionary.csv            {len(dictionary):>6,} rows")

    template = build_prediction_template(candidates)
    template.to_csv(out / "prediction_submission_template.csv", index=False)
    print(f"  prediction_submission_template.csv {len(template):>4,} rows")

    (out / "GAME_RULES.md").write_text(
        build_game_rules(len(candidates), len(historical))
    )
    print("  GAME_RULES.md                  written")

    print(f"\nDone. Packet written to {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
