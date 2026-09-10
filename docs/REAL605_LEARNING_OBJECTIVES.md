# REAL 605 Learning Objectives — Implementation Map

Statuses: **IMPLEMENTED**, **PARTIAL**, **PLANNED**.

Setting IMPLEMENTED means there is an actual student activity in the app that exercises the objective. Installing a library is not enough.

---

## Course-wide learning outcomes

### 1. Data engineering — assemble multi-source real-estate data, build an analytics pipeline, and engineer location, comps, time, and macro features.
- **Game feature:** Data Catalog, Data Quality Challenge, Market Explorer, SQL Lab, Geospatial View.
- **Student activity:** Download imperfect student property copy, identify/describe injected data-quality issues, clean to a working dataset, write SQL against DuckDB, build derived geospatial features, join macro history.
- **Data used:** OC parcels/APN/address (real public), OC tax/assessment attributes (real public, NOT transaction value), CBRE OC anchors (real public), FRED macro (real public sample), Census ACS/LODES public-data samples (cached), semipsynthetic property operating data (synthetic).
- **Assessment artifact:** Cleaned student dataset; SQL queries; derived-feature table; data quality manifest responses.
- **Status: IMPLEMENTED** — the app exposes multi-source data, the data quality challenge, SQL lab, and derived geospatial features.

### 2. Valuation ML — frame valuation for ML, define targets/splits, choose algorithms, and build a baseline AVM.
- **Game feature:** Valuation Lab.
- **Student activity:** Use naive benchmarks (NOI/cap, median comp, price-per-SF) as a straw man; inspect the baseline linear regression coefficients and train/test metrics; download training data; build an improved model; submit predictions via CSV.
- **Data used:** Semipsynthetic property table with asking price as a teaching target proxy (instructor truth); derived features.
- **Assessment artifact:** Model predictions CSV; forecast error vs actuals once revealed.
- **Status: PARTIAL** — naive benchmarks + transparent baseline regression + prediction submission interface exist; a full student-built AVM workflow with a starter notebook is scaffolded but the notebook itself is a placeholder for the MVP.

### 3. Geospatial ML — build proximity/neighborhood signals and quantify spatial valuation effects.
- **Game feature:** Geospatial View, Market Explorer correlations.
- **Student activity:** Inspect derived features (employment density, distance to SNA/Irvine, census tract approx.), relate them to asking price/cap, consider spatial signals in their own valuation model.
- **Data used:** OC parcel context (real), submarket center coordinates with small jitter, cached LODES-style employment proxy, derived features.
- **Assessment artifact:** Geospatial feature table; correlation observations; (future) spatial valuation model.
- **Status: PARTIAL** — real parcel context and derived geospatial features are present; the app does not yet force a spatial valuation model, but the data and hooks exist for one.

### 4. Model training — compare gradient boosting/regularized models, control leakage using time/geography splits, and choose appropriate metrics.
- **Game feature:** Valuation Lab, SQL Lab, provenance/appendix.
- **Student activity:** Compare naive/baseline models; think about train/test splits; use the point-in-time snapshot to understand leakage; the Ridge baseline is included as a regularized alternative.
- **Data used:** Semipsynthetic property data; macro history; point-in-time snapshots.
- **Assessment artifact:** Model comparison notes; split strategy description; forecast metrics.
- **Status: PARTIAL** — a Ridge baseline and the point-in-time tests exist; a full gradient boosting + time/geography split lab with student-trained models is planned.

### 5. Interpretation — explain models clearly and present results in a modern dashboard for investment committees/operating partners.
- **Game feature:** Deal Room, Results/Debrief, Market Explorer, Geospatial View.
- **Student activity:** Write an investment thesis with a falsification test; present predicted vs actual, forecast error, DSCR, value change, key market drivers; use charts and the map in a committee-style narrative.
- **Data used:** Property underwriting outputs, debrief scorecard, market anchors, map.
- **Assessment artifact:** Thesis + falsification test; debrief responses; scorecard.
- **Status: IMPLEMENTED** — the decision journal forces a thesis/falsification and the debrief surfaces interpretation artifacts.

### 6. Forecasting — build time-series workflows including decomposition, stationarity, ARIMA with exogenous variables, and rolling-origin evaluation.
- **Game feature:** Market Explorer (historical market/macro charts), Simulation engine (round-after-round outcomes).
- **Student activity:** Explore macro/market history; think about how to forecast the macro drivers that feed the simulation; the simulation's round structure is a rolling-origin-like environment.
- **Data used:** Macro history, market anchors, round outcomes.
- **Assessment artifact:** Forecasts of macro/market variables (future extension); forecast accuracy scoring.
- **Status: PLANNED** — the data and round structure exist; a dedicated time-series forecasting lab/exercise is not yet built into the app.

### 7. Decision making — convert analytical findings into executive recommendations across alternative futures.
- **Game feature:** Briefing, Deal Room, Investment Decision, Professor Control (scenarios), Results/Debrief.
- **Student activity:** Frame the decision, analyze across scenarios, commit to BUY/PASS with bid/LTV/NOI growth/exit cap/confidence/thesis, see how the same information supports different decisions under different scenarios.
- **Data used:** Market anchors, property cases, scenario resolution, debrief.
- **Assessment artifact:** Decision journal; debrief; scenario comparison.
- **Status: IMPLEMENTED** — the core loop (briefing → decision → lock → reveal → debrief) and multi-scenario professor control are implemented.

---

## Module 1 section map

### 1. Business Problem Definition
- **Activity:** Briefing page — read the investment committee request, restate the problem, define success.
- **Status: IMPLEMENTED**

### 2. Data Sources and Data Types
- **Activity:** Data Catalog — identify real vs synthetic vs derived vs simulated, provenance, limitations.
- **Status: IMPLEMENTED**

### 3. Data Cleaning
- **Activity:** Data Quality Challenge — find and handle missing values, duplicates, inconsistent labels, date formats, stale observations, outliers, and the leakage field.
- **Status: IMPLEMENTED**

### 4. Descriptive Statistics
- **Activity:** Market Explorer — distributions, medians, correlations, cap-rate distributions, rent/vacancy history.
- **Status: IMPLEMENTED**

### 5. Data Visualization
- **Activity:** Market Explorer charts, Geospatial View map, Deal Room cards, debrief charts.
- **Status: IMPLEMENTED**

### 6. Feature Engineering
- **Activity:** Valuation Lab + Geospatial View — build/derive features (occupancy, WALT, tenant concentration, opex ratio, quality, employment density, distances) and use them in models.
- **Status: PARTIAL** — features exist and are downloadable; a guided feature-engineering exercise/notebook is scaffolded but not fully built.

### 7. Linear Regression
- **Activity:** Valuation Lab — inspect baseline linear regression coefficients, train/test MAE/R^2, compare to naive benchmarks.
- **Status: IMPLEMENTED**

### 8. Coding Fundamentals & AI Co-Pilots
- **Activity:** SQL Lab, Python-accessible DuckDB file, downloadable datasets — students write code to query and analyze; AI co-pilot use is a classroom practice, not an app feature.
- **Status: PARTIAL** — the environment supports coding exercises; an explicit AI co-pilot activity is planned.

### 9. Python Fundamentals
- **Activity:** Downloadable datasets and DuckDB file let students write Python to clean/analyze/model; the app itself is a Python+Streamlit reference.
- **Status: PARTIAL** — scaffolding exists; a dedicated Python-fundamentals lab is planned.

### 10. SQL Fundamentals
- **Activity:** SQL Lab — read-only console with example tasks; external DuckDB file for arbitrary SQL.
- **Status: IMPLEMENTED**

### 11. Building Effective BI Dashboards
- **Activity:** The whole app is a BI-style dashboard for an investment committee; students also interpret and present via the debrief.
- **Status: IMPLEMENTED** — the app is a dashboard; teaching dashboard-building as a student skill is planned (students building their own dashboard from the data is a natural extension).

---

## Summary

- IMPLEMENTED (course-wide): data engineering (data catalog, DQ challenge, SQL, geo), interpretation (thesis/falsification + debrief), decision making (full loop + scenarios).
- PARTIAL: valuation ML (baseline regression + submission; full AVM workflow pending), geospatial ML (data + derived features exist; spatial model pending), model training (Ridge + PIT tests exist; GB + time/geography split lab pending), forecasting (data + round structure exist; dedicated time-series lab pending), coding fundamentals/AI co-pilots, Python fundamentals, BI dashboards (app is a dashboard; student-authored dashboard pending).
- PLANNED: dedicated time-series forecasting lab, student-authored BI dashboard, AI co-pilot activity, full spatial valuation model, time/geography split lab with student-trained models.
