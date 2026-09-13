# REAL 605 — CRE Investment Committee: Game Rules

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
2. `historical_training.csv` — 2,400 observations with **known outcomes**.
3. `game_candidates.csv` — 120 properties the game will offer, with **no future outcomes**.
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
