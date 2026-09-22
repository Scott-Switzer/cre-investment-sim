# FRENZEL PITCH DECK — 7 Slides

**CRE Investment Committee Simulation — REAL 605 Pilot**
Scott Switzer · Chapman University · 2026-09-18
**Target:** 5-7 minute presentation to Professor Tim Frenzel

---

## SLIDE 1 — From Model to Investment Decision

**Title:** REAL 605 CRE Investment Committee Simulation

**Headline:** Students build the analytics before class. The simulation forces them to use it under capital constraints.

**Body:**
- One sentence: This is model-first, not game-first. Students build the model before class; the game is only the decision environment.
- The flow: DATA → MODEL → BID/PASS → PORTFOLIO → FEEDBACK → DEBRIEF
- Four funds, $100M equity each, 4 rounds, sealed-bid auction, 16 properties total
- The debrief separates outcome quality, forecast quality, risk discipline, decision quality, and process quality

**Speaker notes:**
Open with the investment-committee problem, not a feature list. "You are an investment team at a small Orange County CRE fund. It is March 31, 2024. The committee has authorized you to deploy up to $150M of equity across a pipeline of acquisition candidates. One round is one quarter. Your job is to decide, property by property, which ones to buy and at what price and leverage, using only the data available as of today."

Emphasize: "They build the model before class — Excel, Python, R, XGBoost, whatever. The app does not build it for them and never will. The app is the decision environment that makes the modeling matter."

**Visual instruction:** Simple horizontal flow diagram: DATA (database icon) → MODEL (code/model icon) → BID/PASS (gavel/checkmark icon) → PORTFOLIO (building stack icon) → FEEDBACK (chart icon) → DEBRIEF (conversation icon). Arrow flow left to right.

**Data/chart values:** None on this slide. It's the framing slide.

---

## SLIDE 2 — Why It Fits REAL 605

**Title:** Why This Fits REAL 605

**Headline:** Maps to the MSRE program's four learning outcomes — and to Module 1 topics.

**Body:**

| MSRE Program Outcome | Game Mechanic | What the Student Practices |
|---|---|---|
| Knowledge of Real Estate | Data Catalog, Deal Room underwriting, Market Explorer, Geospatial View | Real OC data context, property-level CRE underwriting factors, market analysis |
| Problem Solving (data/econ/stats in financial modeling) | Valuation Lab, SQL Lab, Data Quality Challenge, model submission | Build a model, submit predictions, see forecast accuracy revealed, compare to naive benchmarks |
| Communication (transaction structure, investment opportunities, valuation) | Investment thesis + falsification per property, debrief presentation | Write investment theses, defend decisions, interpret results for a committee |
| Critical Thinking (interactive decision-making environment) | Sealed-bid auction, capital constraint, override recording, model-vs-manager-vs-luck classification | Make timed decisions under competitive pressure with scarce capital, then separate process from luck |

Module 1 topics covered: Business Problem Definition, Data Sources and Data Types, Data Cleaning, Descriptive Statistics, Data Visualization, Feature Engineering, Linear Regression, SQL Fundamentals, Building BI Dashboards — all IMPLEMENTED or PARTIAL.

**Speaker notes:**
"Real-estate knowledge comes from working with actual CRE underwriting factors — cap rate, NOI, WALT, tenant concentration, debt rate, LTV, DSCR — using real OC data context and real public market anchors. Problem solving comes from building a model and seeing whether it was right. Communication comes from writing investment theses and defending them in the debrief. Critical thinking comes from the sealed-bid auction — you're making decisions under competitive pressure with scarce capital, and then the debrief forces you to separate process from luck."

Be honest: "The communication outcome is the weakest right now — the game collects student theses and falsification tests but the debrief doesn't yet surface them back to the student. That's the #1 improvement I'd make before a pilot."

**Visual instruction:** 2×2 matrix with the four MSRE outcomes as quadrants, each with a one-line game mechanic mapping. Clean table format.

**Data/chart values:** None. Use the mapping table as the content.

---

## SLIDE 3 — What Students Actually Do

**Title:** What Students Actually Do

**Headline:** Model-first. The pre-class work is the learning. The class is where it gets tested.

**Body:**

**Before class (the learning):**
- Download student packet: historical_training.csv (2,400 observations, 400 OC properties, 6 vintages, outcomes included) + game_candidates.csv (120 properties, outcomes withheld)
- Build a model externally: Excel, Python, R, gradient boosting — any tool
- Predict for all 120 candidates: fair value, NOI growth, downside probability, max bid, target LTV
- Upload predictions CSV at Model Check-In

**In class (the test):**
- Rules briefing (5 min)
- Practice round — not scored (5-8 min)
- 4 scored rounds — 8 min each, one simulated year per round
- Each round: see 4 properties, decide BUY/PASS with bid + LTV + forecasts + thesis + falsification, lock, get feedback
- Sealed-bid auction against rival funds; capital is scarce ($100M equity)

**After (the debrief):**
- Final standings: who won (NAV), who analyzed best (MAE, Brier, value vs naive)
- 10 debrief questions answered from recorded history
- Model vs manager vs luck classification
- 5-channel NAV bridge: value change + NOI - interest - deal costs - reserves = NAV change

**Speaker notes:**
"The pre-class work is where the learning happens — that's where they build the model, engineer features, clean data, write SQL. The class session is where they use it under pressure. The debrief is where they learn whether their process was sound, separate from whether they got lucky."

Walk the timeline: "5 minutes of rules, 5-8 minutes of practice, four scored rounds of 8 minutes with 2 minutes of feedback between each, and a 15-20 minute debrief. That's a class period."

**Visual instruction:** Three-column timeline: BEFORE CLASS (hourglass icon, list of prep steps) → DURING CLASS (clock icon, round timeline) → AFTER (chat bubble icon, debrief elements). Horizontal across the slide.

**Data/chart values:** None. Timeline is the content.

---

## SLIDE 4 — The Analytics Matter

**Title:** The Analytics Matter

**Headline:** Better models create an advantage — but don't guarantee every outcome. That's the honest lesson.

**Body:**

**Model skill gradient (verified):**
- NAIVE ("worth the asking price"): AUC 0.500 — coin flip, cannot rank deals at all
- BASIC (ordinary OLS): AUC 0.896
- STRONG (uses CRE valuation structure): AUC 0.958
- ORACLE (knows the outcome identity): AUC 0.978

This is a real spread. A student who builds a structural model gets ~60% separation on "is this a good deal" vs a student who just reports the ask.

**Strategy balance (100 seeds, 3 bot funds + 1 human):**

| Human Strategy | Mean NAV | Win Rate | Assets | Premium to Ask |
|---|---|---|---|---|
| Never bids | $100.00M | 0% | 0.0 | — |
| Weak model, disciplined | $107.77M | 47% | 4.0 | -0.09% |
| Strong model, disciplined | $110.72M | 61% | 4.0 | -0.25% |
| Meets ask at max LTV (no analytics) | $109.89M | 62% | 7.1 | -0.03% |
| 5% over ask at max LTV (aggressive) | $104.39M | 50% | 9.6 | +4.84% |

**Key results:**
- Analysis effect (strong - weak, same policy): +$2.95M
- Deployment effect (aggressive - disciplined, same model): -$4.96M
- corr(NAV, selection quality) = +0.851 — what drives NAV is picking good deals, not buying more
- corr(NAV, assets acquired) = +0.206 — deploying more does not dominate

**Speaker notes:**
"Here's the honest result: a strong model with disciplined bidding wins 61% of 100 seeds. A strategy with no analytics — just meet the ask at max leverage — wins 62%. At 100 seeds, those are statistically tied. That's not a defect — it's the honest outcome. Analysis wins on average (+$2.95M over a weak model, same policy), not on every seed. Over a semester with multiple games, the advantage compounds. In one game, luck is real — and the debrief is designed to separate process from luck."

"The correlation data is the real story: selection quality — how well your model identifies good deals — correlates with NAV at +0.851. Buying more assets correlates at +0.206. Paying above the ask correlates at -0.130. The money comes from buying the right assets, not from buying more assets or leveraging harder."

**Visual instruction:** Left side: model skill gradient as a simple bar chart (NAIVE 0.500, BASIC 0.896, STRONG 0.958, ORACLE 0.978). Right side: balance table with the 5 strategies. Keep it clean.

**Data/chart values:** Use the exact numbers above. AUC values: 0.500, 0.896, 0.958, 0.978. Mean NAVs: $100.00M, $107.77M, $110.72M, $109.89M, $104.39M. Win rates: 0%, 47%, 61%, 62%, 50%. Correlations: r(NAV,selQ)=+0.851, r(NAV,assets)=+0.206, r(NAV,premium)=-0.130.

---

## SLIDE 5 — Real Estate Economics, Not Arcade Scoring

**Title:** Real Estate Economics, Not Arcade Scoring

**Headline:** Every dollar of NAV change comes from one of five explicit channels. No opaque LLM scoring.

**Body:**

**The NAV bridge (verified to machine precision):**
```
NAV = cash + property values - debt

NAV - starting equity =
    + (property values - what you paid)     ← value channel (appreciation)
    + NOI income received                    ← income
    - interest paid                          ← cost of debt
    - deal costs paid                        ← cost of acquisition (2% of price)
    - capital reserves funded                ← cost of ownership (0.6%-1.8%/year by type)
```

**The economics are real CRE:**
- Deal costs: 2.0% of purchase price — legal, diligence, title, financing. Paid in cash on closing. NOT financed by lenders.
- Capital reserves: Industrial 0.6%, Office 1.8%, Multifamily 1.0%, Retail 1.5% of value per year — TI, leasing commissions, replacement reserves. Scales with the asset, not the loan.
- Debt: interest-only at the property's rate. No amortization in MVP.
- NOI growth: 2.0% base + 1.0% tight-vacancy bonus (vacancy ≤ 8%) + N(0, 1.5%) noise, clipped [-10%, +15%]
- Cap rate: market cap for type + N(0, 0.05%) noise, clipped [3%, 12%]

**Two separate leaderboards (deliberately not blended):**
1. Game leaderboard: ending NAV, cumulative return, cash, debt, portfolio LTV, assets acquired
2. Analytics leaderboard: valuation MAE, NOI forecast MAE, Brier score (downside calibration), value added over naive benchmark, override contribution

**Why this matters:** A property bought near the asking price and financed at max LTV roughly earns its cost of debt. The money is made by buying assets your model says are cheap — not by buying the most assets. The 5-channel bridge makes this visible and verifiable.

**Speaker notes:**
"This is the slide that addresses the 'is this just a game' concern. Every number is an explicit, inspectable CRE economic rule. The NAV bridge reconciles to machine precision — there's no sixth term, no opaque score. Deal costs, capital reserves, interest, NOI growth, cap rate movement — all real CRE economics, all declared in one place, all verified by tests."

"The two leaderboards are deliberate. A good model with poor discipline can lose. A mediocre model with excellent discipline can win. That separation is the point — and it's measurable."

**Visual instruction:** The NAV bridge as a waterfall chart (value change up, NOI up, interest down, deal costs down, reserves down, ending at NAV change). Five bars, clearly labeled. Right side: two leaderboard boxes side by side with labels "GAME LEADERBOARD" and "ANALYTICS LEADERBOARD."

**Data/chart values:** The waterfall values are per-fund (computed during play). The structure is what matters on this slide. Mention the capital reserve rates by type: Industrial 0.6%, Office 1.8%, Multifamily 1.0%, Retail 1.5%. Deal cost rate: 2.0%. NOI growth base: 2.0%. Cap rate noise sigma: 0.05%.

---

## SLIDE 6 — What the Professor Gets

**Title:** What the Professor Gets

**Headline:** The professor runs the discussion. The software runs the market.

**Body:**

**Professor Control:**
- Session creation: scenario (Base Case / Rate Shock / Growth Rebound), starting equity, total rounds
- Model check-in: see which teams have uploaded, validation status
- Round lifecycle: open round, lock round (prevents silent edits), advance, reveal outcome
- Timer: advisory timing display (no hard timer in MVP — you control pace verbally)
- Leaderboard: team standings + analytics leaderboard, side by side
- Export: scores CSV for grading
- Reset/recovery: reset demo, end game early
- Demo mode: auto-advance for solo review without a full class

**Bigscreen (projection for the room):**
- Lobby code display
- Live timer
- Round status
- Winners and standings
- Finale wall with winner + best model + best decisions + most overrides + leverage story

**Student-facing surfaces:**
- Deal Room: 16 metrics per property, underwriting drawer with DSCR/debt yield/predicted value/levered return
- YOUR MODEL panel: private per-fund view of their own predictions — no other team sees it
- Investment Decision: buy/pass, bid, LTV, forecasts, thesis, falsification, lock
- Results/Debrief: per-property actual vs predicted, 5-component score, 10 questions, model-vs-manager-vs-luck matrix

**What the professor does NOT have to do:**
- Manually run a sealed-bid auction
- Track 4 funds' portfolios across 4 rounds
- Compute NAV bridges
- Classify 64 decisions as good/bad model/decision/luck
- The software does all of that. The professor teaches.

**Speaker notes:**
"This is the practical slide. The professor controls the clock, sees submission completeness, advances rounds, and exports scores. The software runs the auction, tracks portfolios, computes NAV, and classifies decisions. You don't debug software in class — you teach from the debrief."

"The Bigscreen is for projection — lobby code, timer, winners, standings, finale. No controls on the Bigscreen, just display, so students can't accidentally change anything from the projector."

**Visual instruction:** Two-column layout. Left: "Professor Controls" list with checkmarks. Right: "Student Surfaces" list with the key pages. Center: "The software runs the market" arrow connecting them.

**Data/chart values:** None. Feature list is the content.

---

## SLIDE 7 — Proposed Pilot

**Title:** Proposed Pilot

**Headline:** One REAL 605 class session. Collect feedback. Measure learning. Revise after.

**Body:**

**The ask:**
"Would you be willing to pilot this in REAL 605 and tell me what needs to change for it to teach the course the way you want?"

Not: "Will you adopt my software?"

**Pilot design:**
- One class session, one game
- Teams of 2-4 students per fund, 4-8 funds
- Model-first: students build model before class (the intended experience)
- Manual fallback available for accessibility (clearly labeled as fallback)
- You run the debrief from the final_debrief screen — all 10 questions answered on screen

**What I'm measuring:**
- Pre-game: student self-reported confidence in valuation modeling (1-5)
- During: model submission rate (% uploading model vs manual path), decision completion, override rate
- Post-game: student self-reported ability to explain value creation, leverage, cap-rate risk, forecast error, luck vs process (1-5 each)
- Your observation: classroom flow, engagement, debrief quality, technical issues

**Pilot success criteria:**
- ≥80% of students upload a model (not using manual fallback as default)
- ≥80% of students can articulate why their decisions worked or failed (post-game self-report ≥4/5)
- Classroom flow works without professor intervention on software
- Debrief generates discussion where students distinguish model quality, decision quality, and luck
- You give specific, actionable feedback on what to change

**What I'd likely change after one pilot:**
1. Surface thesis/falsification in debrief (highest priority)
2. Clarify manual path as fallback (UI text)
3. Add pre/post assessment instrument
4. Fix capex_need inconsistency
5. Possibly add cross-scenario comparison
6. Possibly add hard timers

**What I would NOT change without strong evidence:**
- Economic coefficients (deal costs, capital reserves, debt rates, reserve prices, property distributions)
- The core game loop (briefing → decision → lock → reveal → debrief)
- The two-leaderboard design (game + analytics separate)

**Speaker notes:**
"Here's the ask: pilot this in one REAL 605 session. I'm not asking for permanent adoption tomorrow. I'm asking whether this teaches the right things, and what you'd want changed before a second pilot."

"Success looks like: students can explain why their decisions worked or failed, model quality measurably affects decisions, classroom flow works without you debugging software, and the debrief generates useful discussion. And — most importantly — you give me specific, actionable feedback on what to change."

End with: "I want your feedback on whether this teaches the right things, not just whether the software works."

**Visual instruction:** Simple three-step roadmap: PILOT (one session, feedback) → REVISE (fix gaps, add measures) → SECOND PILOT (if warranted). Downward arrow showing the economic coefficients and core loop are protected from change without strong evidence.

**Data/chart values:** None. The pilot design is the content.

---

## APPENDIX — Data Values Reference (for speaker preparation)

**Model skill gradient (from model_skill_gradient.py):**
- NAIVE level MAE: 1.552, decision AUC: 0.500
- BASIC level MAE: 0.875, decision AUC: 0.896
- STRONG level MAE: 0.651, decision AUC: 0.958
- ORACLE level MAE: 0.405, decision AUC: 0.978, R²: 0.999

**Balance harness (100 seeds, Experiment C):**
- Strong model disciplined: $110.72M mean NAV, 61% win rate, 90% top-2, 4.0 assets, -0.25% premium to ask, 1.00 valMAE
- Medium model disciplined: $109.35M, 56% win rate, 86% top-2, 4.0 assets, -0.17% premium, 1.53 valMAE
- Weak model disciplined: $107.77M, 47% win rate, 73% top-2, 4.0 assets, -0.09% premium, 3.38 valMAE
- Meets ask at max LTV: $109.89M, 62% win rate, 89% top-2, 7.1 assets, -0.03% premium, 1.53 valMAE
- 5% over ask at max LTV: $104.39M, 50% win rate, 68% top-2, 9.6 assets, +4.84% premium, 1.53 valMAE
- Never bids: $100.00M, 0% win rate, 10% top-2, 0.0 assets

**Correlations (Experiment C):**
- corr(NAV, selection quality) = +0.851
- corr(NAV, assets acquired) = +0.206
- corr(NAV, gross LTV) = +0.287
- corr(NAV, valuation MAE) = +0.112
- corr(NAV, premium paid to ask) = -0.130

**Effects:**
- Analysis effect (strong - weak, same policy) = +$2.95M
- Deployment effect (aggressive - disciplined, same model) = -$4.96M

**Capital reserve rates by type:**
- Industrial: 0.6%/year
- Office: 1.8%/year
- Multifamily: 1.0%/year
- Retail: 1.5%/year

**Deal cost rate:** 2.0% of purchase price

**NOI growth parameters:**
- Base: 2.0%/year
- Tight vacancy bonus: +1.0%/year (vacancy ≤ 8%)
- Sigma: 1.5%
- Bounds: [-10%, +15%]

**Cap rate parameters:**
- Noise sigma: 0.05%
- Bounds: [3%, 12%]

**Scenarios:**
- Base Case: no delta
- Rate Shock: policy +2.00pp, growth -1.00pp
- Growth Rebound: policy -0.50pp, growth +1.50pp

---

*End of pitch deck.*
