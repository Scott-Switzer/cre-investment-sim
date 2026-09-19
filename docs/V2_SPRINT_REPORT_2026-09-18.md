# V2 sprint report — September 18, 2026

> **Later the same day:** the management layer was wired into the classroom UI and
> verified end to end against the real stack — see §9. Priorities 1 and the
> professor-facing wording in §8 were superseded by that pass.

Branch `feat/cre-management-v2`, branched from `c88e848` ("allow classroom play
without model CSV"). Everything below is measured on this branch, on the machine
that built it. Anything not measured says so.

Companion documents: `docs/SEPT18_REQUIREMENTS.md` (the professor's meeting,
classified), `docs/V2_PRODUCT_SPEC.md` (implementation-grade spec),
`docs/CLOUD_RUN_DEPLOYMENT.md` (infrastructure path),
`artifacts/sept18-gameplay/` (the Slack deliverable).

---

## 1. What shipped today

| Artifact | Path | State |
| --- | --- | --- |
| Self-contained gameplay HTML for Slack | `artifacts/sept18-gameplay/fenrix-cre-game-overview.html` | Done, verified in a browser viewport |
| Slack-ready message | `artifacts/sept18-gameplay/SLACK_MESSAGE.md` | Done |
| September 18 requirement record | `docs/SEPT18_REQUIREMENTS.md` | Done |
| V2 product/gameplay spec | `docs/V2_PRODUCT_SPEC.md` | Done, updated to the implemented design |
| Course-tier configuration | `src/game/manager.py` (`CourseProfile`, `COURSE_PROFILES`) | Implemented |
| Management layer (engine) | `src/game/adjudicator.py` | Implemented, tested |
| Management layer (service API) | `service/engine_api/*`, `config/bundles/*` | Implemented, tested |
| Engine + API tests | `tests/test_management_layer.py`, `tests/test_engine_api_management.py` | 32 new tests, green |
| Cloud Run path | `docs/CLOUD_RUN_DEPLOYMENT.md` | Prepared, deliberately not executed |

## 2. Requirement classification

Repeating the classification from `docs/SEPT18_REQUIREMENTS.md` because it decides
what was allowed into the core implementation:

* **CONFIRMED** — HTML gameplay overview today; management layer as the V2
  direction; model ladder (valuation → vacancy → rent); ~5 rounds; one coherent
  lifecycle; course tiering by configuration (605 / 310 / 220); real+synthetic
  data mix; Cloud Run as the event target; checkpoint/recovery for a real class.
* **STRONGLY IMPLIED** — deterministic (not LLM-driven) round resolution;
  reconnect-safe state; professor control-plane completeness; anonymization that
  keeps relationships but hides identity.
* **PROPOSED / OPTIONAL** — spatial map; tenant agents; live external data refresh
  (Vanguard); sell/refinance mechanics; deeper multi-model scoring.
* **DEFERRED** — everything in PROPOSED until the 605 classroom run has happened.

## 3. Decisions taken (and why)

1. **Management is a cash-flow layer, not a re-underwriting.** An operating year
   costs income and cash; it does not move the asset's NOI basis or value. The
   first implementation did move them, which broke the existing
   "what a fund is told happened equals what the engine applied" invariant and
   would have required a sixth cash channel for the debrief's bridge to keep
   adding up. The reshaped version keeps both identities exact and is tested in
   `tests/test_management_layer.py`.
2. **605 ships with the operating year off.** REAL 605 is the first real-world
   test, so its tier is the rehearsed game: one model, no management surface, and
   round resolution byte-identical to the pre-V2 engine. 310 is where the full
   three-stance layer lives; 220 runs the operating year at STANDARD with no
   stance decision.
3. **The tier is recorded, not assumed.** It is written into the config inside the
   session snapshot, echoed in the public config block, and used to rebuild the
   adjudicator on restore. A 605 session cannot quietly become a 310 session
   halfway through a class.
4. **The management coefficients are inside `economics_digest()`.** A retuned shock
   probability now fails the bundle's integrity check instead of reaching a
   classroom. That bumped the frozen economics to `2026.09.2`; the *gameplay*
   numbers in the frozen contract are unchanged (measured, §5).
5. **A v2 snapshot still restores.** Every field v2 lacks defaults to what a v2
   session was actually running, so a deploy can land mid-class. v1 and future
   schemas are still refused rather than guessed at.
6. **Round accounting sums holdings in property-id order.** Canonical JSON
   re-sorts keys, so an order-dependent float sum drifts by an ULP between a
   replay and the run that produced it. The frozen-contract fixture for round 4
   caught this; sorting fixed it and the fixtures are now generated
   byte-identically on repeated runs.

## 4. Implementation summary

**Engine (`src/game/adjudicator.py`)**

* `resolve_operating_year(...)` — one pure, seeded function per owned building per
  round, keyed on `(seed, property_id:ops, round_number)`. Draws a tenant
  interruption (Bernoulli), upkeep (Bernoulli over a per-type rate) and a market
  rent miss (uniform to a stance cap) from one generator in a fixed order.
* `Adjudicator.apply_management_year(team, market_state, round)` — resolves every
  holding, charges upkeep to cash/`cumulative_reserves`, and returns the year's
  operating shortfall, which is netted out of the income the fund collects.
* `Adjudicator.management_enabled` — when the tier leaves the layer off, none of
  the above runs and the round is the pre-V2 round.
* `TeamState.management_decisions` (consumed and cleared each round) and
  `TeamState.operating_history` (per round, per building).

**Configuration (`src/game/manager.py`)**

* `CourseProfile` + `COURSE_PROFILES` (`605`, `310`, `220`) and
  `course_profile(mode)`, which refuses an unknown tier.
* `GameConfig.course_mode` (default `605`) and `GameConfig.management_enabled`
  (`None` = whatever the tier declares), with `management_active` resolved once.
* `GameManager.set_management_stances` — legal only while the round is open, only
  for buildings the fund owns, only for stances the tier accepts, and not at all
  when the tier does not simulate an operating year.

**Service (`service/engine_api/`)**

* `ManagementStance` contract; `management_stances` on the resolve request;
  `rejected_stances` on the response, so a refused posture is reported to the
  sending fund instead of crashing a round.
* `POST /v1/create-game-state` accepts an optional `course_mode` /
  `management_enabled`; the tier travels in the snapshot.
* `public_round` publishes the tier and every management coefficient;
  `team_private_view` carries the fund's own operating history, leak-checked like
  every other view.
* `serde` schema **3** (`course_mode`, `management_enabled`, `management_decisions`,
  `operating_history`) with `READABLE_SCHEMA_VERSIONS = (2, 3)` and the adjudicator
  rebuilt at the restored config's tier.
* `bundles`: optional `course_mode` / `management_enabled` on a bundle; the
  published bundle declares `605` + `management_enabled: false`; management
  coefficients in `economics_digest()`.

## 5. Gates actually run

| Gate | Result | Evidence |
| --- | --- | --- |
| Python suite (no `tests/e2e`) | **487 passed**, 5 warnings, 17s | `uv run python -m pytest tests/ -q --ignore=tests/e2e` |
| New engine tests | 19 passed | `tests/test_management_layer.py` |
| New service tests | 14 passed | `tests/test_engine_api_management.py` |
| Frozen engine contract | 107 passed | `tests/test_engine_api_contract.py` |
| Fixture determinism | byte-identical across two independent exports | `shasum` over `tests/contracts/engine_api` before/after a re-export |
| Regression vs branch point | **67 of 73** fixture JSONs identical once the new V2 keys are dropped; the other 6 differ only in `serde_schema_version`, `economics_version`, `economics_digest` and the bundle description — no gameplay number moved | scripted JSON diff against `git show HEAD:...` |
| Node typecheck | green (`tsconfig.json` + `client/tsconfig.json`) | `npm run typecheck` |
| Node unit suite | 127 passed, 15 skipped (Firestore emulator not running), 5.8s | `npm test` |
| Docker image builds | **NOT RUN** | Docker CLI 29.5.2 is installed but the daemon is not running: `Cannot connect to the Docker daemon at unix:///Users/.../.docker/run/docker.sock` |
| Playwright E2E (`tests/e2e`) | **NOT RUN** | Needs the Docker-backed stack; same blocker |
| Deployed smoke (Cloudflare) | **NOT RUN** | No deploy from this branch, by design |
| 70-user load test | **NOT RE-RUN** | Last validated at `507fda3`; the 605 tier leaves round resolution unchanged (see the fixture-identity evidence above), so the measured cost should be identical — but that is an argument, not a measurement |

## 6. Classroom resilience

* **Checkpoint.** Every commit already rewrites the full gzipped engine snapshot
  onto the session document, and each resolved round's `RoundResult` is stored on
  the round record. V2 adds the operating-year record per building per round, so
  the debrief can explain a NAV move rather than only report it.
* **Restore.** A pre-V2 (v2) snapshot restores and finishes on this build: the
  missing fields default to the 605 tier with no stances and no history, which is
  what a v2 session was running. Restore-to-a-chosen-round remains a documented
  procedure, not a button (unchanged this sprint; see
  `docs/V2_PRODUCT_SPEC.md` §6).
* **Professor control plane.** Unchanged by V2: phase machine, timers, live
  monitoring, check-in state, export ZIP, bigscreen, disconnect visibility. The new
  `operating_history` field is available to the monitoring views; **the
  per-fund stance summary panel is not built yet.**
* **Concurrency.** Unchanged and still the source of truth for correctness:
  revision-guarded session mutations and idempotent round resolution.

### Load / QA plan (shape, for the next milestone)

Burst-based, not uniform: 100 simulated clients across 25 funds, with spikes at
join, model check-in, bid submission, round close, leaderboard refresh and a
forced reconnect (kill the SSE stream mid-round). Record p50/p95/p99 **and** the
things that actually break a class: failed actions, duplicate writes, transaction
aborts, incorrect awards, lost state, reconnect failures. Run it against a
deployed URL, not localhost, once the images build.

## 7. Task structure (professor's Kanban request)

No GitHub project board was created: this environment has no authenticated GitHub
project access, and a decorative board is worth less than a task list that lives
with the code. Milestones are grounded in the professor's own framing (605 first
real-world test, 310 as the target run) rather than invented dates.

**NOW — September 18**
- [DONE] Gameplay HTML + Slack message
- [DONE] Requirement record + V2 spec
- [DONE] Management layer (engine + API) with tests
- [DONE] Course-tier configuration, 605 tier unchanged
- [DONE] Cloud Run path documented

**READY**
- Student-facing stance control on the deal board (engine accepts stances today)
- Professor stance summary in round monitoring
- Round checkpoint / restore-to-round procedure

**IN PROGRESS**
- Nothing (branch is at a clean, tested state)

**~3 WEEKS — multiplayer mini-game stress test**
- Burst load shape of §6 against a deployed stack
- Reconnect drill: kill an instance mid-round, confirm no loss
- Vacancy/rent model contracts wired to the stance decision

**BEFORE THE MAIN EVENT — 605 classroom test**
- Deploy the 605 tier as-is; teaching materials for one model
- Debrief template for operating-free results (no management to narrate)

**~2 WEEKS LATER — 310 target run**
- Flip a 310 bundle on, after the 605 run has validated the classroom loop

**1 WEEK BEFORE — feature freeze**
- Bug fixes and polish only

**BLOCKED**
- Docker-backed E2E and image builds: local Docker daemon not running (no
  escalation attempted; starting the user's Docker Desktop is a system action
  nobody asked for)
- Cloud Run deploy: needs the GCP project/region and the engine's IAM token path
  in `engineClient.ts`

## 8. Next three priorities

1. **Wire the stance control to a student screen** (and the professor's stance
   summary) so the 310 tier is playable end to end rather than engine-complete.
2. **Run the burst load and reconnect drill against a deployed stack** — including
   building the images once a Docker daemon is available.
3. **Validate the 605 tier in front of the class**, then decide from that evidence
   whether 605 should show a light stance surface or stay management-free.

## 9. Professor delivery pass (later on September 18)

The gap §8 called out first — engine-complete but not playable — is closed on the
branch. The 310 tier now plays through the existing React/Fastify classroom UI; no
second management app, no parallel API.

**What was wired**

- `client/src/screens/Practice.tsx` — the deal board's management section: one row
  per owned building (id, type, submarket, income, marked value, market vacancy) and
  a three-way stance control (`RUN LEAN` / `STANDARD` / `INVEST & PROTECT`) whose
  values come from the round's published `management.stances`, never hard-coded. The
  chosen stances travel with the round's decisions through the existing
  `/rounds/decision` call, and the review dialog shows them before locking.
- `client/src/screens/Results.tsx` — per-building operating feedback after the
  year resolves: approach used, tenant interruption, upkeep paid, rent effect, net
  on cash — only fields the engine already publishes.
- `client/src/screens/Professor.tsx` — course-version selection at session
  creation, and a management column in the round grid: submitted vs waiting, stances
  set, and the mix per approach.
- `src/rounds.ts`, `src/views.ts`, `src/engineClient.ts`, `src/export.ts`,
  `src/server.ts` — stance validation and forwarding, rejection surfacing, and the
  per-round stance sheet in the export.
- One copy defect fixed while testing: the shared review dialog labelled its confirm
  button "Lock practice decisions" in scored rounds; it is now phase-aware.

**How it was verified (not just unit tests)**

A real stack was run locally without Docker — the Python engine on `:8081` and the
Fastify service on `:8080` with `STORE=memory` — and driven through the browser:

1. Professor signed in, created a **310** session (course selector shows the tier).
2. Student joined, locked a model with "skip file — use on-screen inputs".
3. Round 1: bid on two listings through the UI, locked the decisions, the round
   resolved, and the fund acquired both buildings. Results showed the NAV bridge
   reconciling to the cent with no unexplained residual.
4. Round 2: the management section listed both owned buildings with income, marked
   value and market vacancy, and a segmented stance control each. Choosing
   `INVEST & PROTECT` on one and `RUN LEAN` on the other, then locking, produced in
   the professor's grid: `stancesSet 2`, tally `{INVEST & PROTECT: 1, RUN LEAN: 1}`.
5. Round 1's result screen carried the per-building table with real numbers
   (upkeep −$0.22M on the industrial, −$0.36M net on the multifamily).
6. An illegal stance (`MAX PROTECTION`) was rejected with
   "'MAX PROTECTION' is not a management stance this session accepts. Available:
   RUN LEAN, STANDARD, INVEST & PROTECT."
7. The export archive contains `round_management_stances.csv`
   (`round,fund,property_id,stance`).
8. **605**, same stack: the round board renders no management surface at all — no
   panel, no rows, no "310 course" label — and the confirm button reads "Lock
   decisions". **220** publishes `enabled: true, hasStanceChoice: false`: the
   operating year runs at the standard approach with no posture UI.

**Gates run on the final code state**

| Gate | Result |
| --- | --- |
| `npm run typecheck` (server + client tsconfigs) | pass |
| `npx vitest run` (service) | 140 passed, 15 skipped (Firestore emulator down) |
| `npm run test:client` | 29 passed |
| `npm run build` (server + client bundle) | pass |
| Python engine + frozen contract suite | pass (unchanged by this pass) |
| Docker-backed E2E / load | NOT RUN — no Docker daemon in this environment |

**Updated next three** (replacing §8 for the next working session)

1. Deploy the branch to a preview environment (Cloudflare stage or a Cloud Run
   service) and run the burst load plus the reconnect drill against it, so the
   classroom-resilience claims rest on a deployed stack rather than localhost.
2. Run the 605 tier in front of the class, then decide from that evidence whether
   605 stays management-free or gains a light stance surface.
3. Ship the vacancy and rent model check-ins as real, decision-linked model types
   for 310 — the ladder is designed and the engine reads predictions, but the
   310 round still plays with neutral forecasts when a team skips the file.
