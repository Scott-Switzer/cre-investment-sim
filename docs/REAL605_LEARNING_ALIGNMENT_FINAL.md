# REAL 605 Learning Alignment — Final Assessment
### CRE Investment Committee Simulation vs Chapman MSRE Program Outcomes

**Assessment date:** 2026-09-18 | **Branch:** review/real605-frenzel-final | **HEAD:** c88e848

---

## MSRE Program Learning Outcomes Mapping

### Outcome 1: Knowledge of Real Estate
*Comprehensive knowledge of real estate principles and law relevant to development, investment and finance, and real estate as an asset class.*

| Game Mechanic | Student Action | Evidence Generated | Debrief/Assessment | Gap |
|---|---|---|---|---|
| Data Catalog (provenance-tagged sources) | Identify real vs synthetic vs derived vs simulated; understand OC parcel/assessment/CBRE/FRED provenance | Cleaned dataset; data quality manifest responses | Data honesty labels throughout app; provenance page | None significant — strongest implemented outcome |
| Deal Room underwriting | Read property-level metrics: asking price, NOI, going-in cap, occupancy, WALT, tenant concentration, debt rate, max LTV, primary risks by type | Underwriting assumptions per property | Property cards with 16 metrics; primary risk callout | None — students see real CRE underwriting factors |
| Market Explorer | Analyze cap-rate distributions by type, vacancy history, occupancy vs rent scatter, correlation matrix | Descriptive statistics; correlation observations | Market context visible during play | None |
| Geospatial View | Inspect derived features (employment density, distance to SNA/Irvine, census tract approx.) on PyDeck map | Geospatial feature table; correlation observations | Map renders during prep | PARTIAL — no forced spatial model yet, but data/hooks exist |
| Market evolution across rounds | See Treasury, employment, vacancy, NOI, cap rates change year-over-year | Round-after-round market state | Resolution reveals actual macro movement | PARTIAL — students observe evolution but don't forecast it (forecasting lab is PLANNED) |

**Status: IMPLEMENTED (strong).** This is the best-covered outcome. Students interact with real OC data context, real public market anchors, and property-level underwriting metrics that mirror actual CRE investment committee materials. The data honesty framework (REAL PUBLIC DATA / SYNTHETIC TEACHING DATA / DERIVED FEATURE / SIMULATED FUTURE) is well-implemented.

---

### Outcome 2: Problem Solving
*Effectively analyzing data, and application of economic and statistical concepts/tools in financial modeling for valuations and transaction structure.*

| Game Mechanic | Student Action | Evidence Generated | Debrief/Assessment | Gap |
|---|---|---|---|---|
| Valuation Lab | Use naive benchmarks (NOI/cap, median comp, price-per-SF); inspect baseline linear regression coefficients + train/test MAE/R²; download training data; build improved model | Model predictions CSV; forecast error vs actuals once revealed | Model leaderboard: valuation MAE, NOI MAE, Brier score, value vs naive, override contribution | PARTIAL — baseline regression + submission exist; full AVM workflow notebook is placeholder; no GB + time/geography split lab yet |
| SQL Lab | Write SQL queries against DuckDB; use example tasks; query external .duckdb file | SQL queries; derived-feature table | queries saved/executed | IMPLEMENTED for SQL; PARTIAL for broader modeling |
| Data Quality Challenge | Find/inject issues: missing values, duplicates, inconsistent labels, date formats, stale observations, outliers, leakage field | Data quality manifest responses; cleaned dataset | Manifest with 7 injected issues (DQ-01..DQ-07) | IMPLEMENTED — leakage trap is well-designed |
| Investment Decision inputs | Enter bid, LTV, NOI growth forecast, exit cap forecast, confidence, probability of loss per property | Decision journal with 6 numeric inputs per deal | Finance calculations (underwrite function) produce DSCR, debt yield, predicted NOI, predicted value, predicted levered return | IMPLEMENTED — but these are student-entered, not model-computed in MVP |
| Model skill gradient | Build better model → see it rank higher on analytics leaderboard | MAE, Brier, value-added-over-naive | Verified gradient: NAIVE AUC 0.500 → BASIC 0.896 → STRONG 0.958 → ORACLE 0.978 | IMPLEMENTED — real skill gradient exists and is verified |

**Status: PARTIAL → IMPLEMENTED (improving).** The core problem-solving loop works: student builds model → uploads → sees predictions alongside deals → bids → gets feedback on forecast accuracy. The model skill gradient is real and verified. Gaps: full AVM workflow notebook is placeholder, no guided feature-engineering exercise, no time/geography split lab, no dedicated time-series forecasting lab. These are scaffolded but not fully built.

**Key concern for Frenzel:** The on-screen/manual input path (c88e848) lets students enter forecasts directly without a model. This is pedagogically dangerous if it becomes the default path — it bypasses the "build a model" step entirely. The game must make clear this is a fallback for accessibility, not an equivalent preparation path.

---

### Outcome 3: Communication
*Effective written and verbal communication as it applies to transaction structure, real estate investment opportunities, valuation, and project development.*

| Game Mechanic | Student Action | Evidence Generated | Debrief/Assessment | Gap |
|---|---|---|---|---|
| Investment thesis (per property) | Write thesis text for each property they bid on | Thesis text stored in decision journal | **NOT surfaced in current debrief** — thesis is collected but the final_debrief.py focuses on quantitative outcomes, not the student's written reasoning | **SIGNIFICANT GAP** — thesis is collected but not used. The debrief answers 10 questions but never shows "here's what you believed vs what happened." |
| Falsification test | Write "what would prove this thesis wrong?" per property | Falsification text stored | **NOT surfaced in debrief** — same as thesis | **SIGNIFICANT GAP** — this is the most pedagogically valuable communication artifact and it's collected but not reused |
| Key assumption | Write key assumption per property | Assumption text stored | **NOT surfaced in debrief** | Gap |
| Confidence + probability of loss | Enter per-property confidence and downside probability | Numeric confidence/probability stored | Brier score computed from probability_of_downside; shown on analytics leaderboard | PARTIAL — Brier score uses the probability but confidence is not separately used |
| Decision journal | BUY/PASS + bid + LTV + forecasts + thesis + falsification per property | Complete decision record per round | Stored as history; visible in professor control submission grid | IMPLEMENTED as collection; PARTIAL as communication feedback |

**Status: PARTIAL (underdeveloped).** This is the weakest outcome. The game COLLECTS rich communication artifacts (thesis, falsification, key assumption, confidence) but does NOT FEED THEM BACK to the student in the debrief. The debrief is almost entirely quantitative: NAV, returns, MAE, Brier, channels, overrides. A student who wrote a thoughtful thesis gets no signal back about whether their reasoning was sound — only whether their numbers were right.

**Proposed fix (smallest, highest-value):** In the final debrief, for each property the student bid on, show:
- What you believed: thesis + key assumption + falsification test (as written by student)
- What you did: bid, LTV, forecasts
- What happened: actual NOI growth, actual cap rate, actual value, realized return
- What to update: did the falsification condition occur? Was the thesis right/wrong?

This directly supports communication outcome and critical thinking outcome simultaneously.

---

### Outcome 4: Critical Thinking
*Recognize the interactive decision-making environment of real estate, and how to incentivize favorable outcome from participants.*

| Game Mechanic | Student Action | Evidence Generated | Debrief/Assessment | Gap |
|---|---|---|---|---|
| Sealed-bid auction | Bid against 3 other funds without seeing their bids; highest valid bid wins; hidden reserve | Auction results: who won, at what price, vs reserve | Resolution shows winners + reserves revealed | IMPLEMENTED — core interactive decision environment |
| Capital constraint ($100M equity) | Allocate scarce capital across 4 rounds; can't bid on everything; Round 1 spending affects Rounds 2-4 | Portfolio evolution; cash/debt tracking | NAV bridge shows deal costs, reserves, interest compounding | IMPLEMENTED — capital scarcity is real and consequential |
| Human override recording | See when bid departs from own model policy; override recorded but not punished | Override delta (bid_override, ltv_override) per decision | Debrief Q4: who overrode most; Q5: did overrides help or hurt; model-vs-manager-vs-luck matrix | IMPLEMENTED — override analytics are strong |
| Scenario control (Base/Rate Shock/Growth Rebound) | Professor chooses scenario; students don't know which until reveal | Different market paths per scenario | Debrief shows which scenario played; students can reason about whether their decisions were robust to alternative futures | IMPLEMENTED — but students don't explicitly compare across scenarios (they only see the one that played) |
| Model vs manager vs luck classification | See 5 named cases: model good/followed, model good/bad override, model wrong/good override, good decision/bad outcome, bad decision/lucky outcome | Classification counts per team | Debrief shows case matrix; Q8 (good decision+bad outcome) and Q9 (bad decision+lucky outcome) directly address this | IMPLEMENTED — strongest critical-thinking feature |
| Decision quality scored ex-ante | Decision quality judged against expected outcome before realization, not just actual outcome | Decision quality score separate from outcome quality | Debrief separates outcome quality, forecast quality, risk quality, decision quality, process quality | IMPLEMENTED — this is the right design |
| Uncertainty/luck | Strong model wins 61% of seeds, not 100%; meet-ask-max-LTV wins 62% | Win rates across strategies; NAV dispersion | Balance harness evidence; debrief discusses luck vs process | IMPLEMENTED — but students don't see the distributional evidence themselves (professor sees it, students hear it in debrief) |

**Status: IMPLEMENTED (strong).** The critical thinking outcome is well-served. The sealed-bid auction + capital constraint + override recording + model-vs-manager-vs-luck classification + ex-ante decision quality scoring all work together to create the "interactive decision-making environment" the outcome calls for.

---

## What Students Actually Practice

1. **Building a valuation model** (if they prepare) — regression/ML on 2,400 historical observations, predicting fair value + NOI growth + downside probability for 120 candidates
2. **Converting analysis into policy** — setting max_bid and target_ltv per property BEFORE seeing asks or rivals
3. **Making timed investment decisions** — BUY/PASS with bid, LTV, forecasts, thesis, falsification under capital constraint
4. **Living with consequences** — Round 1 purchases stay through Round 4, revalued every year; overpaying has compounding costs
5. **Interpreting results** — reading NAV bridge, forecast error, DSCR, Brier score, override contribution, model-vs-manager-vs-luck classification
6. **Distinguishing process from outcome** — good decision/bad outcome vs bad decision/lucky outcome

---

## How Frenzel Can See Whether Learning Occurred

**Quantitative signals (already implemented):**
- Analytics leaderboard: valuation MAE, NOI MAE, Brier score, value vs naive, override contribution — ranks teams by analysis quality separately from game winner
- Model skill gradient: verified that better models get better scores (NAIVE 0.500 → STRONG 0.958 AUC)
- Override analytics: who overrode most, did overrides help or hurt
- Decision quality vs outcome quality: separate scores

**Qualitative signals (NOT yet implemented — Frenzel would need to facilitate):**
- Student theses and falsification tests are collected but not surfaced in debrief — Frenzel would need to read them from submission data and ask students to defend them
- No pre/post assessment of student ability to explain value creation, leverage, cap-rate risk, forecast error, luck vs process
- No measure of whether students can articulate WHY their decisions worked or failed beyond "I won" or "I lost"

---

## Missing

1. **Thesis/falsification feedback loop** — most important gap. Student writes thesis → game collects it → debrief never shows it back. This loses the communication outcome's most valuable artifact.
2. **Pre/post learning assessment** — no measure of whether students can explain concepts before vs after. Frenzel would need to add his own.
3. **Scenario comparison** — students only see one scenario path. They can't compare "what I did in Base Case vs what would have happened in Rate Shock." Cross-scenario reasoning is discussed but not facilitated.
4. **Guided feature engineering notebook** — placeholder exists; students don't have a structured exercise for building features.
5. **Time/geography split lab** — planned but not built; students don't get guided practice on leakage-aware validation.
6. **Time-series forecasting lab** — planned but not built; macro forecasting is observation-only.
7. **Student-authored dashboard** — the app IS a dashboard but students don't build their own.

---

## Unnecessary / Over-Engineered

1. **Strategy Card page** — currently shows `value_to_ask_ratio` as a placeholder (divides predicted_fair_value by itself). The page exists but doesn't yet add value beyond what Model Check-In shows. Could be simplified or completed.
2. **Per-property confidence + probability of loss inputs in investment decision** — these are collected but confidence isn't separately used from probability_of_downside in scoring. Brier score uses probability_of_downside. Confidence field may be redundant or needs clearer purpose.
3. **Separate "capex_need" metric in deal room** — the architecture doc (R6) flags this: deal_room.py displays "Capex need" per property that the engine never charges. The engine charges type-based capital reserves instead. This is an inconsistency that could confuse students.

---

## Top 3 Proposed Fixes (before Frenzel meeting)

### Fix 1 (P1 — high value, bounded risk): Surface thesis/falsification in debrief

**What:** In final_debrief.py, for each property the student bid on, add a section showing:
- "What you believed:" — student's thesis + key assumption + falsification test (quoted from their submission)
- "What happened:" — actual NOI growth, actual cap rate, actual value, realized return vs predicted
- "Update:" — did the falsification condition occur? Was the thesis right/wrong/uncertain?

**Why:** Directly serves communication outcome (students see their written reasoning reflected back) and critical thinking outcome (students compare their reasoning to reality). Highest-value improvement for learning.

**Risk:** Low — only adds display of existing collected data. No new data collection, no economics change.

**Effort:** ~2-4 hours. Read decision journal data, render student's own text alongside realized outcomes.

---

### Fix 2 (P1 — important clarification): Make manual/on-screen path clearly a fallback

**What:** On the investment decision page and deal room, when no model is uploaded, add a prominent note: "You are using manual inputs. Pre-class modeling is the intended REAL 605 experience. Manual inputs are available for accessibility/classroom fallback. Your results will not include model-quality scoring on the analytics leaderboard."

**Why:** c88e848 added the manual path for accessibility — good. But without clear signaling, students may treat it as equivalent to model-based play, which would undermine the "build the model before class" pedagogy. The analytics leaderboard can't score model quality without model predictions.

**Risk:** Low — only adds UI text. Doesn't remove the fallback.

**Effort:** ~30 minutes. Add st.info/st.warning boxes on relevant pages.

---

### Fix 3 (P2 — cleanup): Fix capex_need inconsistency

**What:** Either (a) relabel "Capex need" in deal_room.py to clarify it's an informational metric not charged by the engine, or (b) hide it, or (c) align the engine to charge it. The architecture doc R6 already flags this.

**Why:** A practitioner reviewing the deal room will notice "Capex need" displayed but not charged, and read it as an inconsistency. For a graduate-level CRE class, this could undermine credibility.

**Risk:** Low — labeling change only. No economics change.

**Effort:** ~30 minutes.

---

## Overall Assessment

**The game is a strong implementation of REAL 605's real-estate-knowledge and critical-thinking outcomes, a functional implementation of problem-solving, and an underdeveloped implementation of communication.**

The core design is sound: model-first → decision environment → sealed-bid auction → capital constraint → round resolution → five-channel NAV bridge → model-vs-manager-vs-luck debrief. The economics are honest and verified. The model skill gradient is real (NAIVE 0.500 → STRONG 0.958 AUC). The balance evidence shows analysis wins on average (strong model +$2.95M over weak, same policy) without dominating every seed (61% vs 62% tie with meet-ask-max-LTV is acceptable uncertainty).

**The single biggest improvement before the Frenzel meeting:** surface the student's thesis/falsification in the debrief. This closes the communication loop and turns the game from "quantitative feedback" into "reasoning feedback" — which is what distinguishes a graduate-level investment committee simulation from a trading game.

**The second biggest:** make the manual/on-screen path clearly a fallback, not an alternative preparation path. Without this, the no-model path could erode the model-first pedagogy.

**The game is ready for a pilot.** The gaps are improvements, not blockers. The pedagogy is defensible. The economics are honest. The debrief is the strongest feature and the thesis/falsification surfacing would make it stronger.
