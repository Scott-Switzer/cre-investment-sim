# REAL 605 CRE Investment Committee Simulation

A classroom simulation for Professor Tim Frenzel's REAL 605 Real Estate Analytics course at Chapman University.

This is **not** a game that performs the analytics for students. It is a market/decision environment in which doing the analytics provides an advantage. Students receive imperfect point-in-time data, analyze it with the same tools taught in the course, commit to an investment decision, lock it, and then the simulated market resolves. The debrief separates outcome quality from forecast quality, risk discipline, decision quality, and process/data integrity.

## Quick start (demo mode)

```bash
# 1. create environment
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -e ".[dev]"

# 2. build the cached demo dataset (idempotent)
uv run python scripts/bootstrap_demo.py

# 3. launch
uv run python -m streamlit run app.py
```

Open the app, pick **Demo mode** in the professor controls, and follow `docs/DEMO_SCRIPT.md`.

No API keys are required for the cached demo. To refresh live public data, set `CENSUS_API_KEY` and/or `FRED_API_KEY` in `.env` and run `python scripts/refresh_public_data.py`.

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
app.py                      # Streamlit entry point
pages/                      # Streamlit pages (one file per major view)
src/
  data/                     # data access, provenance, market anchors, macro, census, lodes, parcels, property generator
  simulation/               # world state, scenarios, round resolution
  finance/                  # financial engine (loan, DSCR, LTV, cap rate, returns, portfolio)
  scoring/                  # scoring weights, forecast metrics, Brier, decision quality
  models/                   # naive valuation benchmarks, baseline regression, prediction submission
  geo/                      # parcel/geospatial access, derived features, mapping
  utils/                    # state, config, seed, PIT snapshot, audit
data/
  raw/                      # cached raw public data samples
  processed/                # cleaned analytical tables
  synthetic/                # semipsynthetic property operating data + manifest
  cache/                    # api caches
notebooks/                  # starter notebooks for students
tests/                      # pytest suite
docs/                       # methodology, learning objectives, build plan, demo script, reference prototypes
config/                     # scoring weights, simulation parameters, app config
scripts/                    # bootstrap_demo.py, refresh_public_data.py
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
