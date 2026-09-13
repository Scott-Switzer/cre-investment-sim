# Student Packet — Start Here

This is the short version. The full rules are in `student_packet/GAME_RULES.md`
and every column is described in `student_packet/data_dictionary.csv`.

## What you get

| File | Rows | What it is |
| --- | --- | --- |
| `historical_training.csv` | 2,400 | 400 Orange County properties, observed in six annual vintages (2019-2024). Outcomes **are** included. |
| `game_candidates.csv` | 120 | The properties the game will actually offer. Outcomes are **withheld**. |
| `data_dictionary.csv` | 33 | Every column, its units, and whether it is a feature or a target. |
| `prediction_submission_template.csv` | 120 | Pre-filled with the candidate ids. Fill in your predictions and upload this. |
| `GAME_RULES.md` | — | Full game rules: auction, capital, market evolution, scoring. |

`historical_training.csv` is a **panel**: `OC-INDU-01` appears once per vintage. The
same 120 properties that appear in `game_candidates.csv` also appear in the
historical file, because the game is offering you buildings whose history you can
already study. Using a property's own history is legitimate — you are underwriting a
known asset, not a stranger.

## What to predict

Build the model yourself, outside the game, in whatever tool you like. Two targets
matter:

1. **Fair value next year** — what the property will be worth one simulated year
   from now. In the historical data this is `next_year_value`.
2. **Next-year NOI growth** — `noi_growth_realized` in the historical data.

### Use only these columns as inputs

`property_type`, `submarket`, `building_sf`, `year_built`, `occupancy`, `noi`,
`market_rent`, `in_place_rent`, `going_in_cap`, `opex_ratio`, `walt`,
`tenant_concentration`, `capex_need`, `property_quality`, `units`, `primary_risk`,
`employment_density`, `treasury_rate`, `market_vacancy`.

For the candidates you may also use `asking_price`, `debt_rate`, `max_ltv`, and
`amortization_years`.

### Never use these as inputs — they are the answer

`transaction_cap_rate`, `transaction_price`, `noi_growth_realized`, `next_year_noi`,
`next_year_cap_rate`, `next_year_value`.

`next_year_value` is exactly `next_year_noi / next_year_cap_rate`. A model that reads
any of these columns scores perfectly and teaches you nothing. Treat them as targets
only.

## What to submit

Upload `prediction_submission_template.csv` with one row per candidate property. The
required columns are:

| Column | Units | Meaning |
| --- | --- | --- |
| `team_id` | text | Your fund name |
| `property_id` | text | Must match a candidate id **exactly** |
| `model_name` | text | What you call your model |
| `predicted_fair_value` | $M | Your valuation of the property next year |
| `predicted_noi_growth` | decimal | e.g. `0.031` for +3.1% |
| `probability_of_downside` | 0-1 | Your probability the investment underperforms |
| `max_bid` | $M | **The most your model says you should pay** |
| `target_ltv` | decimal | e.g. `0.60` |

Optional: `predicted_noi`, `predicted_exit_cap`, `confidence`, `model_version`, `notes`.

**`max_bid` is the one that turns analysis into policy.** It is the number the game
will hold you to. Everything else describes the property; `max_bid` describes your
intent.

## How to submit

Open the app and go to **Model Check-In**, then upload your CSV. Validation checks
that every `property_id` is a real candidate, that you have not submitted the same
property twice, that probabilities are between 0 and 1, that LTV is within range, and
that there are no unknown ids. You will see your own validation statistics.

**The app will not tell you whether your model is any good.** Accuracy is revealed
only as rounds resolve, which is the point.

Once your model is accepted it is **frozen** for the game. You cannot re-upload
between rounds. That constraint is deliberate: the exercise is about making decisions
with the analysis you brought, not about quietly refitting after every result.

## What the game does with it

Before every bid you will see a private panel showing your own numbers:

```
YOUR MODEL
Fair Value            $54.2M
Ask                   $49.0M
Predicted NOI Growth  +3.1%
Downside Probability  18%
Max Bid               $50.5M
Target LTV            60%
```

No other team can see this. The game is not computing these predictions — it is
reminding you what your analysis said.

You then choose **PASS** or **BID**, and if you bid, a price and an LTV. Highest valid
bid wins the property and pays its own price. Capital is finite, so you cannot chase
everything.

Buying and owning cost real money, and the game charges it:

- **Deal costs** of 2.0% of the price, paid in cash on closing. You must have equity
  **plus** deal costs available or your bid is rejected.
- **Interest** each year on each property's loan at its quoted debt rate.
- A **capital reserve** each year — Industrial 0.6%, Office 1.8%, Multifamily 1.0%,
  Retail 1.5% of value — for tenant improvements and replacement reserves.

A property bought near the asking price and levered to the limit roughly earns its
cost of debt. The edge comes from buying assets your model says are **cheap**, not
from buying the most assets.

## How you are judged

Two separate boards:

- **Game leaderboard** — ending fund NAV. This is who wins.
- **Analytics leaderboard** — valuation MAE, NOI forecast MAE, downside calibration,
  value added versus a naive benchmark, and the measured contribution of your
  overrides.

They are deliberately kept apart. A good model with poor discipline can lose, and a
mediocre model with excellent discipline can win. The final debrief separates your
**model quality**, your **decision quality**, and your **luck** — because those are
three different things and confusing them is the most expensive mistake in the course.
