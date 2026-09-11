# Demo Script — REAL 605 CRE Simulation (≤ 8 minutes)

Run after `uv run python -m streamlit run app.py`. Demo mode is on by default.

## 0. Launch (≈ 30s)
1. Open the app in a browser.
2. Confirm the sidebar shows: Demo mode ON, Scenario = Base Case, Decision date 2024-03-31, Available capital $150M.

## 1. Home (30s)
- Read the one-paragraph value proposition: doing the analytics provides an advantage; not a game that does the work for students.
- Point out the data honesty tags: REAL PUBLIC DATA · SYNTHETIC TEACHING DATA · DERIVED FEATURE · SIMULATED FUTURE.

## 2. Briefing (45s)
- Show the investment committee request, mandate (capital, hurdle 8%, max LTV 70%, min DSCR 1.20x, concentration limits), and decision date.
- Show the public market anchors table (CBRE OC Q2 2026 office/industrial/multifamily + FRED 10Y).
- Emphasize: these are REAL PUBLIC DATA anchors. The properties are synthetic.

## 3. Data Catalog (45s)
- Show the data sources table with provenance (source name, URL, data status).
- Note the limitations: OC assessed/tax value is NOT transaction market value; ACS/FRED are cached public-data samples; property cases are synthetic.
- Download the student property copy CSV to show students get raw data.

## 4. Data Quality Challenge (60s)
- Show the manifest of injected issues (DQ-01..DQ-07).
- Show the raw student copy with the leakage field `future_market_cap_rate_observed_q2_2026` present.
- Point out the leakage trap: that field is from Q2 2026, available AFTER the 2024-03-31 decision date. Using it would be leakage.
- Show the instructor truth table (instructor only).

## 5. Market Explorer (60s)
- Show type distribution, cap-rate box plots, asking price/NOI histograms, market medians, occupancy vs rent scatter, correlation matrix.
- Emphasize: enough to form hypotheses — not an answer card.

## 6. SQL Lab (60s)
- Show available tables and schemas.
- Run one example task (e.g., median cap by type) from the example-tasks list.
- Show the persistent `real605.duckdb` file students can query externally.

## 7. Valuation Lab (60s)
- Show naive benchmarks (NOI/cap, median comp, price-per-SF).
- Show the baseline linear regression coefficients and train MAE/R^2; compare to naive benchmarks.
- Show the Ridge alternative.
- Show the training-data download.
- (Optional) upload a sample predictions CSV to show the submission interface.

## 8. Geospatial View (45s)
- Show the PyDeck map of the 30 properties by type.
- Show derived features: employment density, distance to SNA/Irvine, census tract approx., flood indicator placeholder.
- Note the coordinates are at plausible submarket centers with small jitter; real OC parcel geometry is available from OC GIS REST and would be overlaid in a fuller version.

## 9. Deal Room (60s)
- Pick a property (e.g., Anaheim Commerce Center).
- Show asking price, NOI, going-in cap, occupancy, WALT, rent, tenant concentration, debt rate, max LTV, primary risk.
- Set BUY, a bid, LTV, NOI growth forecast, exit cap forecast, confidence, probability of loss.
- Show the underwriting output: equity required, debt service, DSCR, debt yield, predicted NOI, predicted value, predicted levered return.

## 10. Investment Decision (60s)
- Show the full pipeline with thesis and "what would prove this wrong."
- Click "Submit decision (saves to round)." Note that the round locks.

## 11. Professor Control (60s)
- Show scenario selector, decision date, seed, capital.
- Click "Start / restart game" with the Base Case scenario.
- Show current round status (round 1 of 3, not locked, not revealed).
- Click "Lock round" then "Reveal outcome."
- Show ground truth and student decisions log.
- Show score components summary; export scores CSV.

## 12. Results / Debrief (60s)
- Show per-property debrief: actual NOI growth, exit cap, exit value, levered return, forecast value/NOI error, Brier loss, DSCR, LTV, expected levered return, and the five component scores + total.
- Emphasize the separation: outcome quality vs forecast quality vs risk discipline vs decision quality vs process quality. Decision quality is scored against the EXPECTED outcome before realization, so luck is not rewarded as skill.
- Read one debrief question aloud.

## 13. Provenance & Methodology (30s)
- Show what is observed vs generated; what the app does NOT claim (not a forecast of the actual OC market).
- End.

Total ≈ 7–8 minutes.
