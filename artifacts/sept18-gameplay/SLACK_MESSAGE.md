# Slack-ready message (Sept 18 gameplay overview)

Copy/paste below and attach `fenrix-cre-game-overview.html` in the same message
(or drop the link if the artifact is hosted somewhere the channel can open).

---

Hey — I put together the current real-estate game flow based on today's
discussion. Here it is as a short HTML overview (attached, ~2 minutes to read).

The core loop is underwriting → bidding → acquiring → managing → results, run
over several rounds, with each team's model feeding its own bids:

- **Before class:** teams get the dataset and build their model(s)
- **In class (~60–75 min):** market update → underwrite → sealed-bid auction →
  operate what you own (rent, vacancy, maintenance, surprises) → portfolio
  update → leaderboard

I also mapped the class versions:

- **605** — simpler valuation-focused version, run first as the real-world test
- **310** — valuation + vacancy + rent, with per-building management decisions
- **220** — simplified regression version, Excel/Solver friendly

The HTML walks through the screens, the model ladder, and what's working today
vs. what's still planned.

The main things I'd like feedback on:

1. **Level of management complexity** — how much operating detail belongs in the
   round before it slows the game down (and how often surprises should hit)?
2. **310 dataset** — keep it commercial, or add a residential option to teach the
   same loop on a simpler asset class?

Reply in-thread if you have thoughts — and if you want to work on a slice, the
areas are game UX, data & models, engine & infrastructure, and classroom ops.
