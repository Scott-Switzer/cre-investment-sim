# CRE Investment Committee — Pre-Implementation Architecture

**Status:** design. **Phase 0 (the engine service) is implemented** — see §12.
**Scope:** the new standalone game repo. The verified Python engine stays here, in
`cre-investment-sim`.
**Decisions already taken (by the project owner, 2026-09-13, revised same day):**

1. The game lives in a **new standalone repository**, not in `fenrix-ai/FenriX`
   and not in this repo.
2. The **verified Python adjudicator is wrapped as an engine service** and remains
   the single source of truth. Economics are **not** reimplemented in TypeScript.
3. The game service follows the **approved new-generation platform**: a Node 22 +
   TypeScript + Fastify container on **Cloud Run**, with **Firestore reached
   server-side only**, **SSE** (polling fallback) to browsers, and **signed HttpOnly
   cookies** for identity. It does **not** use the Firebase client SDK, client-side
   Firestore listeners, or Cloud Functions as its application server.

### Transitional baseline

> The full FenriX platform baseline — hub, shared services, agent players, the
> `game-<name>` scaffolding — **is not yet implemented**. This game implements its
> own game-service container now, but its interfaces and conventions are chosen to
> match that baseline, so it can move into the shared platform **without an
> architectural migration**. Nothing in this design depends on a component that
> does not exist; nothing in it needs to be undone when those components arrive.

> **Move this file into the new repo as `docs/ARCHITECTURE.md` when it is created.**
> It sits here today only because this repo is the current workspace and owns the
> engine it depends on.

---

## 1. Comparison of the three applications

Verified by reading the repositories, not from memory.

| | Bakery Bash | Salary Showdown | CRE Investment Committee (today) |
| --- | --- | --- | --- |
| Repo | `fenrix-ai/FenriX` | `fenrix-ai/FenriX` | `Scott-Switzer/cre-investment-sim` |
| Path | `games/bakery-bash` | `games/salary-showdown` | repo root |
| Frontend | React + Vite | React 19, TypeScript, Vite, `react-router-dom`, `@dnd-kit` | Streamlit (Python) |
| Backend | Cloud Functions | Cloud Functions, **plain JavaScript** | none — in-process |
| Engine | external Cloud Run service (`huginX`) via `docs/engine-api.md` | in-repo `backend/functions/src/engine.js`, with `test/fixtures/engine_parity.json` | in-repo Python, 284 tests |
| Identity | Firebase anonymous auth | `contexts/AuthContext.tsx` | none |
| Round orchestration | phase state on the game doc | `components/PhaseRouter.tsx` + `lib/phaseOrder.ts` | `GameManager` state machine |
| Professor surface | create/advance/pause, submission grid | `components/professor/{SessionSetup,SeatPanel,SubmissionGrid,TimerStrip,AdvanceControl,RevealStepper,RoundContext}.tsx` | Streamlit control page |
| Projection surface | — | `components/bigscreen/{LobbyWall,DecisionWall,StandingsShuffle,FinaleWall}.tsx` | none |
| Test discipline | balance reports, runbooks | ~116 `src` files; `lib/*.test.ts` for every pure module; **20 `*.itest.tsx`** integration tests; `backend/functions/test/*` incl. `advance-race.test.js` | 284 pytest; `verify_demo_flow` 53/53; `verify_ui_flows` 35/35 |
| Reusable by us | lobby, join codes, submission locking, professor controls | everything in the professor and bigscreen layers, phase routing, contexts, test harness | the only verified economics in the org |

### Three corrections to the original plan

- **`shared/` is not reusable code.** In `fenrix-ai/FenriX`, `shared/auth`,
  `shared/leaderboard`, `shared/analytics` and `shared/ai-agents` each contain
  **only a `README.md`**. Reuse means copying patterns from the games, not
  importing a shared library.
- **Salary Showdown's backend is JavaScript**, not TypeScript. Only its frontend is
  TS. A TypeScript backend is a deliberate improvement over the exemplar, and
  should be a stated one rather than assumed parity.
- **`docs/tech-stack.md` is stale.** It still describes Firebase as the stack. The
  newer, approved `docs/superpowers/specs/2026-08-16-gcp-games-platform-design.md`
  supersedes it, and that spec — not the older document — is the target here.
  Bakery Bash and Salary Showdown remain the model for **product flow**; their
  infrastructure is explicitly not the model for this game.

### What the approved GCP design already decides for us

From the 2026-08-16 spec, quoted because it constrains this design:

- Games are containers on Cloud Run; Frontend and API in **one service**.
- **Firestore is reached server-side only** (`@google-cloud/firestore`), never via
  the client SDK.
- **SSE** pushes round transitions; polling is the fallback. WebSockets are not in
  the baseline.
- **AI agents fill empty player seats** so a session works at any class size.
- Bakery Bash is *"the only legacy-generation game"*; Salary Showdown is slated for
  a port.

The first three points are the architecture this document specifies. The fourth is
the one place this game does not match the baseline, and it is a *timing* gap
rather than a design gap: there is no shared platform to build on yet, so the CRE
game becomes the **first concrete implementation** of the new-generation
`game-<name>` pattern instead of a fourth consumer of it. It brings no legacy
infrastructure with it — in particular, no Firebase client SDK and no Cloud
Functions.

---

## 2. Reusable patterns to copy

Copy the **product patterns**, not the code.

| Pattern | Source | Use in CRE |
| --- | --- | --- |
| Anonymous identity + persistent rejoin | `AuthContext.tsx` | player joins with display name, no account |
| Phase-driven rendering | `PhaseRouter.tsx`, `lib/phaseOrder.ts` | `practice → round → locked → results` |
| Lobby with live roster | `LobbyWall.tsx` | funds, members, model status |
| Professor control strip | `SessionSetup`, `TimerStrip`, `AdvanceControl` | create session, open/lock/reveal/advance |
| Submission grid | `SubmissionGrid.tsx` | model + decision state per fund, `17 / 18` |
| Seat management | `SeatPanel.tsx` | reassign a locked-out student to their fund |
| Projection walls | `bigscreen/*` | lobby code, live timer, winners, standings, finale |
| Pure-function modules with unit tests | `app/src/lib/*.test.ts` | money, phases, standings, submission lights |
| Integration tests per screen | `app/src/itest/*.itest.tsx` | one per route |
| Race-condition tests | `backend/functions/test/advance-race.test.js` | double-advance, double-submit |
| Hidden data held server-side | `backend/functions/src/data/hidden.json` | reserve prices, future outcomes |
| Golden fixtures pinning engine output | `test/fixtures/engine_parity.json` | the engine service contract |

---

## 3. Architecture

```
   STUDENT / PROFESSOR BROWSER
   React 19 + TS + Vite
        │
        │  HTTPS + SSE  (polling fallback).  No Firebase client SDK.
        │  Signed HttpOnly cookie session.
        ▼
   CRE GAME SERVICE                         Cloud Run
   Node 22 + TypeScript + Fastify
        │
        ├── Firestore (Native)               SERVER SIDE ONLY
        │   @google-cloud/firestore          no client listeners, no rules-based
        │                                    security model for game state
        │
        └── CRE PYTHON ENGINE                Cloud Run, private
            │  IAM / OIDC, server-to-server   browser may NEVER call this
            ▼
        this repo's verified adjudicator, unchanged economics
```

### The one rule that makes the later port mechanical

> **The browser talks to the game service and nothing else. The game service
> writes Firestore; the browser observes state through `GET /events` (SSE).**

There is no Firestore client SDK in the browser and no client-side listener. The
client holds no game state it did not receive from an API response, so it has
nothing to keep in sync and nothing to leak. When the game moves into the shared
platform, the persistence layer and the SSE route move with it unchanged, because
none of the game logic was ever in the client or in the transport.

### Why this also fixes the security problem

The CRE game's integrity rests on information the player must never see: the
**seller's reserve price** on each property, and every **realised future outcome**.
In a client-database design those live one rules mistake away from the browser.

With the engine wrapped as a service, the reserve and the outcomes are **computed
inside the engine and never returned until the round is revealed**. The client
cannot leak what it was never sent. This is a correctness argument for decision 2,
not only a maintenance one, and it is the single largest risk reduction in the
design.

---

## 4. The engine service contract

The engine keeps its economics **exactly as they are** — deal costs, capital
reserves, interest, the five-channel NAV identity, everything in
`docs/GAME_ECONOMICS.md`. No rebalancing, no porting.

### 4.1 The one real engine-side job: a serialisation boundary

`GameManager` is stateful: it owns the pool, the round machine, the market history
and every fund's portfolio in memory. Cloud Run scales to zero and restarts
freely, so the engine must be **pure per call**.

Recommended shape: the Node API owns persistence; the engine is a function of
`(seed, round, decisions, prior state)` → `(outcomes, next state)`. Both halves
are small and JSON-serialisable:

- **Fund state in:** cash, debt, holdings `[{property_id, purchase_price, debt, type, submarket, current_noi, current_value}]`, cumulative channels.
- **Round state in:** round number, scenario, market state, the four offered property ids.
- **Out in:** per-property auction results, per-fund updated state, revealed property outcomes, the five-channel bridge, and the leaderboard.

The pool itself must **not** be passed over the wire. It is regenerated
deterministically inside the engine from `seed`, which `generate_properties()` and
`_generate_property_pool()` already guarantee.

This is the main piece of engine work. It is additive: a thin adapter plus a
`to_state()` / `from_state()` pair, with the existing 284 tests unchanged.

### 4.2 Endpoints (implemented, Phase 0)

```
GET  /v1/health             liveness + version identity for CI smoke tests
GET  /v1/bundles            datasets a professor may choose (never seeds)
POST /v1/create-game-state  bundle_id, teams[] -> state + public round one
POST /v1/open-round         state -> next state + that round's public deals
POST /v1/resolve-round      state, decisions[] -> state + revealed results
                            + analytics + rejected decisions
POST /v1/finalize-game      state -> standings + analytics + ten-question debrief
```

`/v1/finalize-game` is a **read-only view**, not a second resolution step: every
number it reports comes from history `resolve-round` already recorded. It is
separate because the debrief has a different *audience* from the round loop, not
because it computes anything new — so it is safe to call repeatedly, and safe to
call before the game is complete.

Auth: Cloud Run IAM / OIDC, server-to-server, exactly as `docs/engine-api.md`
does for huginX. No API keys, nothing to rotate, and no route a browser can reach.

**The engine's response to `resolve-round` is not the response the browser gets.**
`resolve-round` returns trusted server state plus public results; the game service
projects that state into student-safe DTOs (§4.4). That split is deliberate: the
engine is allowed to be truthful, and the projection is the only thing that decides
what a player sees.

### 4.3 Parity strategy — reshaped by decision 2

There is **no TypeScript economics to keep in parity**, so the parity-test class of
bugs disappears. What replaces it:

1. **Contract fixtures, not parity fixtures.** Freeze ~25 engine responses
   (request JSON → response JSON) across the states that matter: practice, valid
   bid, below reserve, LTV tie-break, insufficient equity, deal costs, reserves,
   interest, rounds 1→4 persistence, final NAV, debrief. These are generated *from*
   the Python engine, so they define the contract and can never disagree with it.
2. **Contract tests on both sides.** The Node API asserts it sends valid requests
   and parses real responses; the Python service asserts the frozen fixtures still
   reproduce byte-identically. A contract change fails one of the two loudly.
3. **No client arithmetic on outcomes.** The client may format, sort and chart
   server numbers. It may not compute NAV, returns, or P&L channels. This is the
   rule that keeps drift structurally impossible rather than merely tested for.

### 4.4 The projection boundary

`service/engine_api/public.py` is the only module that builds a player-visible
payload, and it builds each one by **naming** the fields it exposes. Nothing is
produced by copying the engine snapshot and deleting keys: subtraction fails open
the first time a field is added, and the field that would leak is the seller's
reserve.

Every public serialiser ends by calling `visibility.assert_no_leaks(...)`, which is
enforced at runtime rather than documented and hoped for. The classification of
every field is in `docs/CRE_DATA_VISIBILITY.md`; the tests that prove the public
payloads never carry a reserve or a future outcome are in
`tests/test_engine_api_visibility.py`.

### 4.5 Bundles — why a professor never chooses a seed

A student's model is trained against **one** property pool. A different seed keeps
the property ids (`OC-OFFI-06`) and changes what they mean, so a model built for
one pool predicts confident nonsense for another, silently, in class.

The unit of choice is therefore a **bundle**: a frozen, versioned pairing of a
seed, a candidate pool, a packet, and a set of economic coefficients.

```json
{
  "bundle_id": "real605-fall26-v1",
  "display_name": "REAL 605 — Fall 2026",
  "engine_version": "0.1.0",
  "economics_version": "2026.09.1",
  "economics_digest": "82b42656e8ab6802…",
  "packet_version": "real605-fall26-v1",
  "seed": 20240331,
  "candidate_pool_hash": "24240d70b01ba2c2…",
  "schema_version": 1
}
```

`economics_digest` is a SHA-256 over every frozen economic coefficient, and
`candidate_pool_hash` is a SHA-256 over the pool's decision-relevant fields. Both
are asserted by tests, which turns two claims that used to live in prose — *“the
economics did not change”* and *“the pool did not change”* — into mechanical checks.

Consequences, all enforced rather than documented:

- `/v1/create-game-state` accepts `bundle_id` and **has no seed parameter**.
- `verify_bundle_integrity()` re-derives both hashes from the live engine and
  refuses a bundle that no longer matches.
- A team's submission must cover the bundle's pool exactly. Missing or unknown
  property ids is a **hard rejection before play**, not a warning:

  > This model was built for a different property dataset. Download the correct
  > REAL 605 packet or create a session using the matching bundle.

---

## 5. Firestore data model

**Reached server-side only**, by the game service, via `@google-cloud/firestore`.
There is no browser security-rules architecture for game state, because the browser
never opens a Firestore connection at all. The collection layout below is therefor
a *server* layout: it holds hidden data (reserves, future outcomes) precisely
because nothing unprivileged can read it.

All documents are small.

```
sessions/{sessionId}
    name, joinCode, professorUid, createdAt
    mode: "team" | "individual", maxTeamSize
    rounds: 4, practiceEnabled: true, roundSeconds: 480
    bundleId: "real605-fall26-v1"   <-- the professor chooses a DATASET, see R3.
                                        The seed comes from the bundle and is
                                        never a request field.
    phase: lobby | model_checkin | practice | round | locked | results | finale
    currentRound: -1..3, timerEndsAt

sessions/{sessionId}/members/{uid}
    displayName, fundId, joinedAt

sessions/{sessionId}/funds/{fundId}
    name, memberUids[], createdBy
    modelStatus: none | validated | locked
    modelName, modelLockedAt, forecastSummary {mae, mean_upside, ...}
    policy {maxBidRule, targetLtv}      <-- POLICY, not forecast
    nav, cash, debt, assets, rank, lastSeenAt

sessions/{sessionId}/models/{fundId}        (one doc per fund, not per prediction)
    modelName, lockedAt, rows: [{property_id, predicted_fair_value,
        predicted_noi_growth, probability_of_downside, confidence}]
    policyDefaults: {max_bid, target_ltv}

sessions/{sessionId}/rounds/{round}/deals/{propertyId}
    The single property DTO from the engine's public projection: identity, physical,
    operations, capital markets, and the game's own cost rates (acquisition_cost_rate,
    capital_reserve_rate) so the underwriting drawer can be honest about charges.
    NO reserve_price, NO future outcome. See docs/CRE_DATA_VISIBILITY.md.

sessions/{sessionId}/rounds/{round}/decisions/{fundId}
    items: [{property_id, action, bid, ltv}], submittedAt
    Served only to the owning fund and to the professor. Opposing bids are never
    published, at any phase: the auction is sealed.

sessions/{sessionId}/rounds/{round}/results/{propertyId}
    winner, winning_bid, reserve_revealed, realized_value, noi_growth
    Emitted only once the round is resolved. The engine physically does not return
    these fields before then, so this is a scheduling question, not a rule.

sessions/{sessionId}/rounds/{round}/pnl/{fundId}
    value_channel, noi_income, interest, deal_costs, reserves, nav

sessions/{sessionId}/events/{eventId}
    round, phase, message, at, actorUid
```

### Two data-model decisions worth stating

- **One `models/{fundId}` document, not 120.** 120 prediction documents × 70
  students is 8,400 writes and as many reads per grading pass. A single document
  per fund is ~10× cheaper and atomic. Well under the 1 MiB document limit.
- **The underwriting fields are transmitted by the engine, not read from a CSV.**
  Today the rich columns exist in `data/synthetic/*.csv` and in `PropertyMarket`
  is a 14-field subset. The engine service is the right place to merge them, so
  the game never has two representations of the same building. See risk R5.

---

## 6. Route map

Mirrors Salary Showdown's shape, so the patterns transfer.

```
/                 Landing        HOST A SESSION | JOIN WITH CODE | TRY DEMO
/join             Join           display name, 6-char code, individual | team, pick/create fund
/lobby            Lobby          roster, per-fund model status, "waiting for professor"
/model            Model check-in upload CSV, validation report, LOCK MODEL
/play             PhaseRouter    renders by session.phase, never by client guess
  /play/round/:n                 deal cards, underwriting drawer, decision submit
  /play/locked                   submitted, "17 / 18", no opposing bids visible
  /play/results/:n               winners, revealed reserve, model/decision/outcome badges, P&L bridge
/standings        Standings      game board | analytics board (separate tabs, never blended)
/finale           Finale         winner, best model, best decisions, most overrides, leverage, luck
/professor       Professor      gated; session setup, timer, submission grid, controls
/bigscreen        Big Screen     projection; no controls (lobby | round | reveal | standings | finale)
```

`/play` must be driven entirely by `session.phase`. A client that decides its own
phase will disagree with the professor's screen exactly once, in front of a class.

---

## 7. Model-upload contract

This is where the teaching thesis is enforced, so the naming is load-bearing.

### Three distinct concepts, never blended

| Concept | Named in UI | Authored | Fields |
| --- | --- | --- | --- |
| **FORECAST** | *Your team's pre-class forecast* | before class, in Python/R/Excel | `predicted_fair_value`, `predicted_noi_growth`, `probability_of_downside`, `confidence`, `model_name` |
| **POLICY** | *Your investment policy* | derived from the analysis | `max_bid`, `target_ltv` |
| **DECISION** | *Your decision* | in the live round | `action`, `bid`, `ltv`, plus `bid_override`, `ltv_override` |

> `max_bid` and `target_ltv` are **policy**, not predictions. The UI must never
> call them predictions.

### Upload flow

1. `submitModel({sessionId, fundId, modelName, csv})` — callable function.
2. Server validates against **this session's** candidate pool:
   - exact property-id set match; no duplicates, no missing;
   - numeric and finite; `0 <= probability_of_downside <= 1`; `predicted_fair_value > 0`;
   - `0 < target_ltv <= 1`, and per-property `<= max_ltv`;
   - **no forbidden target columns present** (`next_year_value`, `next_year_noi`,
     `transaction_price`, `transaction_cap_rate`, `next_year_noi_growth`).
3. Returns a machine-readable report: `{ok, errors[], warnings[], summary{}}` where
   summary carries descriptive stats for the check-in screen (properties matched,
   mean predicted upside vs ask, forecast dispersion) — **not** accuracy, because
   no outcome is known yet.
4. On success: `modelStatus = validated`; the fund presses **LOCK MODEL** →
   `locked`, write-once. Rules and the function both refuse later writes.
5. Demo mode: `modelName = "DEMO FORECAST"` and the UI states it is preloaded. Never
   present demo predictions as the reviewer's work.

### Contract change this implies — flagged, not yet made

The shipped packet (`student_packet/prediction_submission_template.csv`) currently
requires `max_bid` and `target_ltv` in the same file, because
`src/game/submission.py::validate_game_submission` validates them there. That
conflates policy with forecast.

**Recommended, minimal path:** keep the CSV as it is (no packet regeneration, no
break for existing students), and treat `max_bid`/`target_ltv` as *policy defaults
carried in the file* that the student may override in-game. The UI labels them
policy; the server records the delta as `bid_override` / `ltv_override`.

**Later refinement:** drop them from the CSV and require an in-game policy step.
That is a better lesson and a packet-format change, so it should be its own
decision, not a side effect of the port.

---

## 8. Migration phases

Each phase ends in something demonstrable. No phase starts before the previous one
is coherent.

| Phase | Deliverable | Done when |
| --- | --- | --- |
| **0 — Engine service** ✅ | `service/engine_api/` (Fastify-era FastAPI container), serialisation boundary, bundles, visibility boundary, Dockerfile, contract fixtures generated from Python | a round can be resolved over HTTP, replay deterministically, and leak nothing; all 284 existing tests still pass |
| **1 — Repo + identity** | new repo, game-service scaffold, join codes, cookie sessions, lobby | 3 browsers join one session by code and see each other |
| **2 — Model check-in** | upload contract, validation report, lock | the shipped student fixture uploads, validates, and locks; a bad CSV returns readable errors |
| **3 — Round shell** | phase router, deal cards, underwriting drawer, decision submit/lock | four rounds play end to end against the real engine |
| **4 — Results** | winners, revealed reserve, badges, P&L bridge, standings + analytics tabs | NAV on screen equals NAV from `verify_demo_flow` for the same bundle and decisions |
| **5 — Professor + bigscreen** | controls, submission grid, timer, projection walls | a round is run start to finish with no terminal |
| **6 — Finale** | winner, best model, override count, leverage, luck | the ten debrief questions render from engine output |
| **7 — Load + hardening** | 70 concurrent joiners, duplicate/race tests, SSE reconnect, cookie rejoin | races in `advance-race` style pass; reconnect mid-round loses no state |
| **8 — Platform adoption** | move the container under the shared hub; swap any local seam for the shared service | deferred until the baseline exists; §3 is what keeps it a port, not a rewrite |

---

## 9. Risks, ranked

**R1 — Reserve price and future outcomes leaking to the client.** *Highest
consequence.* Mitigated structurally by the engine service; the client never
receives hidden state. Any move that puts economics or hidden state in Firestore
reintroduces it.

**R2 — `GameManager` is stateful; Cloud Run is not.** The serialisation boundary
(§4.1) is the real engineering risk in Phase 0. If the engine is left stateful, the
service works in dev and fails on cold start under load.

**R3 — Sessions must be dataset-pinned, or every student's model breaks.**
Discovered during this project: the packet and the pool are both generated from a
seed, and the submission guard already refuses a mismatched pool. A professor
creating a session with a fresh random seed would invalidate **every** pre-built
student model — silently, in class. This is **mitigated in Phase 0**: a session
selects a *bundle* (`real605-fall26-v1`), the seed is bundle metadata, and the
create-state call has no seed field to abuse. A model that does not match the
bundle's candidate pool is **hard rejected before play**, with no warning path.
See §4.5.

**R4 — 70 concurrent players.** Duplicate joins, double submission, double advance,
timer races. Salary Showdown's `advance-race.test.js` and `create-team.test.js` are
the precedent to copy.

**R5 — Two representations of the same property.** Today `PropertyMarket` carries
14 fields while the dataset CSVs carry the underwriting columns, and
`pages/deal_room.py` renders from the CSV. If the live game reads CSVs directly, the
game and the packet can disagree. The engine service should be the only source of
property data.

**R6 — `capex_need` means two things.** `pages/deal_room.py` displays a
"Capex need" figure per property that the engine **never charges**; the engine
charges a type-based capital reserve instead. Surfaced to a practitioner this reads
as an inconsistency. Resolve by relabelling or by hiding it — but the new game must
not inherit the ambiguity.

**R7 — Anonymous identity is device-bound.** Clearing storage loses a seat.
Mitigated by join code + roster claim + `SeatPanel`-style professor reassignment.

**R8 — Building ahead of the shared platform.** The hub, shared services and agent
players do not exist yet, so this game implements its own service container. The
exposure is small and one-directional: the container's *interfaces* (HTTP + SSE +
server-side-only persistence) are the approved baseline's, so adoption is a
configuration change rather than a rewrite. The one thing to resist is inventing
solutions the platform will later provide — auth, leaderboards, agent players —
rather than leaving a seam for them.

**R9 — Do not let the client compute.** Any NAV, return, channel or ranking
arithmetic in TypeScript re-creates the parity problem decision 2 just removed.

---

## 10. Files and directories to create

New repository. Engine changes land **here**, in `cre-investment-sim`.

### In this repo (engine service, Phase 0 — **built**)

```
service/engine_api/__init__.py
service/engine_api/app.py          FastAPI app; the routes in §4.2
service/engine_api/bundles.py      bundle loading, economics digest, pool hash
service/engine_api/serde.py        GameManager <-> JSON; the boundary in §4.1
service/engine_api/engine.py       stateless operations; the only orchestrator
service/engine_api/contracts.py    Forecast / Policy / Decision types (§7)
service/engine_api/public.py       the student-safe projection (§4.4)
service/engine_api/visibility.py   field classification + assert_no_leaks (§4.4)
config/bundles/real605-fall26-v1.json   the dataset a professor selects
Dockerfile.engine                  python:3.11-slim, non-root, Cloud Run ready
tests/contracts/engine_api/*.json  frozen request/response pairs, generated FROM
                                   the engine; the executable contract (§4.3)
scripts/export_engine_fixtures.py  regenerates those fixtures
scripts/serve_engine.py            local uvicorn entrypoint
```

---

## 12. Phase 0 — implementation status

What exists now, and what it is proven to do:

| Item | Where |
| --- | --- |
| Versioned bundle + integrity check | `service/engine_api/bundles.py`, `config/bundles/` |
| Lossless JSON state, incl. the RNG bit-state | `service/engine_api/serde.py` |
| Hidden-information boundary | `docs/CRE_DATA_VISIBILITY.md`, `service/engine_api/visibility.py` |
| Forecast / Policy / Decision types | `service/engine_api/contracts.py` |
| Single property DTO (one representation, not two) | `service/engine_api/public.py::public_deal` |
| `capex_need` terminology resolved | relabelled `indicative_capex_exposure`, with a note |
| HTTP surface | `service/engine_api/app.py` |
| Contract fixtures | `tests/contracts/engine_api/` |
| Container | `Dockerfile.engine` |

The point of Phase 0 is not that there is an API. It is that **the Streamlit app can
be replaced without translating, weakening, or re-deriving the simulation**. The
economics did not move, and they are the same code that 284 tests already cover.

### In the new repo (game, Phases 1–7)

```
docs/ARCHITECTURE.md             this document
docs/ENGINE_CONTRACT.md          endpoint shapes, auth, error codes
Dockerfile                       Node 22 game service on Cloud Run
service/                         Node 22 + TS + Fastify — frontend AND API, one
                                 container, per the platform baseline
  src/server.ts                  HTTP + SSE (GET /events), polling fallback
  src/auth.ts                    signed HttpOnly cookie sessions; professor
                                 passcode -> professor-scoped cookie
  src/engine.ts                  IAM/OIDC client for the Python engine; the
                                 browser never calls the engine directly
  src/store.ts                   Firestore via @google-cloud/firestore, server-side
                                 only; no client SDK, no browser security rules
  src/session.ts                 create, join, assign seats
  src/model.ts                   submission contract, validation, lock
  src/round.ts                   decision submit, lock, resolve via engine
  src/standings.ts
  src/{session,model,round,advance-race}.test.ts
app/                             React 19 + TS + Vite
  src/App.tsx
  src/main.tsx
  src/api/client.ts              fetch + EventSource; the ONLY network surface
  src/contexts/{SessionContext,GameContext,ProfessorContext}.tsx
  src/components/PhaseRouter.tsx
  src/components/ui/{PhaseHeader,StatusChip,MetricCard,SectionCard,ErrorNotice,Timer}.tsx
  src/components/deal/{DealCard,DealGrid,UnderwritingDrawer,DecisionTicket}.tsx
  src/components/model/{ModelCheckIn,ValidationReport,ForecastPanel,PolicyPanel}.tsx
  src/components/professor/{SessionSetup,SubmissionGrid,TimerStrip,AdvanceControl,SeatPanel}.tsx
  src/components/bigscreen/{LobbyWall,RoundWall,RevealWall,StandingsWall,FinaleWall}.tsx
  src/components/results/{DealResult,ModelDecisionOutcomeBadge,PnlBridge}.tsx
  src/lib/{phaseOrder,formatMoney,submissionLights,liveStandings}.ts
  src/lib/*.test.ts
  src/pages/{LandingPage,JoinPage,LobbyPage,ModelPage,PlayPage,StandingsPage,FinalePage,ProfessorPage,BigscreenPage}.tsx
  src/itest/*.itest.tsx          one per route
  public/assets/properties/{industrial,office,multifamily,retail}.jpg
```

Note what is **absent**: no `firestore.rules` (the browser never reaches Firestore),
no `firebase.json` hosting target for game state, and no `functions/`. Frontend and
API ship in one image, which is what the baseline specifies.

---

## 11. What happens to the Streamlit app

Unchanged and retained, per the standing rule: it remains the engine's reference
implementation, the analytics QA surface, and the debugging harness. This repo
gains the engine service and keeps all 284 tests, the balance harness, and
`docs/GAME_ECONOMICS.md`.

**The new game becomes authoritative for classroom play only after Phase 4** —
that is, once NAV on the new screen equals NAV from `verify_demo_flow` for the same
bundle and the same decisions. Until then, Streamlit is the game and the service is
a parallel surface.
