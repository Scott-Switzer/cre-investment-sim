# September 18, 2026 — Professor Requirements Record

Source of truth, in precedence order:

1. this repository and the running staging build (`cre-game-preview.scswitzer.workers.dev`)
2. the September 18, 2026 professor meeting
3. prior design / meeting context

This file is the requirement **record**; `docs/V2_PRODUCT_SPEC.md` is the
implementation-grade spec derived from it. Every requirement below carries a
classification:

- **CONFIRMED** — explicitly requested. Enters the core implementation.
- **IMPLIED** — strongly implied by confirmed direction; enters as supporting
  engineering when cheap and safe.
- **PROPOSED** — discussed as an option; must not block confirmed work.
- **DEFERRED** — explicitly out of scope for now; preserved so nobody re-litigates.

---

## 1. The immediate deliverable

> "Just give us like we did last time ... kind of an HTML, very simple."
> "you two put your gameplays on the Slack channel."

**CONFIRMED.** First artifact of this sprint is a self-contained, simple HTML
gameplay overview suitable for Slack. Understandable in 2–3 minutes. No external
dependencies. It must not misrepresent unfinished features as implemented
(current / planned / optional labels). It exists to let teammates pick a project
team and give feedback.

Status: **DONE this sprint** — `artifacts/sept18-gameplay/fenrix-cre-game-overview.html`.

## 2. The game concept (unchanged core)

Students receive data before class → build predictive model(s) → run a CRE fund
→ bid against other teams → acquire and manage properties → respond to changing
operating conditions → **portfolio NAV decides the winner**.

**CONFIRMED.** Target length ≈ 60–75 minutes. Class time must not become model
training time; models are prepared from the pre-released dataset and *used*
during gameplay. (The existing service already follows this pattern: packet
before class, model check-in, then play.)

## 3. Management layer

> Acquired properties must be **managed**, not purchased and ignored.

**CONFIRMED.** The model ladder as discussed:

| # | Model | Predicts | Informs |
| --- | --- | --- | --- |
| 1 | Acquisition / property value | fair value | maximum bid |
| 2 | Vacancy / tenant occupancy | occupancy risk | acquisition risk + management response |
| 3 | Rent / income development | NOI trajectory | expected return, hold/repair strategy |

**CONFIRMED** (ladder direction); the precise per-model contract is
**IMPLIED** and specified in the product spec.

Operating shocks — maintenance costs, operational interruptions, market changes,
other defensible property-level surprises — should develop over roughly five
rounds. **CONFIRMED** in direction; exact per-round schedule is **IMPLIED**
(round count 5 is the professor's "roughly five", so the default V2 game is 5
scored rounds, configurable).

One coherent investment lifecycle — UNDERWRITE → BID → ACQUIRE → OPERATE →
UPDATE EXPECTATIONS → ALLOCATE CAPITAL → MEASURE — not three bolted-together
mini-games. **CONFIRMED.**

## 4. Course tiering

Same core engine, different instructional complexity **by configuration, not
three forked applications**:

| Course | Role | Models | Method cap |
| --- | --- | --- | --- |
| 605 | first real-world stress test, ~15–16 students | 1 (valuation) | Random Forest level |
| 310 | primary/full ML version | 2–3 (value + vacancy + rent/income) | XGBoost / logistic-regression level acceptable |
| 220 | simplified rollover | fewer features, regression focus | Excel/Solver-friendly if required |

**CONFIRMED** as direction. The repository already has the right seam
(`GameConfig`, `config/bundles/*.json`); V2 adds a `course_mode` concept on top.
The professor also asked for `dataset_variant` to be separate from
`course_mode` (commercial_oc now; residential_oc and a future US variant
listed).

## 5. Data strategy

Real + synthetic mix; build so datasets are **replaceable**. Do not block on
external sources (Vanguard conversation continues separately — **DEFERRED**).

**CONFIRMED:** data architecture must preserve source provenance, ground-truth
outcomes, train/test separation, scenario seeds, feature definitions, synthetic
transformation metadata, and course-mode compatibility. Most of this already
exists (data dictionary with provenance tags, bundles with pinned seeds +
candidate-pool hashes, packet built by the same `realized_year_outcome` the
adjudicator uses) — V2 work is to *verify and document* it against the new
management fields, not to rebuild.

**CONFIRMED:** properties must not be trivially reverse-searchable on Zillow
etc. If real OC properties are the foundation, anonymization/synthesis must
preserve relative pricing, submarket differences, rent/value and occupancy
relationships, property-type economics, macro sensitivity, and rank order where
pedagogically appropriate — using stable, heterogeneous perturbation rather than
one flat shift. A red-team pass must confirm no hidden outcomes leak into
student features.

## 6. Live AI / tenant agents

Agent-like tenant counterparties are the long-term Fenrix vision but **not
required** for the first stable classroom version. **CONFIRMED as DEFERRED.**
Round resolution must be deterministic / seeded-stochastic; no gameplay
reliability, latency, or cost may sit behind a frontier-model call. A tenant
behavior interface should exist so richer agents can substitute later
(**IMPLIED** as a design seam only).

## 7. Infrastructure

Two states, never conflated:

- **CURRENT:** Cloudflare Workers staging (`cre-game-preview.scswitzer.workers.dev`) — the baseline/control.
- **TARGET:** GCP Cloud Run for the event.

**CONFIRMED:** do not migrate before shipping the HTML and understanding the
repo; the React/Fastify/Python architecture is already Cloud Run compatible.
Cloud Run must tolerate reconnects, use Firestore as shared truth, keep
instances stateless, and not require session affinity. **IMPLIED:** decide
combined container vs sidecar based on deployment simplicity.

## 8. Firestore / game state

Concurrency-safe auction and round resolver; atomic transactions only where
actions genuinely compete; idempotent transaction functions; recoverable state
covering session, teams, config, round, property availability, bids, awards,
cash, debt, portfolio, operating state, predictions, outcomes, shocks,
leaderboard inputs. **CONFIRMED — and already largely true**: the existing
service stores the whole hidden engine snapshot on the session document
(gzipped), every commit is guarded ("resolve exactly once"), and `Idempotency-Key`
retries replay. V2 rule: **extend minimally, version migrations, do not rewrite
what works.**

## 9. Backup / restore

Not optional for the event: per-round recoverable checkpoints; AUTO SAVE /
ROUND CHECKPOINT / EXPORT / RESTORE / RESET concepts. **CONFIRMED.** Export
already exists (ZIP of revealed CSVs). Restore beyond reset is the gap to close
or explicitly scope.

## 10. Professor control plane

The professor view must run a real room: expected vs joined, connected /
disconnected, team identity, current phase, model check-in state, submitted /
not submitted, round progression, timer, open/close phases, per-team inspection,
export, recovery, big-screen leaderboard. Prioritize observability over
decorative analytics; the professor must be able to spot who is stuck.
**CONFIRMED** as a requirements list — much exists (phase machine, If-Match
transitions, timers, export, bigscreen); V2 review closes meaningful gaps.

## 11. UX standard (Bakery Bash lesson)

Plan the experience before coding features. Every screen states: user goal,
information shown, decision required, possible actions, validation/error state,
next state, professor visibility. Plain language first, domain term second
("Expected annual property income (NOI)"). Keep cash, borrowing capacity,
holdings, estimated value, income, vacancy, upcoming decision, and round
visible. No 3D. 2D clarity beats a beautiful confusing world. **CONFIRMED.**

## 12. Pedagogy standard

Every model must map to a real decision, or be removed. Design review must
answer: what it predicts, what trains it, when the student sees it, what
decision it informs, what is hidden, how reality resolves, what feedback
arrives, what to adjust next round. Round feedback must be timely; the
leaderboard must decompose into interpretable economic components for the
debrief. **CONFIRMED** — and the existing two-leaderboard design (NAV +
analytics) already embodies it.

## 13. Economic model

Do not replace tested economics without understanding them; audit for purchase
price, market value, cash, debt/LTV, transaction costs, reserves, rent/NOI,
vacancy, capital costs, appreciation, NAV, scoring. Add the management layer
**without double-counting returns**; write the accounting identities down before
changing code; final scoring reproducible from stored state; seeded simulation
replays identically. **CONFIRMED.**

## 14. Project management

Kanban/scrum view requested; milestone framing NOW → ~3 WEEKS (multiplayer
stress test) → BEFORE MAIN EVENT (605 test) → 310 target run → feature freeze 1
week before event. **CONFIRMED** as direction; exact dates deferred until the
event date is pinned.

## 15. Load expectation

60–70 students total across the broader event; design tests with headroom
(70 minimum, 100 simulated clients as a stretch target), burst-shaped around
join / submission / bid / round-close / leaderboard refresh / reconnect rather
than uniform GETs. **CONFIRMED** as the target. A previous 70-student/24-fund
load test exists (commit 507fda3); V2 re-validates after management changes.
