# Pilot Measurement Plan — REAL 605 CRE Simulation

**Lightweight, practical, non-IRB. For a one-session pilot.**

---

## What We're Trying to Learn

1. Do students engage with the model-first → decision-environment structure?
2. Does better analysis produce better decisions (measurable)?

3. Can students articulate why their decisions worked or failed after the debrief?
4. Does the classroom flow work without the professor debugging software?
5. Does the debrief generate useful discussion about model vs manager vs luck?

---

## Measures

### Pre-game (before class, 5 minutes)

**Student self-report (1-5 scale, anonymous):**
- "How confident are you in your ability to value a commercial real estate property using a model?"
- "How confident are you in your ability to make an investment decision under capital constraints?"
- Optional: 3-question short pre-test on CRE valuation concepts (cap rate, NOI, LTV, DSCR definitions)

**Submission data (objective):**
- Model submission rate: % of students/funds that upload a model CSV vs use manual path
- Model quality proxy: valuation MAE of submitted model vs naive benchmark (if enough submissions)

### During game (observed, no student burden)

**Decision data (objective, from game):**
- Decision completion rate: % of properties decided per round (BUY or PASS submitted)
- Override rate: % of bids that depart from model max_bid / target_ltv
- Bid aggressiveness: average premium/discount to ask per fund
- LTV usage: average LTV per fund vs target LTV
- Assets acquired: count per fund

**Classroom observation (professor/researcher):**
- Time per round (did rounds stay within target timing?)
- Technical issues (page load problems, confusion about what to do, etc.)
- Student engagement (visible effort on decisions, discussion among teammates)
- Late submissions (did any student/fund struggle to decide before lock?)

### Post-game (after debrief, 5 minutes)

**Student self-report (1-5 scale, anonymous):**
- "I can explain why my fund's decisions worked or failed."
- "I can explain how leverage created or destroyed value for my fund."
- "I can explain how cap-rate movement affected my portfolio."
- "I can explain the difference between forecast error and bad decisions."
- "I can explain the difference between a good decision with a bad outcome and a bad decision with a lucky outcome."
- "The simulation helped me understand real estate investment decisions better than a spreadsheet assignment alone would have."

**Optional post-test (same 3 questions as pre-test, if used):**
- Measures concept retention: cap rate, NOI, LTV, DSCR

### Professor observation (after class, 10 minutes)

**Frenzel's assessment (free text, 5-10 minutes):**
- "Did the classroom flow work without you debugging software?"
- "Did the debrief generate useful discussion?"
- "Did students distinguish model quality from decision quality from luck?"
- "What would you change before a second pilot?"
- "Would you use this again? Why or why not?"
- "What's the one thing that would make this most useful for your class?"

---

## Success Criteria

**Must-pass (pilot is a failure if these don't happen):**
1. Classroom flow works without professor intervention on software (no blocking technical issues)
2. All students can complete decisions and the game reaches the debrief
3. Professor can run the debrief from the final_debrief screen without needing to read code

**Should-pass (pilot is promising if these happen):**
4. ≥80% of students/funds upload a model (model-first pedagogy is engaging, not rejected)
5. ≥80% of students self-report ≥4/5 on "I can explain why my decisions worked or failed"
6. Debrief discussion includes explicit distinction between model quality, decision quality, and luck (observed by professor)

**Nice-to-have (pilot is strong if these happen):**
7. Model submission rate correlates with game performance (analytics leaderboard separates teams meaningfully)
8. Students who uploaded models self-report higher confidence post-game than those who used manual path
9. Professor gives specific, actionable feedback beyond "it worked" / "it didn't"

---

## Data Collection

**Automated (from game):**
- Export scores CSV from professor control at end of game
- Contains per-fund: NAV, return, cash, debt, assets, rank, valuation MAE, NOI MAE, Brier score, value vs naive, override count, override contribution, decision quality, outcome quality, forecast quality, risk quality, process quality

**Manual (from students):**
- Pre-game: 2-3 survey questions (1-5 scale) — can be paper or Google Form
- Post-game: 5-6 survey questions (1-5 scale) — same format

**Professor (from you):**
- 5-10 minute free-text reflection after class
- Answers to the 5 observation questions above

---

## What I Would NOT Measure in a First Pilot

- Pre/post concept test with graded questions (too much friction for one session)
- Individual student-level tracking across multiple games (one session only)
- Statistical significance tests on small samples (n will be small; descriptive is enough)
- LLM-based thesis scoring (would undermine the communication outcome's human element)
- Long-term retention (can't measure in one session)

---

## After the Pilot

**Within 1 week:**
- Compile measures into a short summary
- Identify P0/P1 issues from classroom observation
- Note any changes Frenzel requests

**Within 2 weeks:**
- Implement highest-priority fixes (thesis/falsification in debrief, manual path clarification, capex_need fix)
- Prepare for second pilot if warranted

**Decision points:**
- If classroom flow fails (blocking technical issues): fix before second pilot
- If model submission rate is low (<50%): investigate why — is it preparation burden, confusion, or students choosing manual path? Address before second pilot.
- If students can't articulate outcomes: improve debrief (thesis/falsification surfacing is the likely fix)
- If professor is enthusiastic: plan second pilot with more measures
- If professor is lukewarm: understand why before investing more

---

*End of pilot plan.*
