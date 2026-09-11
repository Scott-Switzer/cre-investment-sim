# Professor Demo Script

**Audience:** Professor Tim Frenzel, REAL 605 Real Estate Analytics

**Length target:** 5–8 minutes

**Starting page:** Home (`/`)

**Goal of the opening:** Answer within 30 seconds the question, *"What decision is the student trying to make?"*

Do **not** open by listing features. Open with the investment-committee problem.

---

## 0. Before you start (15 seconds)

1. Launch the app:
   ```bash
   uv run python -m streamlit run app.py
   ```
2. Confirm the sidebar shows:
   - Demo mode checked
   - Market scenario: **Base Case**
   - Decision date: **2024-03-31**
   - Available capital: **$150M**
3. Click **3 · Professor Control — start the demo** in the home page links, or simply begin at **1 · Briefing**.

The demo is already pre-seeded with one complete game, including one locked sample decision for **OC-INDU-01** under the Base Case.

---

## 1. Investment Committee Brief (about 45 seconds)

**Page:** `1 · Briefing — Investment Committee Request`

**Say:**

> "You are an investment team at a small Orange County CRE fund. It is March 31, 2024. The committee has authorized you to deploy up to $150M of equity across a pipeline of acquisition candidates. One round is one quarter. There are three rounds. Your job is to decide, property by property, which ones to buy and at what price and leverage, using only the data available as of today."

**Click through:**

- Note the mandate table: available capital, hurdle return, max LTV, min DSCR, concentration limits, rounds, decision date.
- Note the task: BUY/PASS, with bid, LTV, NOI growth forecast, exit cap forecast, confidence, thesis, and a **what would prove this thesis wrong?** response.

**What this demonstrates:**

- Real-estate analytics begins with a business problem, not a model.
- Students must frame the decision before touching any data.
- This maps to Module 1: *Business Problem Definition*.

**Next:** click **→ Next: Market Explorer**.

---

## 2. Analyze the Data (about 90 seconds)

### 2a. Data Quality Challenge (about 40 seconds)

**Page:** `2 · Data Quality Challenge`

**Say:**

> "Students don't get a pristine dataset. They get a deliberately imperfect copy — the kind they will actually face in practice. Some issues are noise; some matter a lot. One field here is a future-data leakage trap: it is only available after the decision date, and using it would cheat."

**Click through:**

- Show the student data table.
- Show the **data quality manifest** and the **leakage trap** field.
- Note one or two concrete issues: a duplicate property row, missing occupancy or NOI in places, inconsistent property type labels, a stale observation, a value in the wrong units.

**What this demonstrates:**

- REAL 605 Module 1: *Data Cleaning*, *Data Sources and Data Types*.
- Point-in-time hygiene: students must learn not to lean on information that did not exist at the decision date.
- The app does not fix everything for them. They must clean and justify.

**Next:** click **→ Next: Deal Room**.

### 2b. Market Explorer (about 25 seconds, optional quick pass)

**Page:** `4 · Market Explorer`

**Say:**

> "Here is real public market context plus distributions of the candidate properties. This is enough to form hypotheses. It does not tell you which property is best."

**If time is tight, skip the full explorer** and move straight to the Deal Room. The Market Explorer is there for the analytics-minded student; the professor does not need to dwell here during the first demo.

**Next:** click **→ Next: Deal Room**.

---

## 3. Value the Opportunity (about 90 seconds)

### 3a. Deal Room (about 45 seconds)

**Page:** `7 · Deal Room`

**Say:**

> "These are the candidate acquisitions. For each property we show asking price, NOI, going-in cap, occupancy, WALT, debt rate, max LTV, and primary risks. We do not show the future outcome. That is reserved for the debrief."

**Find the pre-seeded deal:** look for **OC-INDU-01**.

If the OC-INDU-01 case looks too thin for the story you want to tell, improve its thesis and forecast in the decision page in the next step, but do not change the underlying property record gratuitously. The pre-seeded decision is the spine of this demo.

**What this demonstrates:**

- Investment-committee presentation discipline: 5–7 critical metrics up front, with secondary detail available but not cluttering the screen.
- BUY/PASS framing from the earlier prototypes is preserved.

**Next:** click **→ Next: Investment Decision**.

### 3b. Investment Decision (about 45 seconds)

**Page:** `8 · Investment Decision`

**Say:**

> "This is where the student commits. BUY or PASS. If BUY: bid, LTV, NOI growth forecast, exit cap forecast, predicted value, confidence, and an investment thesis that includes what would prove the thesis wrong. Once locked, the decision cannot be silently edited."

**If a pre-seeded decision already appears for OC-INDU-01**, walk through it:

- Show the submitted bid, LTV, NOI forecast, exit cap forecast, predicted value, confidence, probability of loss, thesis, and falsification condition.
- Confirm the submission timestamp and round are recorded.
- Confirm that the **locked** indicator is set.

**If you want a slightly stronger teaching story for OC-INDU-01**, you can gently strengthen the thesis and forecast here, for example along these lines:

- A warehouse in Orange County with solid in-place occupancy and a realistic rent gap to market.
- A moderate bid below asking.
- A going-in cap above the risk-free rate plus a real spread.
- A conservative LTV and DSCR.
- A thesis that depends on continued employment growth and stable industrial vacancy — and a clear falsification condition, such as a sharp rise in industrial supply or a collapse in logistics employment.

Do **not** make the case look obviously perfect. The point is to show a real, defensible-sounding student decision that can later turn out good-or-bad depending on the market.

**What this demonstrates:**

- Decision journaling and audit log.
- Lock immutability.
- Forecast discipline, not just a price guess.

**Next:** return to **Professor Control**, or click **→ Next: Professor Control**.

---

## 4. Professor Control — Lock / Advance / Reveal (about 60 seconds)

**Page:** `10 · Professor Control`

**Say:**

> "The professor controls the clock. Lock submissions so no one edits after seeing the outcome. Advance the round. Then reveal the market resolution."

**Click through:**

1. Confirm round status: **Locked: No**, **Revealed: No** (if you restarted) or **Locked: Yes** (if you are on the pre-seeded state).
2. If needed, click **Lock round**.
3. Click **Advance to next round** if you want to move beyond round 0.
4. Click **Reveal outcome**.

**What this demonstrates:**

- The simulation does not auto-resolve; the instructor controls disclosure.
- The underlying engine is a pedagogical simulator with Base Case, Rate Shock, and Growth Rebound scenarios, seeded and reproducible.
- The resolution is not a random "recession card"; it responds to market state variables.

**Important:** if your first open already shows the pre-seeded decision as locked and round 0 revealed, you can skip the lock/advance step and proceed straight to the debrief. The pre-seed exists so the first reviewer does not have to build a decision before seeing the debrief flow.

**Next:** click **→ Next: Results / Debrief**.

---

## 5. Reveal + Debrief (about 90 seconds)

**Page:** `11 · Results / Debrief`

**Say:**

> "This is the most important part of the course alignment. We do not just say how much money was made. We separate outcome from process."

**Walk the five score components:**

1. **Outcome quality** — what actually happened financially.
2. **Forecast quality** — how accurate the NOI, cap-rate, and value forecasts were.
3. **Risk quality** — did the student stay inside LTV, DSCR, and concentration limits.
4. **Decision quality** — was the decision reasonable given the information available at the decision point.
5. **Process quality** — did the student use point-in-time information and avoid leakage.

**Point at the narrative classification if it appears:**

- Good decision / good outcome
- Good decision / bad outcome
- Bad decision / good outcome
- Bad decision / bad outcome

**Emphasize expected vs. realized return.** A student who made an analytically sound decision should not be treated as incompetent just because one stochastic realization was unfavorable. Decision-quality scoring is based primarily on the information and probability distribution available before realization.

**What this demonstrates:**

- REAL 605 Module 7: *Decision making* — converting analytical findings into executive recommendations across alternative futures.
- REAL 605 Module 5: *Interpretation* — explain results for an investment committee.

**Next (optional):** click **→ Appendix: Provenance & Methodology**, or end the demo here.

---

## 6. Provenance & Methodology (about 30 seconds, optional closer)

**Page:** `12 · Provenance & Methodology`

**Say:**

> "Everything in this app is labeled. Real public data from Orange County, Census, LEHD/LODES public samples, and FRED where available. Synthetic teaching data for the property operating cases. Derived features. Simulated futures. We do not claim the simulator forecasts the actual Orange County market."

**Point at the data honesty tags:**

- REAL PUBLIC DATA
- SYNTHETIC TEACHING DATA
- DERIVED FEATURE
- SIMULATED FUTURE

**End the demo here** if you are at 5–8 minutes. This is a clean stopping point.

---

## Quick presenter cheat sheet

- **Open with the problem, not the tool.**
- **The pre-seeded decision is for OC-INDU-01 under Base Case.**
- **The leakage trap is the single most important teaching moment in the data-quality section.**
- **The debrief must separate luck from skill.**
- **If a page feels empty during rehearsal, first check that the demo database has been bootstrapped**, then check the Professor Control pre-seed.

---

## One-shot rehearsal sequence

1. Home → **3 · Professor Control — start the demo**
2. Professor Control → **→ Next: Results / Debrief** (if pre-revealed) or
3. Home → **1 · Briefing** → **→ Next: Market Explorer** → **→ Next: Deal Room** → **→ Next: Investment Decision** → back to Professor Control → Lock → Reveal → Results / Debrief → Provenance & Methodology

That full loop is the defensible MVP walkthrough for next week.
