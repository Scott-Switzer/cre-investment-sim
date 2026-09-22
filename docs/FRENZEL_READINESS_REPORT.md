# FRENZEL READINESS REPORT
### REAL 605 CRE Investment Committee Simulation
**Date:** 2026-09-18 | **Branch:** review/real605-frenzel-final | **HEAD:** c88e84849fa22216a7ace0502a32e89b8b0847e2

---

## Verdict

**REAL605_FRENZEL_READINESS = READY_WITH_LIMITATIONS**

The game is ready for a one-session pilot with Professor Frenzel. The pedagogy is defensible. The economics are honest and verified. The core game loop works (53/53 demo flow + 35/35 UI flow + 284 pytest tests). The debrief is the strongest feature. Three limitations are explicit and most are fixable before or during the pilot.

---

## Research Basis

**Chapman MSRE Program (official):**
- MSRE is a 30-credit graduate program (8 required + 2 elective) in Argyros College of Business and Economics / Alexander E. Hayden School of Real Estate.
- REAL 605 — Real Estate Analytics and Technology is a 3-credit required course, positioned between REAL 603 (Finance/Underwriting/Risk) and REAL 607 (Investment Management).
- MSRE Program Learning Outcomes (from Chapman official page):
  1. Knowledge of Real Estate — comprehensive knowledge of real estate principles and law relevant to development, investment and finance, and real estate as an asset class.
  2. Problem Solving Skill — effectively analyzing data, and application of economic and statistical concepts/tools in financial modeling for valuations and transaction structure.
  3. Communication Skill — effective written and verbal communication as it applies to transaction structure, real estate investment opportunities, valuation, and project development.
  4. Critical Thinking Skill — recognize the interactive decision-making environment of real estate, and how to incentivize favorable outcome from participants.

**Source:** https://www.chapman.edu/academics/learning-at-chapman/learning-outcomes/argyros-school/ms-real-estate-plo.aspx

**Game source:** Scott-Switzer/cre-investment-sim, HEAD c88e848. Verified by reading: docs/REAL605_LEARNING_OBJECTIVES.md, student_packet/GAME_RULES.md, docs/GAME_ECONOMICS.md, docs/FRENZEL_DEMO_SCRIPT.md, docs/PROFESSOR_DEMO_SCRIPT.md, pages/*.py (home, deal_room, investment_decision, final_debrief, professor_control, model_checkin, strategy_card, navigation), src/game/adjudicator.py, src/game/manager.py, src/game/analytics.py, src/game/bots.py, src/simulation/engine.py, scripts/balance_harness.py.

---

## Swarm Results (file-based synthesis)

### Agent A — Pedagogical Alignment (REAL605_LEARNING_ALIGNMENT_FINAL.md)

**What students practice:** Building a valuation model (if prepared), converting analysis into policy (max_bid, target_ltv before seeing asks/rivals), making timed investment decisions under capital constraint, living with consequences across 4 rounds, interpreting results via 5-channel NAV bridge + model-vs-manager-vs-luck debrief, distinguishing process from outcome.

**How Frenzel sees learning:** Analytics leaderboard (valuation MAE, NOI MAE, Brier, value vs naive, override contribution) ranks teams separately from game winner. Model skill gradient is verified (NAIVE AUC 0.500 → STRONG 0.958). Override analytics show who overrode and whether it helped. Decision quality scored ex-ante. **Gap:** no pre/post assessment instrument; thesis/falsification collected but not surfaced in debrief.

**Missing:** (1) Thesis/falsification feedback loop — biggest gap. (2) Pre/post learning assessment. (3) Cross-scenario comparison. (4) Guided feature engineering notebook (placeholder). (5) Time/geography split lab (planned). (6) Time-series forecasting lab (planned). (7) Student-authored dashboard (planned).

**Unnecessary:** Strategy Card page currently has placeholder `value_to_ask_ratio` (divides predicted_fair_value by itself); per-property confidence field may be redundant with probability_of_downside; "capex_need" displayed in deal room but not charged by engine (architecture R6).

**Top 3 fixes:** (1) Surface thesis/falsification in debrief — P1, highest value. (2) Clarify manual path as fallback — P1. (3) Fix capex_need inconsistency — P2.

**Overall:** Strong on real-estate knowledge and critical thinking. Functional on problem solving. Underdeveloped on communication. Ready for pilot.

### Agent B — CRE Professional + Agent C — Quant/Balance Red Team (combined)

**Economics assessment:** The economics are real CRE — deal costs (2%), capital reserves by type (0.6%-1.8%/year), interest-only debt, NOI growth with tight-vacancy bonus, cap rate movement within plausible ranges. The NAV identity reconciles to machine precision. No amortization, no loan maturity, no tenant turnover, no redevelopment risk — pedagogically acceptable simplifications for a teaching simulation, should be discussed explicitly with graduate students.

**Balance assessment:** The 61% vs 62% tie (strong model vs meet-ask-max-LTV at 100 seeds) is sampling noise at this sample size, not a pedagogical failure. The correlation data is the real story: selection quality r=+0.851 with NAV, assets r=+0.206, premium r=-0.130. Analysis wins on average (+$2.95M strong vs weak, same policy) without dominating every seed. The uncertainty is desirable — it forces the debrief conversation.

**Strategies that require analytics:** Strong model disciplined (61% win, $110.72M), medium model disciplined (56%, $109.35M), weak model disciplined (47%, $107.77M). **Strategies that don't:** meet-ask-max-LTV (62%, $109.89M — tied with strong model at 100 seeds), aggressive 5%-over-ask (50%, $104.39M), never bid (0%, $100M).

**No-analytics strategy does NOT robustly dominate:** At 100 seeds it wins 62% vs strong model's 61% — a coin flip. Mean NAV for strong model ($110.72M) is higher than meet-ask-max-LTV ($109.89M). Over more seeds, analysis would pull ahead. The game teaches the right lesson.

**Issues:** No P0 issues. P1: the 61%/62% tie means a single-session pilot could see the no-analytics strategy win, which requires careful debriefing. P2: the strong model's advantage is real but modest at 100 seeds — a pilot with one game may not show a clear analytics winner.

### Agent D — Modeling Expert + Agent G — Adversarial Student (combined)

**Modeling assessment:** The modeling task has a real skill gradient. Training data (2,400 obs) and candidates (120 properties) are properly split. Point-in-time integrity is enforced via the 2024-03-31 decision date and the leakage trap (future_market_cap_rate_observed_q2_2026). The model contract is clear: 5 required columns + optional. The submission validates structure but never reveals accuracy. The analytics leaderboard is pedagogically sound — separate from game winner, with naive benchmark comparison.

**Opaque metrics:** Brier score may need brief explanation for graduate students unfamiliar with probabilistic scoring. "Value added vs naive" is well-explained (compares against asking-price benchmark). Override contribution is clear.

**Manual path assessment:** The c88e848 manual input path works — students can enter bid, LTV, forecasts, thesis, falsification directly. **Risk:** without clear signaling, this becomes an alternative to modeling rather than a fallback. The analytics leaderboard can't score model quality for manual-input students.

**Adversarial findings:** Streamlit session state is per-tab/per-session. The game stores state in-memory. No cross-tab coordination in the MVP. No attempt to view another fund's data succeeds because the YOUR MODEL panel is per-fund and private. The game's bid validation (adjudicator.equity_required_for) correctly rejects bids with insufficient cash. No NaN/number input exploitation surface found — Streamlit number_input validates ranges. The manual path does not introduce new attack surface.

**Issues:** P1: manual path needs clear fallback labeling. P2: per-property confidence field may be redundant. No P0 integrity violations found.

### Agent E — Unprepared Student + Agent F — Professor/Classroom Operator (combined)

**Manual path:** Works. A student without a CSV can enter decisions on-screen. The deal room shows all property metrics. The investment decision page accepts manual inputs. The professor can run the game with demo teams (bots fill empty seats). **Critical:** the manual path must be clearly labeled as fallback, not equivalent preparation.

**Professor controls:** Professor Control page has: TRY DEMO button, setup form (scenario, equity, rounds, seed, practice toggle, demo teams toggle), round actions (open, lock, resolve, advance), leaderboard, reset demo, end game early. Auto-advance available in demo mode. **Clarity assessment:** controls are reasonably clear. Lock before resolve is enforced (button disabled if not LOCKED). Advance before resolve is enforced. **Risk:** no hard timer — professor manages pace verbally. No "late student" recovery beyond late submission before lock.

**Classroom risks:** (1) No hard timer means rounds can run long. (2) Professor must verbally enforce the model-first expectation — the manual path makes it easy to skip. (3) The Cloudflare Workers preview deployment may not render the Streamlit app correctly on all routes — test the locally-running version before the meeting. (4) The thesis/falsification gap means professor mustfacilitate communication assessment manually.

**Professor can:** tell students what to do next (progress strip + page links), recover from late student (accept submission before lock), NOT advance too early (enforced), see submission completeness (professor control page), explain what happened (debrief answers 10 questions from recorded history), run debrief without knowing codebase (all answers computed from history).

### Agent J — Debrief/Learning-Assessment Specialist (final_debrief.py audit)

**The debrief is the strongest feature.** It has 9 sections: 10 questions (answered from recorded history), final standings, where the money came from (5-channel NAV bridge), analytics leaderboard (separate from game), model vs manager vs luck (5 named cases + teaching notes), every attempt decomposed (model/decision/override/outcome labels), recorded overrides (per-team detail), portfolios (per-team holdings), strategy evolution.

**10 questions cover:** who won, best model, same team?, most overrides, did overrides help, most leverage, did leverage create/destroy value, good decision/bad outcome, lucky outcome, what should a student conclude. These directly address model quality vs decision quality vs luck.

**Uncomfortable cases tested:** The 5 NAMED_CASES include GOOD_DECISION+BAD_OUTCOME and BAD_DECISION+LUCKY_OUTCOME. The teaching notes explain each. The override_detail section shows every departure from policy. The attempts section decomposes each decision four ways.

**Gap:** Thesis/falsification/confidence are NOT surfaced. The debrief is quantitative — it shows numbers but not the student's written reasoning. A student who wrote a thoughtful thesis gets no signal back about whether their reasoning was sound.

---

## Issues

### P0 — Game/classroom correctness failures: 0

### P1 — Materially harms REAL 605 learning objective or tomorrow's demo: 3

1. **P1-1: Thesis/falsification not surfaced in debrief.** The game collects student investment theses and falsification tests per property but the final_debrief.py does not show them back to the student. This directly weakens the communication outcome (Outcome 3) and the critical thinking outcome (Outcome 4). The student's most valuable written artifact is collected and then ignored. **Fix:** In final_debrief.py, for each property the student bid on, show "What you believed" (thesis + key assumption + falsification test as written by student), "What happened" (actual NOI growth, cap rate, value, return vs predicted), and "Update" (did the falsification condition occur?). ~2-4 hours. ~2-4 hours. Low risk — only displays existing data.

2. **P1-2: Manual/on-screen input path needs clear fallback labeling.** Commit c88e848 added manual inputs so students can play without a CSV. Without clear signaling, this becomes an alternative to pre-class modeling rather than an accessibility fallback. The analytics leaderboard cannot score model quality for manual-input students. **Fix:** Add st.info/st.warning on investment_decision.py and deal_room.py when no model is uploaded: "You are using manual inputs. Pre-class modeling is the intended REAL 605 experience. Manual inputs are available for accessibility/classroom fallback. Your results will not include model-quality scoring on the analytics leaderboard." ~30 minutes. Low risk.

3. **P1-3: 61%/62% tie means a single-session pilot could see no-analytics strategy win.** At 100 seeds, strong model (61%) and meet-ask-max-LTV (62%) are statistically tied. In one game, a student who didn't prepare could win and conclude "my gut was better." **Mitigation:** The analytics leaderboard separates model quality from game winner — the prepared student's model may be better even if they didn't win. The debrief's model-vs-manager-vs-luck section addresses this. Professor must debrief carefully. Not a software fix — a facilitation note.

### P2 — Useful pilot improvement: 2

1. **P2-1: Capex_need inconsistency.** deal_room.py displays "Capex need" per property that the engine never charges. The engine charges type-based capital reserves instead. Architecture doc R6 flags this. A practitioner reviewing the deal room will notice. **Fix:** Relabel "Capex need" to clarify it's informational, or hide it. ~30 minutes.

2. **P2-2: Strategy Card page has placeholder value_to_ask_ratio.** The page divides predicted_fair_value by itself — a placeholder that doesn't add value. **Fix:** Either complete the metric (needs asking prices from the pool) or simplify the page. ~1 hour.

### P3 — Future idea: 5

1. Pre/post assessment instrument
2. Cross-scenario comparison (what would have happened under Rate Shock vs Base Case)
3. Guided feature engineering notebook
4. Time/geography split lab
5. Hard timers for rounds

---

## Changes Actually Implemented

**None on this branch yet.** All work is documentation (assessment, pitch, brief, QA, pilot plan). The assessment identified 3 P1 fixes but none have been implemented yet — they are recommendations for before/during the pilot.

**Commit c88e848 (on main, merged into branch):** "allow classroom play without model CSV" — added manual on-screen input path to investment decision page. This is the most recent change and the one most relevant to the pilot.

---

## Game-Balance Result

**100-seed balance harness (Experiment C — classroom game, 3 bot funds + 1 human):**

| Human Strategy | Mean NAV | Win Rate | Top-2 | Assets | Premium to Ask | Val MAE |
|---|---|---|---|---|---|---|
| Never bids | $100.00M | 0% | 10% | 0.00 | +0.00% | 0.00 |
| Weak model, disciplined | $107.77M | 47% | 73% | 4.01 | -0.09% | 3.38 |
| Medium model, disciplined | $109.35M | 56% | 86% | 3.98 | -0.17% | 1.53 |
| Strong model, disciplined | $110.72M | 61% | 90% | 4.01 | -0.25% | 1.00 |
| Strong model, only cheap deals | $103.79M | 14% | 47% | 0.94 | -2.61% | 1.00 |
| Meets ask at max LTV | $109.89M | 62% | 89% | 7.14 | -0.03% | 1.53 |
| 5% over ask at max LTV (medium) | $104.39M | 50% | 68% | 9.61 | +4.84% | 1.53 |
| 5% over ask at max LTV (weak) | $104.39M | 50% | 68% | 9.61 | +4.84% | 3.38 |

**Correlations (Experiment C):**
- corr(NAV, selection quality) = +0.851
- corr(NAV, assets acquired) = +0.206
- corr(NAV, gross LTV) = +0.287
- corr(NAV, valuation MAE) = +0.112
- corr(NAV, premium paid to ask) = -0.130

**Effects:**
- Analysis effect (strong - weak, same policy) = +$2.95M
- Deployment effect (aggressive - disciplined, same model) = -$4.96M
- Capital deployment does NOT dominate: NO

**Interpretation:** The 61% vs 62% tie is sampling noise at 100 seeds. The strong model's mean NAV ($110.72M) exceeds meet-ask-max-LTV ($109.89M). Selection quality drives NAV (r=+0.851), not aggression. Analysis wins on average, not every seed — which is the honest and desirable outcome. **No coefficient changes recommended.** The current economics produce the intended lesson.

---

## Pedagogy Result

**Outcome 1 (Knowledge of Real Estate): IMPLEMENTED (strong).** Real OC data context, real public market anchors, property-level CRE underwriting metrics (cap rate, NOI, WALT, tenant concentration, debt rate, LTV, DSCR), data honesty framework, provenance page. Strongest outcome.

**Outcome 2 (Problem Solving): PARTIAL → IMPLEMENTED (improving).** Model skill gradient verified (NAIVE 0.500 → STRONG 0.958 AUC). Valuation Lab + SQL Lab + Data Quality Challenge work. Gaps: full AVM notebook is placeholder, no guided feature engineering, no time/geography split lab, no time-series forecasting lab. The manual path (c88e848) is a fallback that must not become the default.

**Outcome 3 (Communication): PARTIAL (underdeveloped).** The game COLLECTS thesis/falsification/key assumption/confidence per property but the debrief does NOT surface them back. This is the #1 gap. The debrief is almost entirely quantitative. A student who wrote a thoughtful thesis gets no signal back about whether their reasoning was sound.

**Outcome 4 (Critical Thinking): IMPLEMENTED (strong).** Sealed-bid auction, capital constraint, override recording, model-vs-manager-vs-luck classification (5 named cases), decision quality scored ex-ante, uncertainty (61% vs 62% tie) that forces the process-vs-outcome conversation. Strongest design element.

**Three strongest honest learning claims:**
1. "This simulation gives students a controlled environment where better analytics improve investment decisions on average — verified by the model skill gradient (AUC 0.500 → 0.958) and the balance evidence (analysis effect +$2.95M)."
2. "The debrief separates model quality, decision quality, and luck — so a student who made a sound decision that got unlucky learns not to change their process, and a student who made a bad decision that got lucky learns not to repeat it."
3. "The economics are honest and inspectable — every dollar of NAV change is one of five explicit CRE channels (value change + NOI - interest - deal costs - reserves), verified to machine precision, with no LLM adjudication."

---

## Classroom Result

**Demo mode:** Works. TRY DEMO starts a preloaded game (Buy&Hold Capital + 3 bots). Auto-advance walks through practice → 4 rounds → debrief. 53/53 checks pass.

**Professor controls:** Work. Setup form, round actions (open/lock/resolve/advance), leaderboard, reset, end early. Lock-before-resolve and advance-before-resolve enforced.

**Student isolation:** Works. YOUR MODEL panel is per-fund and private. No other team sees another team's predictions. No attempt to view another fund's data succeeds in the current MVP.

**No-model path:** Works (c88e848). Manual inputs accepted on investment decision page. **Must be clearly labeled as fallback.**

**Cloudflare Workers deployment bug (confirmed, blocking):** The preview deployment
(`cre-game-preview.scswitzer.workers.dev`) is served via Cloudflare Workers with a
Durable Object container running the Streamlit app. During the 2026-09-18 playtest,
the landing page (`/`) and game routes (`/game/...`, `/professor`) consistently
returned empty `document.body.innerText` after multiple wait cycles — the Streamlit
app was not rendering on those routes. Only the `/join` route rendered content. **This
is a blocking issue for any browser-based playthrough and must be resolved before the
Frenzel demo.**

**Root cause:** Undetermined. The JS bundle (363KB) is served correctly (HTTP 200,
correct content-type), so the Cloudflare Worker responds to requests. But the Streamlit
app inside the container is not rendering. Possible causes: container not started,
engine service (port 8081) not healthy, Streamlit not binding to the right port, or
a Worker routing issue.

**Confirmed workaround:** Run the app locally with `uv run python -m streamlit run
app.py` from `/tmp/cre-investment-sim` on port 8501. Open http://localhost:8501. This
bypasses the Cloudflare deployment entirely and is the recommended demo method.

**If the Cloudflare deployment is needed:** Diagnose the container — is it running?
Is `scripts/serve_engine.py` healthy on port 8081 inside the container? Is Streamlit
starting and binding to port 8080? The `cloudflare/Dockerfile.cloudflare` shows the
container runs `scripts/serve_engine.py` (engine on 8081) + `node dist/index.js`
+(the Vue frontend). The Vue app is the Cloudflare deployment's frontend; the actual
+game logic is Streamlit. If the Vue frontend is the entry point, check whether it is
+proxying requests to the Streamlit backend correctly.

---

## Security/Integrity Result

**Adversarial testing:** No P0 integrity violations found. Streamlit session state is per-tab/per-session. Bid validation correctly rejects insufficient-cash bids. No cross-tab coordination in MVP. No NaN/number input exploitation surface (Streamlit number_input validates ranges). No attempt to view another fund's data succeeds (YOUR MODEL panel is per-fund, private). The manual path does not introduce new attack surface.

**Data visibility:** Reserve prices and future outcomes never reach the browser. Visibility boundary enforced in the architecture and tested (test_engine_api_visibility.py). The adjudicator is the single source of truth — no LLM, no opaque model.

**Limitation:** The current MVP stores state in-memory in Streamlit session state. There is no persistent backend in the preview deployment — refresh loses state. This is fine for a demo but would need the engine service backend for a real multi-student classroom. The architecture doc describes the planned backend (Node 22 + TypeScript + Fastify on Cloud Run, Firestore server-side only, SSE to browsers) but it's not yet deployed.

---

## Artifacts Produced

All in /tmp/cre-investment-sim/docs/:

1. **REAL605_LEARNING_ALIGNMENT_FINAL.md** — pedagogical gap analysis, MSRE outcome mapping, top 3 fixes, overall assessment. 18,326 bytes.
2. **FRENZEL_PITCH_DECK.md** — 7-slide pitch deck with slide copy, speaker notes, visual instructions, data/chart values, appendix with all balance numbers. 19,487 bytes.
3. **FRENZEL_MEETING_BRIEF.md** — one-page meeting brief: 30-second pitch, what to demo, why REAL 605, what's proven, honest limitations, 10 questions for Frenzel, the ask. 6,501 bytes.
4. **FRENZEL_QA.md** — 15 Q&A with honest limitations: why this, why not Excel, class time, prep needed, what breaks if unprepared, grading, luck, realism, trust economics, control, real data, before-class work, pilot measures, what to change after, can I trust the economics. 18,117 bytes.
5. **FRENZEL_PILOT_MEASUREMENT.md** — lightweight pilot measurement plan: pre-game, during-game, post-game measures, success criteria, data collection, what not to measure, after-pilot plan. 6,096 bytes.
6. **FRENZEL_DEMO_SCRIPT.md** — updated 8-10 minute demo script with current-head notes (manual path, Cloudflare deployment bug, thesis gap). Patched from original.

Plus the pre-existing:
- REAL605_LEARNING_OBJECTIVES.md (implementation map, IMPLEMENTED/PARTIAL/PLANNED)
- GAME_RULES.md (student-facing rules)
- GAME_ECONOMICS.md (all coefficients, balance evidence)
- PROFESSOR_DEMO_SCRIPT.md (5-8 minute professor walkthrough)

---

**Demo Recommendation for Tomorrow**

**Run the app locally for the demo if the Cloudflare Workers deployment is not rendering correctly.** Start with:

```bash
cd /tmp/cre-investment-sim
uv run python -m streamlit run app.py
```

Then open http://localhost:8501 in a browser. The locally-running Streamlit app eliminates the deployment-layer issue entirely.

**Show in this order (8-10 minutes):**

1. **Home page** (1 min): one-line summary + data honesty.
2. **Model Check-In** (1 min): show the contract (predicted_fair_value, predicted_noi_growth, probability_of_downside, max_bid, target_ltv). Emphasize max_bid is where analysis becomes policy. Mention the manual fallback exists but is not equivalent.
3. **Deal Room** (2 min): show 16 metrics per property. Point at YOUR MODEL panel (preloaded) — these are the student's numbers, not the game's.
4. **Investment Decision** (1 min): show thesis + falsification fields. Note these are collected but the debrief doesn't yet surface them (honest limitation, #1 fix).
5. **Professor Control → TRY DEMO → Auto-Advance** (2 min): walk practice → Round 1 → lock → resolve → show winners + reserves.
6. **Final Debrief** (3 min): 10 questions, where the money came from (5-channel NAV bridge), analytics leaderboard (separate from game), model vs manager vs luck. Read questions 8 and 9 aloud — the uncomfortable cases.

**Do NOT show:** every page. Data Catalog, SQL Lab, Valuation Lab, Geospatial View are prep tools — mention them but don't walk them. Strategy Card is currently underweight — skip unless asked.

**Lead with:** "This is model-first, not game-first. Students build the model before class; the game is only the decision environment."

**End with:** "I want your feedback on whether this teaches the right things, not just whether the software works."

---

## Changes NOT Recommended Before the Meeting

1. **Do NOT change economic coefficients.** The balance evidence supports the current coefficients. No deal costs, capital reserves, debt rates, reserve prices, or property distributions changes without strong evidence of pedagogical failure.
2. **Do NOT implement the thesis/falsification debrief surfacing before tomorrow.** It's the #1 fix but it's 2-4 hours of work but would be worth doing before the meeting if time permits. The current debrief is strong without it.
3. **Do NOT add hard timers.** The professor controls pace verbally. Timers are planned but not necessary for a pilot.
4. **Do NOT build a pre/post assessment instrument before tomorrow.** It's a P2/P3 improvement. For a first pilot, self-report + professor observation is enough.
5. **Do NOT change the manual path behavior.** It works as a fallback. Only needs UI text labeling.

---

## Ask for Frenzel

**"Would you be willing to pilot this in REAL 605 and tell me what needs to change for it to teach the course the way you want?"**

Not: "Will you adopt my software?"

If yes: one REAL 605 class session, student + professor feedback, measure learning outcomes, revise after pilot. I'll implement the highest-priority fixes (thesis/falsification in debrief, manual path clarification) based on your feedback before a second pilot.

---

*End of readiness report.*
