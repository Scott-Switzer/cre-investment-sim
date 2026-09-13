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

> "You win on ending NAV. But NAV moves for exactly five reasons, and I can show
> you all five: the change in property values, the NOI the portfolio paid you, the
> interest you paid on the debt, the deal costs you paid to buy, and the capital
> reserves the buildings consumed."

Open the **Final Debrief** after the fourth round. Point at *Where the money came
from*.

> "Value change plus NOI income minus interest, minus deal costs, minus reserves
> equals NAV minus the starting equity. There is no sixth term, and no opaque score."

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

**Does buying the most assets win?** No, and that is measured rather than asserted.
`scripts/balance_harness.py` runs the real four-fund game across 100 seeds with
different human strategies. A strong model bidding its own ceiling finishes at
$110.72M and wins 61% of games; bidding 5% over the ask at maximum leverage finishes
at $104.39M and wins 50%; never bidding finishes at $100.00M and wins 0%. A stronger
model at a fixed policy is worth about +$3.0M, and aggression costs about −$5.0M.
`corr(NAV, assets acquired)` is +0.21.

Why: deal costs of 2% on every purchase, capital reserves charged each year by
property type, and interest at a debt rate above the market cap rate. A property
bought near the ask and levered to the limit roughly earns its cost of debt, so the
money comes from buying assets the model says are cheap. Every coefficient and the
full balance evidence are in `docs/GAME_ECONOMICS.md`.

**The honest limitation.** Maximum leverage paid at the asking price is still a
competitive strategy — it wins 62% of seeds against the strong model's 61%, with a
lower ending NAV ($109.89M vs $110.72M). Analysis wins on average, not on every seed,
which is exactly the point: the debrief has to separate model quality from decision
quality because outcome alone will not.
