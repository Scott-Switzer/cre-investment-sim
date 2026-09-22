# FRENZEL QA — Hard Questions and Honest Answers

### For Professor Tim Frenzel · REAL 605 · 2026-09-18

---

### Q1: Why do I need this? What does it teach that my current approach doesn't?

**A:** Your current approach likely has students build models and present findings. That teaches modeling. What it doesn't teach is what happens when those models meet a competitive market with scarce capital and uncertain outcomes — which is the actual job of a real estate investment analyst.

This simulation adds three things modeling assignments alone don't:
1. **Consequences for overpaying** — deal costs (2%), capital reserves (0.6%-1.8%/year by type), and interest above the cap rate mean buying a good building at a bad price destroys value. Students feel this across 4 rounds.
2. **Competitive pressure** — sealed-bid auction against rival funds. The same property can be a good deal at $45M and a bad deal at $52M. Students experience the difference between "my model says it's worth $50M" and "someone else is willing to pay $52M."
3. **Process vs outcome separation** — the debrief explicitly classifies decisions as good/bad regardless of what the dice did. A student who made a sound decision that got unlucky learns not to change their process. A student who made a bad decision that got lucky learns not to repeat it.

**Limitation:** If your current approach already includes competitive allocation decisions with real consequences, the marginal value is lower.

---

### Q2: Why a game? Why not just use Excel?

**A:** Excel is where they build the model. The game is where they use it under pressure. The analogy: Excel is the flight simulator's control panel; the game is the simulated flight.

A spreadsheet assignment teaches: can you build a valuation model? A simulation teaches: can you make investment decisions with that model when (a) capital is scarce, (b) rivals are bidding, (c) the market moves, and (d) you only get one shot per round?

The game also solves a practical problem: in a class of 30 students, you can't manually run a sealed-bid auction, track 4 funds' portfolios across 4 rounds, compute NAV bridges, and classify 64 decisions as good/bad model/decision/luck in real time. The software does that so you can teach.

**Limitation:** If your class is small enough to run a manual auction and you're comfortable tracking portfolios on the board, the software is less essential. But it still saves prep time and ensures consistency.

---

### Q3: What exactly is real data? What is synthetic?

**A:** Four categories, labeled throughout the app:

- **REAL PUBLIC DATA:** Orange County parcel/APN/address context, OC tax/assessment attributes (NOT transaction values — assessed value is not market value), CBRE Orange County market anchors (Q2 2026 office/industrial/multifamily cap rates + FRED 10Y Treasury), Census ACS/LODES public-data samples (cached), FRED macro series (cached public-data sample).
- **SYNTHETIC TEACHING DATA:** Property operating cases — NOI, asking price, rents, lease structure, WALT, tenant concentration, occupancy, property quality, capex need. These are calibrated to OC market conditions but are not real buildings.
- **DERIVED FEATURE:** Employment density proxy, distance to SNA/Irvine airport, census tract approximations. Computed from real public data sources but are approximations.
- **SIMULATED FUTURE:** Round-after-round outcomes — NOI growth, cap rate movement, property revaluation. Driven by a pedagogical simulator with explicit, inspectable coefficients. NOT a forecast of the actual Orange County market.

Every table and column carries provenance metadata. The provenance page documents everything.

**Limitation:** The property operating data is synthetic. A student who assumes the properties are real buildings is mistaken. The data honesty labels are present but you may want to reinforce this verbally.

---

### Q4: How does model quality actually matter?

**A:** It matters in two ways, and the game measures both separately:

1. **Analytics leaderboard:** ranks teams by valuation MAE, NOI forecast MAE, Brier score (downside calibration), value added over a naive benchmark, and override contribution. A team with a better model scores higher here regardless of whether they won the game.

2. **Game outcome:** better models create an advantage, but don't guarantee wins. At 100 seeds: strong model + disciplined bidding = $110.72M mean NAV, 61% win rate. Meet-ask-at-max-LTV (no analytics) = $109.89M, 62% win rate. These are statistically tied at 100 seeds — which is honest and desirable. Analysis wins on average (+$2.95M strong vs weak, same policy), not on every seed.

The correlation data tells the real story: selection quality (how well the model identifies good deals) correlates with NAV at +0.851. Assets acquired correlates at +0.206. Premium paid to ask correlates at -0.130.

**Limitation:** At 100 seeds, the strong model's 61% win rate vs the no-analytics strategy's 62% is a coin flip. A student who doesn't prepare can still win a given game. Over a semester with multiple games, the advantage compounds — but in a single session, luck is real.

---

### Q5: How much is luck?

**A:** Enough that a single game doesn't settle anything, but not so much that preparation is pointless.

The game has seeded randomness in NOI growth (N(0, 1.5%) per property per year, clipped to [-10%, +15%]) and cap rate (N(0, 0.05%), clipped to [3%, 12%]). The same seed replays the same game exactly — so if you run the same decisions twice, you get the same result. But across seeds, outcomes vary.

Evidence:
- Strong model wins 61% of 100 seeds, not 100%. The other 39% of the time, a worse strategy wins.
- Meet-ask-at-max-LTV (no analytics) wins 62% — statistically tied with the strong model at 100 seeds.
- The dispersion matters: mean NAV for strong model is $110.72M, but individual seeds range widely.

The debrief is designed around this: questions 8 (good decision, bad outcome) and 9 (bad decision, lucky outcome) explicitly address luck. The model-vs-manager-vs-luck matrix shows cases where the right process got unlucky and the wrong process got paid.

**Limitation:** In a single-class-session pilot with one game, luck will be visible and obvious. Students (and you) may overweight it. Multiple sessions would amortize this, but a pilot is one session.

---

### Q6: Can a dumb strategy win?

**A:** Yes, occasionally. And that's by design, not a bug.

At 100 seeds:
- Meet-ask-at-max-LTV (no analytics): 62% win rate, $109.89M mean NAV
- Strong model, disciplined: 61% win rate, $110.72M mean NAV
- 5% over ask at max LTV (aggressive, medium model): 50% win rate, $104.39M
- Never bid: 0% win rate, $100.00M

The no-analytics strategy wins more often than the strong model in a 100-seed sample. But:
- Its mean NAV ($109.89M) is below the strong model's ($110.72M) — it wins more often but less impressively.
- The correlation data shows selection quality drives NAV (r=+0.851), not aggression (r=+0.206 for assets, r=-0.130 for premium).
- Over many seeds, analysis wins on average. Over one seed, luck matters.

This is the honest outcome. If the strong model won 100% of seeds, the game would be teaching "modeling always wins" — which is false in real estate and wouldn't be a good lesson. The uncertainty is a feature: it forces the debrief conversation about process vs outcome.

**Limitation:** In a pilot with one game, a student who didn't prepare might win and conclude "my gut was better than their model." You'd need to debrief this carefully. The analytics leaderboard helps — it shows the prepared student's model was better even if they didn't win the game.

---

### Q7: What if students don't prepare?

**A:** They can still play using the on-screen/manual input path (added in the most recent commit). They enter bid, LTV, forecasts, thesis, and falsification directly on the decision page — no CSV upload required.

But two things change:
1. **They miss the modeling practice.** The REAL 605 learning outcome is "build a model, then use it." The manual path skips step 1.
2. **They get no model-quality scoring.** The analytics leaderboard measures model MAE, Brier score, value vs naive — all of which require model predictions. A manual-input student gets game scoring (NAV, returns) but not analytics scoring.

The manual path is intended as an accessibility fallback — for students who can't build a model, or for a last-minute participant. It should NOT be presented as an equivalent preparation path.

**Limitation:** Without clear signaling, students may treat the manual path as "good enough" and skip modeling. The fix is UI text making the fallback status explicit — small change, high value.

---

### Q8: How long does class take?

**A:** Two presets are configured:

- **QUICK CLASS:** 5 min briefing + 6 min practice + 9 min × 4 rounds + 18 min debrief = ~65 minutes total
- **EXTENDED CLASS:** 5 min briefing + 8 min practice + 12 min × 6 rounds + 25 min debrief = ~110 minutes total

The Frenzel demo script targets 10 minutes for a walkthrough (not full play). A full class session is one class period.

The round timing is advisory only — there are no hard timers in the MVP. The professor opens, locks, and advances rounds manually. This means you control the pace, but also means you need to manage it.

**Limitation:** No hard timers means a class can run long if students deliberate. You'd need to manage time verbally. Timers are planned but not implemented.

---

### Q9: How do teams work? How many students?

**A:** The game supports both team and individual modes.

- **Team mode:** students join with a display name, pick or create a fund, upload a shared model. Multiple students can be in one fund. The game tracks per-fund state.
- **Individual mode:** each student is their own fund.

Minimum: 2 funds (1 human + 1 bot, or 2 humans). Demo mode runs 4 funds (1 human + 3 bots). The architecture supports 70+ concurrent players (load-tested in a prior gate).

For a pilot, I'd suggest teams of 2-4 students per fund, with 4-8 funds in a session. The bots fill empty seats if you have fewer human teams.

**Limitation:** The team mode is implemented in the architecture but the current demo is single-human + bots. Multi-human-team classroom play needs testing at scale before a large pilot.

---

### Q10: What does the professor control?

**A:** Everything needed to run the class:

- **Session creation:** scenario (Base Case / Rate Shock / Growth Rebound), starting equity, total rounds
- **Model check-in:** view which teams have uploaded, validation status
- **Round lifecycle:** open round, lock round (prevents silent edits), advance to next round, reveal outcome
- **Timer:** advisory timing display (no hard timer in MVP)
- **Leaderboard:** team standings (NAV, return, cash, debt, assets, rank) + analytics leaderboard (MAE, Brier, value vs naive, overrides)
- **Export:** scores CSV for grading
- **Bigscreen:** projection surface for lobby, round, reveal, standings, finale — no controls, just display
- **Reset/recovery:** reset demo, end game early
- **Demo mode:** auto-advance button for solo review without a full class

The professor can pause by simply not advancing. The professor can recover from a late student by locking the round late (submissions still accepted until lock). The professor can see submission completeness on the professor control page.

**Limitation:** No hard timer means you enforce time limits verbally. No built-in "late student" recovery beyond late submission before lock. No automated grading — you'd use the exported CSV.

---

### Q11: How could this be graded?

**A:** Four possible components, using data the game already captures:

1. **Model quality (analytics leaderboard):** valuation MAE, NOI MAE, Brier score, value vs naive. Objective, comparable across students. Weight: 30-40% of grade?
2. **Decision quality (debrief):** decision quality score (ex-ante, against expected outcome). Separates process from luck. Weight: 20-30%?
3. **Communication (thesis/falsification):** currently collected but not auto-scored. Would need your rubric. Weight: 20-30%?
4. **Game outcome (NAV):** least recommended as a grade component, because luck matters. A student who made good decisions can lose. Weight: 0-10% at most, if any.

The export CSV gives you per-team: NAV, return, cash, debt, assets, rank, valuation MAE, NOI MAE, Brier score, value vs naive, override count, override contribution, decision quality, outcome quality, forecast quality, risk quality, process quality.

**Limitation:** No auto-grading rubric is built. You'd define your own weights and use the exported data. The communication component (thesis/falsification) needs manual review unless you build an auto-scoring approach — which I would NOT recommend, because thesis quality is inherently subjective.

---

### Q12: What would you measure in a pilot?

**A:** Lightweight, practical measures:

1. **Pre-game:** student self-reported confidence in valuation modeling (1-5 scale). Optional: a short pre-test on CRE valuation concepts.
2. **During game:** model submission rate (% of students who upload a model vs use manual path), decision completion rate (% of properties decided per round), override rate.
3. **Post-game:** student self-reported ability to explain: value creation sources, leverage effect, cap-rate risk, forecast error, luck vs process (1-5 scale each). Optional: a short post-test with the same concepts.
4. **Professor observation:** classroom flow smoothness, student engagement, debrief discussion quality, technical issues.

Success criteria:
- ≥80% of students upload a model (not using manual fallback)
- ≥80% of students can articulate why their decisions worked or failed (post-game self-report ≥4/5)
- Classroom flow works without professor intervention on software
- Debrief generates discussion where students distinguish model quality, decision quality, and luck
- You give specific, actionable feedback on what to change

**Limitation:** Self-reported measures are weak. A pre/post test with actual concept questions would be stronger but adds friction. For a first pilot, self-report + your observation is enough.

---

### Q13: What would you change after one class?

**A:** Based on what I know now, likely changes after a pilot:

1. **Surface thesis/falsification in debrief** — highest priority. Close the communication loop.
2. **Clarify manual path as fallback** — UI text, so students don't treat it as equivalent to modeling.
3. **Add a pre/post assessment instrument** — even a short one, to measure learning.
4. **Fix capex_need inconsistency** — relabel or align with engine.
5. ** Possibly add cross-scenario comparison** — if students and you find the single-scenario limitation salient.
6. ** Possibly add hard timers** — if classroom time management is a problem.

I would NOT change the economics (deal costs, capital reserves, debt rates, reserve prices, property distributions) without strong evidence of a pedagogical failure. The balance evidence supports the current coefficients.

---

### Q14: Can I trust the economics?

**A:** Yes, for a teaching simulation. Here's why:

1. **Everything is explicit and inspectable.** All economic coefficients are declared in one place (src/game/adjudicator.py, docs/GAME_ECONOMICS.md). No LLM, no black box, no opaque scoring.
2. **The NAV identity reconciles to machine precision.** NAV = cash + property values - debt. Every dollar of change is one of five channels: value change, NOI income, interest, deal costs, capital reserves. Verified in tests.
3. **The coefficients are real CRE economics:** 2% deal costs (legal, diligence, title, financing), capital reserves by property type (TI, leasing commissions, replacement reserves), interest-only debt at the property's rate, cap rate movement within plausible ranges, NOI growth with a tight-vacancy bonus.
4. **The balance is tested, not asserted.** 100-seed analysis with multiple strategies shows the coefficients produce the intended lesson (analysis wins on average, aggression doesn't dominate) without being tuned to force a specific winner.
5. **The simulator is transparent about being synthetic.** The data honesty labels and provenance page make clear these are teaching data, not real market predictions.

**Limitation:** These are simplified CRE economics. No amortization, no loan maturity, no tenant turnover modeling, no capital expenditure beyond reserves, no redevelopment/redevelopment risk, no market liquidity / exit risk beyond the cap rate. For a graduate course, you may want to discuss these simplifications explicitly — they're pedagogically acceptable simplifications, not hidden assumptions.

---

### Q15: What data is real? (Professor-facing summary)

**A:** From the provenance page and data catalog:

**Real public data (cached samples):**
- Orange County parcel/APN/address context
- OC tax/assessment attributes (NOT transaction values)
- CBRE Orange County Q2 2026 market anchors (office, industrial, multifamily cap rates + vacancy)
- FRED 10-Year Treasury rate (cached public-data sample)
- Census ACS/LODES public-data samples (cached)

**Synthetic teaching data (calibrated to OC conditions):**
- Property operating cases: NOI, asking price, going-in cap, occupancy, WALT, rents, lease structure, tenant concentration, property quality, capex need
- Round outcomes: NOI growth, cap rate movement, property revaluation

**Derived features:**
- Employment density proxy (from cached LODES-style data)
- Distance to SNA/Irvine
- Census tract approximations

**The app does NOT claim:**
- These properties are real buildings you could buy
- The simulation predicts the actual Orange County market
- Synthetic future outcomes are historical facts

**Limitation:** The OC public data is cached (not live-retrieved in the MVP). The Census/FRED data is a sample, not the full series. For a pilot, this is fine — the point is the analytical process, not the data freshness.
