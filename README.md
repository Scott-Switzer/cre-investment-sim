# REAL 605 CRE Investment Committee Simulation

A classroom simulation for Professor Tim Frenzel's REAL 605 Real Estate Analytics course at Chapman University.

This is **not** a game that performs the analytics for students. It is a market/decision environment in which doing the analytics provides an advantage.

## The instructional pattern

```
BEFORE CLASS   historical data -> students build a model EXTERNALLY -> predictions + investment policy
DURING CLASS   model check-in -> strategy card -> practice round -> live rounds -> feedback -> adapt
END            final NAV + analytics leaderboard + model / manager / luck debrief
```

The game is the **decision environment**. The student's model is the **analytical engine**. Those two layers stay separate: the game never computes a student's predictions, it only *displays* what their uploaded model said.

The Data Catalog, SQL Lab, Valuation Lab and Geospatial View remain available as **course preparation tools**, deliberately kept out of the timed round screen so nobody navigates eleven analytical pages while the clock runs.

## Two modes

The landing page splits the app in two:

- **1 · Prep** — Dataset Downloads, Model Check-In, Strategy Card, plus the analytics labs.
- **2 · Live Game** — practice round, four scored rounds, sealed-bid auctions, portfolio, feedback, leaderboard.

## Quick start (demo mode)

```bash
# 1. create environment
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -e ".[dev]"

# 2. build the cached demo dataset (idempotent)
uv run python scripts/bootstrap_demo.py

# 3. build the pre-class student packet
uv run python scripts/build_student_game_packet.py

# 4. launch
uv run python -m streamlit run app.py
```

No API keys are required for the cached demo. To refresh live public data, set `CENSUS_API_KEY` and/or `FRED_API_KEY` in `.env` and run `python scripts/refresh_public_data.py`.

## Verify the whole game loop

```bash
uv run python scripts/verify_demo_flow.py   # practice -> 4 rounds -> winner -> debrief
uv run python -m pytest tests/ -q
```

`verify_demo_flow.py` walks the exact professor demonstration sequence with the real demo teams and the real adjudicator, and fails loudly if any step breaks.

## The student packet

`python scripts/build_student_game_packet.py` writes to `student_packet/`:

| File | Contents |
| --- | --- |
| `historical_training.csv` | 2,400 observations with **known outcomes** (targets: `next_year_value`, `next_year_noi`, `noi_growth_realized`) |
| `game_candidates.csv` | the 120 properties the game actually offers, with **no future outcomes** |
| `data_dictionary.csv` | every column, its units, and its provenance tag |
| `prediction_submission_template.csv` | the submission contract, one row per candidate |
| `GAME_RULES.md` | the rules students are playing under |

**The packet and the game share one data source.** Candidates are the game's own property pool, and training targets are produced by the same `realized_year_outcome` function the adjudicator uses to revalue assets. A model trained on the packet is therefore learning the process the game actually runs, not a lookalike dataset.

## Game rules (MVP)

- **Capital:** $100M equity per team, configurable.
- **Rounds:** 1 practice round (never scored) + 4 scored rounds. One round = one simulated year.
- **Deals:** 4 properties per round; every team sees the same deals.
- **Decision:** PASS, or BID with `bid_price` and `ltv`. That is all.
- **Auction:** sealed bid. Highest **valid** bid wins and pays its own price. Valid means bid > 0, LTV within the asset's `max_ltv`, round open, and enough equity (`cash >= bid x (1 - ltv)`).
- **Reserve:** the seller has a hidden reserve price; if the top bid is below it, nothing sells.
- **Tie-break:** lower LTV (more certainty of close) wins; if still tied, a seeded deterministic draw.
- **Persistence:** assets bought in Round 1 are revalued and held through Round 4.
- **Two leaderboards:** the game is won on **ending NAV**. Analytical quality is scored separately (valuation MAE, NOI MAE, Brier calibration, value added vs a naive benchmark, override contribution).

## Adjudicator principle

The game has an explicit, inspectable rules engine at `src/game/adjudicator.py`. No LLM and no opaque model decides whether a bid is valid, who wins a property, what a property is worth, what the market does, or who is scored how. All economic coefficients are declared as module constants in that file — including the ones the student packet imports, so a reviewer can read every number that determines an outcome.

Market evolution is driven by one pure function, `realized_year_outcome`, so the figure a team is shown in its round feedback is exactly the value the engine applied to its books.

Full world state (every bid, every reserve) is kept separate from the player observation state produced by `Adjudicator.get_player_observation`.

## Stack

- Python 3.11+
- Streamlit
- DuckDB (analytical DB / SQL lab)
- pandas, numpy
- scikit-learn, statsmodels
- geopandas / shapely / pyproj (where needed)
- pydeck / streamlit-folium for maps
- plotly / altair
- pytest

## Repo structure

```
app.py                      # Streamlit entry point: Prep + Live Game modes
pages/                      # one file per view
datasets.py                 #   PREP: student packet downloads
model_checkin.py            #   PREP: upload model outputs
strategy_card.py            #   PREP: your policy before play
live_game.py                #   LIVE: unified round screen
leaderboard.py              #   LIVE: standings + overrides
final_debrief.py            #   LIVE: model/manager/luck debrief
briefing.py data_catalog.py data_quality.py market_explorer.py
sql_lab.py valuation_lab.py geospatial.py deal_room.py
investment_decision.py results.py professor_control.py provenance.py
src/
  game/
    adjudicator.py          # THE RULES ENGINE: bids, auctions, reserve, market, valuation, NAV
    manager.py              # round state machine + classroom timing presets
    bots.py                 # deterministic demo-bot policies
    submission.py           # the student model output contract + validation
    analytics.py            # analytics leaderboard + model/manager/luck classification
  data/                     # data access, provenance, market anchors, macro, property generator
  simulation/               # world state, scenarios, round resolution
  finance/                  # financial engine (loan, DSCR, LTV, cap rate, returns, portfolio)
  scoring/                  # scoring weights, forecast metrics, Brier, decision quality
  models/                   # naive valuation benchmarks, baseline regression
  geo/                      # parcel/geospatial access, derived features, mapping
  utils/                    # state, config, seed, PIT snapshot, audit
data/
  raw/                      # cached raw public data samples
  processed/                # cleaned analytical tables
  synthetic/                # semipsynthetic property operating data + manifest
  cache/                    # api caches
student_packet/             # generated: the pre-class dataset + submission template
demo_teams/                 # generated: deterministic demo-bot model outputs
notebooks/                  # starter notebooks for students
tests/                      # pytest suite
docs/                       # methodology, learning objectives, demo script, reference prototypes
config/                     # scoring weights, simulation parameters, app config
scripts/                    # bootstrap_demo.py, build_student_game_packet.py,
                            # create_demo_teams.py, verify_demo_flow.py, refresh_public_data.py
```

## Data honesty

Every table and column carries provenance metadata:

`source_name`, `source_url`, `observation_date`, `available_at`, `retrieved_at`, `data_type`, `is_synthetic`, `notes`

Visible tags in the UI:

- REAL PUBLIC DATA
- SYNTHETIC TEACHING DATA
- DERIVED FEATURE
- SIMULATED FUTURE

The property operating cases are transparent synthetic teaching data calibrated around real Orange County public market anchors. The application does not claim to forecast the actual Orange County market.

## Course alignment

See `docs/REAL605_LEARNING_OBJECTIVES.md`.

## Demonstration success condition

A reviewer can sit down, run locally, and demonstrate:

> This uses real Orange County and public economic/geospatial data where possible. The property operating cases are transparent synthetic teaching data. Students receive imperfect point-in-time data, analyze it with the same tools taught in REAL 605, commit to an investment decision, and then the simulated market resolves. We can assess whether their model was good, whether their decision was good, and whether they simply got lucky.

## Reference prototypes

The original HTML demo and Excel MVP are preserved as reference artifacts in `docs/reference/`. Their deal logic, financing calculations, scoring concepts, and Orange County positioning were used as starting context. The Python implementation improves architecture rather than reproducing the spreadsheet formulas verbatim.

## License

Educational use for Chapman REAL 605.
