# Game Economics

Every number that determines an outcome in the simulation, in one place.

This file is the instructor-facing companion to `src/game/adjudicator.py`. The
coefficients below are module-level constants there, and the student packet
builder imports them, so a model trained on the packet is learning the same
process the game runs. Nothing in the game is scored by a hidden formula, an LLM,
or a black box.

Frozen at the release candidate described in `BALANCE` at the bottom.

---

## 1. The game in one paragraph

Four funds each start with **$100M of equity** and no debt. Over four scored
years, the market offers **four properties per year** (16 total). Funds bid in a
sealed-bid auction, finance some of the price with debt, and hold everything they
win to the end. The fund with the highest ending **NAV** wins. A separate
analytics board scores the *quality of the analysis*.

---

## 2. How a property is priced and revalued

### 2.1 The operating case (property generation)

`src/data/properties.py` generates each property deterministically from the game
seed. Per property type:

| | Industrial | Office | Multifamily | Retail |
| --- | --- | --- | --- | --- |
| Going-in cap rate range | 5.0–6.0% | 6.2–7.8% | 4.8–5.8% | 6.0–7.0% |
| Debt rate range | 6.00–6.60% | 6.30–7.20% | 5.90–6.40% | 6.30–6.90% |
| Maximum LTV | 70% | 60% | 70% | 65% |
| Size | 60k–220k SF | 90k–260k SF | 20k–70k SF | 30k–160k SF |

NOI is built from size, market rent, occupancy and an operating-expense ratio,
then **asking price = NOI ÷ going-in cap**. The going-in cap is the property's
own cap rate, and it is drawn independently of the type's market cap rate below.
That gap is the game's central analytical signal.

### 2.2 Market capitalisation rates

`realized_year_outcome()` is the **only** function that decides what a property
is worth. Portfolio revaluation and the round feedback card both call
it, so what a team is told happened is exactly what was applied to its books.

```
noi_growth = clip( NOI_GROWTH_BASE
                   + tight_vacancy_bonus (if vacancy <= 8%)
                   + N(0, NOI_GROWTH_SIGMA),
                   -10%, +15% )
cap_rate   = clip( market cap rate for the type + N(0, CAP_NOISE_SIGMA),
                   3%, 12% )
next_noi   = NOI x (1 + noi_growth)
value      = next_noi / cap_rate
```

| Constant | Value |
| --- | --- |
| `NOI_GROWTH_BASE` | 2.0% per year |
| `NOI_GROWTH_TIGHT_VACANCY_BONUS` | +1.0% per year |
| `TIGHT_VACANCY_THRESHOLD` | 8.0% |
| `NOI_GROWTH_SIGMA` | 1.5% |
| `MIN_NOI_GROWTH` / `MAX_NOI_GROWTH` | −10% / +15% |
| `CAP_NOISE_SIGMA` | 0.05% |
| `MIN_CAP_RATE` / `MAX_CAP_RATE` | 3% / 12% |

Starting market conditions and macro environment:

| Constant | Industrial | Office | Multifamily | Retail |
| --- | --- | --- | --- | --- |
| `BASE_VACANCY` | 5.5% | 13.3% | 3.6% | 6.5% |
| `BASE_CAP_RATE` | 5.5% | 7.2% | 5.2% | 6.5% |

`BASE_POLICY_RATE` 5.3% · `BASE_UNEMPLOYMENT` 3.9% ·
`BASE_EMPLOYMENT_GROWTH` 0.6% · `BASE_INFLATION` 2.8% ·
`BASE_CREDIT_CONDITIONS` 0.5

Scenario deltas: `Base Case` (none), `Rate Shock` (policy +2.00pp, growth
−1.00pp), `Growth Rebound` (policy −0.50pp, growth +1.50pp).

**Typical pool values** (seed 20240331, 120 properties): mean asking price
$28.29M, mean going-in cap 5.93%, mean debt rate 6.40%, mean maximum LTV 66%.
The realised value relative to the ask is a coin flip — the property is worth
more than the ask about 49% of the time — which is why a model that only reports
the ask adds nothing.

---

## 3. Auctions

- **Sealed bids.** Each fund submits at most one bid per property per round.
- **Reserve price.** Each property carries a hidden reserve drawn deterministically
  from **90–95% of the asking price**. The highest bid below the reserve wins
  nothing; the property does not sell.
- **Winner.** The highest **valid** bid. A bid is valid when the round is open,
  the price is positive, `0 < LTV <= the property's maximum LTV`, and the fund
  holds enough cash for **equity + deal costs** (see §4).
- **Tie-break, in order:** (1) lowest LTV — the more certain close — then (2) a
  seeded deterministic draw.
- **No second price.** The winner pays exactly what it bid.

A team can win more properties in a round than it can fund; the engine then
unwinds the most expensive wins first and marks them unsold, rather than silently
overdrawing the fund.

---

## 4. Costs of buying and owning

These are the rules that make the price paid matter. Without them, a property
bought at the ask earned a free levered lunch and the *volume* of acquisitions
decided the scoreboard rather than the quality of the analysis.

### 4.1 Deal costs (acquisition)

```
acquisition_cost = purchase_price x ACQUISITION_COST_RATE
```

`ACQUISITION_COST_RATE = 2.0%`. Legal, diligence, title and financing fees.
Lenders do not finance closing costs, so this is paid from cash on closing and
reduces NAV immediately. Bid validity requires `cash >= equity + deal costs`
(`equity_required_for()`), and the bot policy applies the same rule.

### 4.2 Capital reserves (recurring)

```
reserve = sum over holdings of ( current_value x CAPITAL_RESERVE_RATE[type] )
```

| Type | Rate |
| --- | --- |
| Industrial | 0.6% of value per year |
| Office | 1.8% of value per year |
| Multifamily | 1.0% of value per year |
| Retail | 1.5% of value per year |

Tenant improvements, leasing commissions and replacement reserves. It scales with
the **asset**, not the loan, so leverage multiplies it.

### 4.3 Debt interest

```
interest = sum over holdings of ( debt_amount x debt_rate )
```

Interest-only; the MVP has **no amortisation** and no loan maturity. Each property
carries the debt rate quoted at the time it was bought.

---

## 5. The round, in exact order

1. Market advances one year (`advance_market`).
2. Auctions resolve for every property offered this round.
3. Winning funds pay equity + deal costs in cash, take on debt, and book the asset.
4. **NOI income is credited** — every holding, including one bought this round,
   pays its NOI in cash.
5. **Holdings are revalued** (`realized_year_outcome`), which also advances each
   holding's NOI to next year.
6. **Capital reserves are funded** on the revalued asset.
7. **Interest is charged** on the debt that financed it.
8. NAV and cumulative return are computed.

The order is deliberate: income is earned at the NOI the asset carried, reserves
are funded on the revalued asset, and interest is paid on the debt outstanding.

Practice behaves like a scored round for pricing and feedback but awards no
property, moves no cash, and charges no income, reserve or interest.

---

## 6. NAV, and the exact decomposition

```
NAV = cash + property values - debt
```

Every dollar of NAV change is one of five channels, and they reconcile to machine
precision (verified in `tests/test_game_economics.py`):

```
NAV - starting equity
    = sum(current value - purchase price)     value channel (appreciation)
    + NOI income received                     income
    - interest paid                           cost of debt
    - deal costs paid                         cost of acquisition
    - capital reserves funded                 cost of ownership
```

`return_on_cost` — the honest leverage test — is
`(value channel + income - reserves) / total purchase price`, compared against the
weighted average debt rate. Borrowing adds value only when that exceeds the rate.

---

## 7. BALANCE — measured, not asserted

`scripts/balance_harness.py` runs three experiments and is the evidence behind the
freeze. Run `uv run python scripts/balance_harness.py --seeds 100`.

### Experiment C — the classroom game (100 seeds, 3 bot funds + 1 human)

| Human strategy | mean NAV | win rate | top-2 | assets | premium to ask |
| --- | ---: | ---: | ---: | ---: | ---: |
| never bids | $100.00M | 0% | 10% | 0.0 | — |
| weak model, disciplined | $107.77M | 47% | 73% | 4.0 | −0.09% |
| medium model, disciplined | $109.35M | 56% | 86% | 4.0 | −0.17% |
| **strong model, disciplined** | **$110.72M** | **61%** | **90%** | 4.0 | −0.25% |
| strong model, only cheap deals | $103.79M | 14% | 47% | 0.9 | −2.61% |
| meets the ask at max LTV | $109.89M | 62% | 89% | 7.1 | −0.03% |
| 5% over ask at max LTV | $104.39M | 50% | 68% | 9.6 | +4.84% |

- **Analysis effect** (strong model minus weak model, same policy): **+$2.95M**.
- **Deployment effect** (aggressive minus disciplined, same model): **−$4.96M**.
- `corr(NAV, assets acquired)` = **+0.21** — deployment does **not** dominate.

### Experiment A — pure economics (100 seeds, each strategy alone)

| Strategy | mean NAV | profitable | assets | premium to ask |
| --- | ---: | ---: | ---: | ---: |
| `MODEL_DISCIPLINED` | $125.29M | 100% | 8.6 | −2.45% |
| `VALUE_SELECTIVE` | $124.28M | 100% | 5.9 | −4.01% |
| `STRONG_DISCIPLINED` | $122.08M | 100% | 7.6 | −0.52% |
| `MAX_LTV` | $118.14M | 99% | 10.1 | −0.17% |
| `WEAK_DISCIPLINED` | $115.78M | 99% | 7.0 | −0.28% |
| `RANDOM_VALID` | $114.92M | 98% | 5.3 | −2.78% |
| `WEAK_AGGRESSIVE` | $107.91M | 83% | 9.8 | +3.57% |
| `BUY_EVERYTHING` | $105.68M | 72% | 9.7 | +4.45% |
| `ALL_PASS` | $100.00M | 0% | 0.0 | — |

`corr(NAV, assets acquired)` = **+0.31** · `corr(NAV, premium paid to ask)` =
**−0.50** · `corr(NAV, realised selection quality)` = **+0.85**.
Model-quality effect **+$6.30M**, deployment effect **−$7.88M**.

### Experiment B — competition (40 seeds, all strategies in one shared game)

`STRONG_DISCIPLINED` beats `WEAK_AGGRESSIVE` in **32/40** games, mean NAV edge
**+$7.28M**. `WEAK_EVERYTHING`-style arms lose money outright (`WEAK_AGGRESSIVE`
$93.23M). Within-seed rank correlations: assets **−0.09**, LTV **−0.26**,
selection quality **+0.81**.

*Known limitation, stated rather than hidden:* Experiment B puts eleven bidders
into a sixteen-property market, so the arm that bids highest corners the pool and
`BUY_EVERYTHING` posts 50% of seed wins. That is a property of a sealed-bid auction
with a low reserve, not a return advantage — its mean NAV ($102.92M) is below the
disciplined arms' in Experiment A, and the real classroom game (Experiment C) has
four funds competing for the same sixteen assets.

### What the freeze guarantees

- Never bidding finishes last and essentially never wins.
- Buying everything, and buying at maximum leverage, do **not** dominate.
- A better model with disciplined bidding beats a worse model with aggressive
  deployment over many seeds.
- A weaker model still wins often enough that outcomes are uncertain — the strong
  model wins 61% of classroom games, not 100%.
- Paying above the ask is negatively correlated with NAV (−0.50 in Experiment A,
  −0.13 in Experiment C).
- More assets is **not** automatically better: `corr(NAV, assets)` is +0.31 in
  Experiment A, +0.21 in Experiment C, and −0.09 in Experiment B.

**The frozen coefficients are exactly the values in §2–§4.** Any change to them
must be accompanied by a re-run of the balance harness, because the balance above
is what the transaction costs are standing on.
