# Professor Frenzel Meeting Brief — One Page

**CRE Investment Committee Simulation — REAL 605 Pilot Discussion**
Scott Switzer · Chapman University · 2026-09-18

---

## THE 30-SECOND PITCH

REAL 605 students build a valuation model BEFORE class using real Orange County data. In class, they put it into a sealed-bid auction against rival funds, allocate $100M of equity across 4 rounds of simulated market outcomes, and then get a debrief that separates model quality from decision quality from luck. Better analytics create a measurable advantage — but don't guarantee every outcome. That's the lesson.

---

## WHAT TO DEMO (8-10 minutes)

1. **Model-first framing** (1 min): Show dataset downloads page — 2,400 historical observations + 120 candidates. "They build the model before class. The app never builds it for them."
2. **One investment decision** (3 min): Deal Room → Investment Decision. Show YOUR MODEL panel (preloaded), bid inputs, thesis/falsification fields. "This is where analysis becomes a policy — max bid decided before seeing the ask or your rivals."
3. **Professor advance** (2 min): Professor Control → Auto-Advance. Lock → Resolve → Advance. Show winners + reserves revealed.
4. **Results/NAV** (2 min): Leaderboard — ending NAV, cumulative return, 5-channel NAV bridge (value change + NOI - interest - deal costs - reserves).
5. **Debrief** (2 min): Final Debrief — 10 questions answered from recorded history. Model vs manager vs luck matrix. "Should you ever override your own model? Yes — but the game records it, and then we argue about it."

---

## WHY REAL 605

The simulation maps to the MSRE program's four learning outcomes:

- **Real-estate knowledge:** real OC parcel/assessment data, CBRE anchors, FRED macro, property-level underwriting metrics (cap rate, NOI, WALT, tenant concentration, debt rate, LTV, DSCR) — the same factors in an actual investment committee package
- **Problem solving:** build a model, submit predictions, see forecast accuracy revealed, compare to naive benchmarks — with a verified skill gradient (NAIVE AUC 0.500 → BASIC 0.896 → STRONG 0.958)
- **Communication:** investment thesis + falsification test per property; debrief surfaces predicted vs actual, forecast error, DSCR, value change
- **Critical thinking:** sealed-bid auction against rivals, capital constraint, human override recording, model-vs-manager-vs-luck classification, decision quality scored ex-ante

The game is NOT an alternative to the modeling assignments — it's the decision environment that makes the modeling matter.

---

## WHAT IS ALREADY PROVEN

- **Demo flow:** 53/53 checks pass — full practice → 4 rounds → winner → debrief loop verified
- **UI flows:** 35/35 checks pass — all screens render, no data leaks, debrief answers all 10 questions
- **Model skill gradient:** verified NAIVE 0.500 → BASIC 0.896 → STRONG 0.958 → ORACLE 0.978 AUC on "is this a good deal"
- **Economic balance:** 100-seed analysis shows strong model + disciplined bidding = $110.72M mean NAV, 61% win rate; aggressive deployment = $104.39M, 50% win rate; analysis effect +$2.95M, deployment effect -$4.96M; corr(NAV, selection quality) = +0.851
- **No LLM adjudication:** all economics in src/game/adjudicator.py — explicit, inspectable, 284 tests
- **No data leaks:** reserve prices and future outcomes never reach the browser; visibility boundary enforced and tested

---

## HONEST LIMITATIONS

1. **Communication outcome is underdeveloped.** The game collects student theses and falsification tests but the current debrief doesn't surface them back to the student. This is the #1 improvement I'd make — it closes the communication loop.
2. **Manual/on-screen input path exists** (added for accessibility) but needs clearer signaling that it's a fallback, not an equivalent to pre-class modeling. Without this, students may skip the model-building step.
3. **Strong model wins 61% of seeds, meet-ask-max-LTV wins 62%.** At 100 seeds these are statistically tied. Analysis wins on average, not on every seed — which is the honest and desirable outcome, but means a student who doesn't prepare can still win a given game.
4. **The student-built AVM notebook is a placeholder.** The baseline regression + submission interface exist, but the full guided workflow isn't built yet.
5. **"Capex need" is displayed in the deal room but not charged by the engine** — flagged as inconsistency R6 in the architecture doc.
6. **This is a pilot.** I'm not asking for permanent adoption tomorrow.

---

## QUESTIONS TO ASK FRENZEL

1. Does the model-first → decision-environment structure fit how you already teach REAL 605, or would you want to reshape it?
2. Would you want students to work in teams or individually? (The game supports both via fund/members.)
3. How many students would participate in a pilot? (The game handles 4 funds minimum; the architecture supports 70+.)
4. Would you want to grade the model submission, the decisions, the debrief participation, or some combination?
5. Is the thesis/falsification collection useful even if the debrief doesn't yet surface it — would you want that fixed before pilot?
6. Would you want to see the cross-scenario comparison (what would have happened under Rate Shock vs Base Case) added before pilot?
7. What's your reaction to the 61%/62% tie between strong model and meet-ask-max-LTV — is that acceptable uncertainty, or does it undermine the "analysis matters" message?
8. Would you want a pre/post assessment instrument built for the pilot?
9. What's the right class session to pilot this in — is it a natural fit for a specific week's topic?
10. What would make you say "this taught my students something I couldn't have done with a spreadsheet"?

---

## THE ASK

**Would you be willing to pilot this in REAL 605 and tell me what needs to change for it to teach the course the way you want?**

Not: "Will you adopt my software?"

If yes: one REAL 605 class session, student + professor feedback, measure learning outcomes, revise after pilot.

---

## PILOT SUCCESS LOOKS LIKE

- Students can explain why their decisions worked or failed (not just "I won" / "I lost")
- Model quality measurably affects decisions (analytics leaderboard separates teams)
- Classroom flow works without professor needing to debug software
- Debrief generates useful discussion about model vs manager vs luck
- Frenzel gives specific, actionable feedback on what to change
