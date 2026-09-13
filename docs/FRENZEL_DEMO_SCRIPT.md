# Frenzel Demo Script — 10 minutes

**One sentence to open with:** *This is model-first, not game-first. Students build
the model before class; the game is only the decision environment.*

Run everything from the landing page. No terminal, no database, no uploads.

---

## 0:00 — 1 min · The packet (model-first)

Open **PREP → Dataset Downloads**.

> "Students get this the week before class. 2,400 historical transactions across
> 400 Orange County properties, six annual vintages, with outcomes attached. And
> 120 candidate properties the game will actually offer — same buildings, later
> state, outcomes withheld."

Point at the two files that matter and say why the split exists:

- `historical_training.csv` — the model-building data, targets included.
- `game_candidates.csv` — the decision set, no future information anywhere in it.

> "They build whatever they want externally — Excel, R, XGBoost. The app does not
> build it for them and never will."

If asked whether the task is real modelling or a toy: **`uv run python
scripts/model_skill_gradient.py`** shows the gradient. A naive "it's worth the
asking price" model gets an AUC of 0.500 on *is this a good deal*. Ordinary OLS
gets 0.896. A model that uses the structure of real estate valuation gets 0.978.
That is a real spread, and it is the spread the course is teaching.

---

## 1:00 — 2 min · Model check-in and the strategy card

Open **PREP → Model Check-In**. Upload a filled
`prediction_submission_template.csv` — or point at the preloaded model.

> "The contract is `predicted_fair_value`, `predicted_noi_growth`,
> `probability_of_downside`, `max_bid`, `target_ltv`. **`max_bid` is the important
> one** — that is where analysis becomes a policy."

Then say the thing that makes this different from a dashboard:

> "Validation checks structure: are the property ids real, are probabilities
> between 0 and 1, did you duplicate a row. It will **never** tell you whether
> your model is accurate. Accuracy is revealed only as rounds resolve."

Open **PREP → Strategy Card**. Every number here comes from the team's own
uploaded file. The app is not generating a strategy; it is reflecting theirs.

---

## 3:00 — 3 min · Start a game and play one round

Landing page → **Professor Control → TRY DEMO**.

> "You are Buy&Hold Capital. Value Fund, Growth Fund, Risk Fund are the
> competition. You have a model preloaded — no setup."

Note the progress strip: **PRACTICE › ROUND 1 › ROUND 2 › ROUND 3 › ROUND 4 ›
DEBRIEF**, with the current stage filled in.

Walk the practice round once, then **Round 1**. On the deal screen, point at the
left column, then the **YOUR MODEL** pane:

> "Fair value, asking price, the model's max bid, target LTV, downside
> probability. Those are *your* numbers, from *your* file. No other team sees
> them, and the game is not computing them."

Then press **Auto-Advance Next Round** to lock and resolve. Show the result: who
won each of the four assets, at what price, against the seller's reserve.

---

## 6:00 — 2 min · Where the money actually came from

Advance to the standings and the leaderboard.

> "You win on ending NAV. But NAV moves for exactly three reasons, and I can show
> you all three: the change in property values, the NOI the portfolio paid you,
> and the interest you paid on the debt."

Open the **Final Debrief** after the fourth round. Point at *Where the money came
from*.

> "Value change plus NOI income minus interest paid equals NAV minus the starting
> equity. There is no fourth term, and no opaque score."

This is the moment to correct the most common student error: more assets is not
better. Leverage only adds value when the return on cost beats the debt rate —
and the table says which funds cleared that bar and which did not.

---

## 8:00 — 2 min · Model vs manager vs luck

Stay on the debrief. Read the ten questions *out loud* — they are answered on
screen from recorded history:

1. Who won the game? 2. Who had the best model? 3. Were those the same team?
4. Who overrode their own model most often? 5. Did those overrides help or hurt?
6. Who used the most leverage? 7. Did leverage create or destroy value?
8. Which decision looked right beforehand but went wrong? 9. Which team got
lucky? 10. What should a student conclude?

> "Now the part I actually care about. This screen refuses to treat the winner as
> the best analyst. It separates three things students constantly conflate: the
> quality of the model, the quality of the decision made with it, and luck."

Show the **model vs manager vs luck** cases. Two of them are uncomfortable on
purpose:

- *Good decision, bad outcome* — right process, unlucky year. Changing the process
  here is the mistake.
- *Bad decision, lucky outcome* — paid for a mistake. Not repeatable.

And the headline question:

> "Should you ever override your own model? Yes — but the game records it, and
> then we argue about it. Decision quality is judged **ex ante**, against what was
> knowable before the outcome, never against what the dice did."

---

## 10:00 — Close · The class flow

> "Here is the actual class period: five minutes of rules and model check-in, five
> to eight minutes of practice, four scored rounds of eight minutes with two
> minutes of feedback between each, and a fifteen-to-twenty minute debrief. QUICK
> CLASS and EXTENDED CLASS presets are both configured.
>
> The point is that **they build the analytics before class**, bring it in, and
> spend the class making decisions under a capital constraint. That is the REAL
> 605 outcome — model, then investment recommendation."

---

## Likely questions

**Where does this fit with the other labs?** The Data Catalog, SQL Lab, Valuation
Lab and Geospatial pages are PREP tools — course preparation. They are not the
game path. Nothing in them appears on the timed round screen.

**Is any of this LLM-adjudicated?** No. `src/game/adjudicator.py` is the rules
engine: bid validity, who wins, reserve prices, cash, debt, market transitions,
NOI, valuation and scoring. Full world state and player-visible state are kept
separate, and no language model decides any of it.

**Can a student cheat by reading the target columns?** The packet's
`data_dictionary.csv` marks the six outcome columns as targets, and
`docs/STUDENT_PACKET_README.md` lists them explicitly under "Never use these as
inputs". `next_year_value` is exactly `next_year_noi / next_year_cap_rate`, so a
model that peeks scores perfectly and teaches nothing — which is itself a
worthwhile conversation.

**What if I change the game seed?** The packet and the game are both built from a
seeded generator, so the same property id refers to a *different building* under a
different seed. The app checks this and warns; the verification scripts refuse to
run. Regenerate the packet if you change the seed.

**Known limitation to state plainly.** In the shipped parameterisation, capital
deployment has a bigger effect on the winner than valuation accuracy does: the
going-in cap rate sits above the debt rate, so carry is positive and a fund that
buys more assets earns more. The valuation signal is visible in the analytics
leaderboard and in the override cases, but it does not dominate the NAV race.
Tightening the spread between cap rates and the debt rate is the single highest-value
next tuning step.
