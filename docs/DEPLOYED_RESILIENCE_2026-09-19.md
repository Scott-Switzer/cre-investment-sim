# Deployed classroom resilience — 2026-09-19

The milestone: prove the classroom game works on the **real deployed stack** under
multi-user load, reconnects, persistence, professor actions and course isolation —
not on localhost.

Everything below was produced by driving `https://cre-game-preview.scswitzer.workers.dev`
over its public HTTP API with `scripts/classroom_load.mjs`. No Docker, no browser, no
local server. Raw per-request samples are written to `artifacts/resilience/<run>/`
(untracked; regenerate with the harness).

**Verdict: PARTIAL.** Correctness and durability are good — no state corruption, no
lost seat, no double-resolved round, exact NAV reconciliation. One blocker remains and
it is not a gameplay defect: **the deployed stack cannot seat a classroom.** 46 of 50
concurrent joins time out at 60 seconds.

---

## 1. Source control and deployment

| | |
| --- | --- |
| V2 branch | `feat/cre-management-v2` @ `61263ad` |
| V2 merge | PR **#2**, squash-merged as `cceedb0` (tree identical to `61263ad`) |
| Deploy | Cloudflare Workers Build on `cceedb0`, deployment `36e28bf6` at 05:50:07Z |
| Resilience fixes | PR **#3**, squash-merged as `a63a281` (tree identical to `a63c0b8`) |
| Resilience deploy | Cloudflare Workers Build on `a63a281` **succeeded**, deployment `325d56c5` at 11:58:50Z |
| Staging | `https://cre-game-preview.scswitzer.workers.dev` |
| Store | Firestore (`/healthz` → `store: firestore`), not memory |

Deployment is Git-integrated: pushing to `main` runs `wrangler deploy` and rebuilds the
container. Per Cloudflare's docs, **preview** builds run `wrangler versions upload`, which
does not update container images — that is why the check on a pull request fails while the
same build on `main` succeeds. Nothing was deployed by hand.

Provenance is strong but not a literal SHA string: the deployed `/healthz` carries a
`build.sha` field (so the running code is the merged code), the deployment is the one the
Git build for that commit produced, and the live engine reports V2-only values
(`economics_version 2026.09.2`, `serde_schema_version 3`). `build.sha` is `null` because
Cloudflare's build environment does not export `WORKERS_CI_COMMIT_SHA` into the container
as a var. The one-line follow-up is to set the deploy command to
`wrangler deploy --var GIT_SHA:$WORKERS_CI_COMMIT_SHA` in the dashboard; that cannot be
done from the repository.

**Docker Desktop was never needed.** It is broken on this machine — root cause found and
unrelated to the repository: the host data volume is 98% full (4.8 GB free), and the VM
dies mid-boot with `no space left on device`. The Git-integrated build runs Docker inside
Cloudflare's own build platform, so local Docker is not on the deployment path at all.

## 2. Gates

| Gate | Result |
| --- | --- |
| Python | **487 passed** |
| Service (vitest) | **164 passed, 0 skipped** |
| Firestore emulator | **16 passed** (previously skipped entirely: the emulator was not running) |
| Client (vitest) | **52 passed** |
| Typecheck / production build | pass |
| Docker E2E | NOT RUN — ENVIRONMENT |
| Cloud Run | not attempted — post-delivery, per scope |

The previously skipped Firestore suite now runs and is the reason one of the defects
below was fixable with confidence: it exercises the real database, not a Map.

## 3. Course tiers, on the deployed build

Read from the round payload the service publishes, not from the UI:

| Tier | `management.enabled` | `hasStanceChoice` | Stances published |
| --- | --- | --- | --- |
| 605 | `false` | `false` | none |
| 310 | `true` | `true` | `RUN LEAN`, `STANDARD`, `INVEST & PROTECT` |
| 220 | `true` | `false` | none (plays `STANDARD`) |

Refusals are exact and name the reason. On 310 an invented stance returns 400 —
`'MAX PROTECTION' is not a management stance this session accepts. Available: RUN LEAN,
STANDARD, INVEST & PROTECT.` On 605 and 220 a stance returns 400 —
`this session is playing the 605 course tier, which has no management decision`. After
either refusal the fund can still submit its ordinary decision.

Management feedback is real and per building. From a completed live 310 game, the owning
fund's `portfolio.operating_history` carries one row per round per building:

```json
{ "property_id": "OC-INDU-01", "stance": "RUN LEAN", "shock_hit": false,
  "shock_probability": 0.14, "shock_noi_impact": 0, "maintenance_hit": true,
  "maintenance_charge": 0.343081, "rent_miss": 0, "total_noi_impact": 0,
  "total_cash_impact": 0.343081 }
```

A building acquired during a round correctly plays the `STANDARD` default for that round —
it is owned at resolution, not at submission.

## 4. NAV reconciliation

Every resolution in every run was checked against the bridge: ending NAV minus the sum of
the published channels (`value_channel + noi_income − interest_paid − acquisition_costs −
reserves`) must return the starting NAV. Worst residual across the smoke and load runs:
**0.000000**, asserted to the cent. Per-round P&L is the engine's own, and the totals
carry forward across rounds.

## 5. Where a warm request spends its time

Single student, warm container, measured per route. This is the decomposition the
"it's just a cold start" explanation does not survive:

| Probe | What it touches | p50 |
| --- | --- | --- |
| `GET /v1/whoami` | container hop + Node only | **606 ms** |
| `GET /healthz` | + engine health probe | 615 ms |
| `GET /v1/bundles` | + a full engine call | 589 ms |
| `GET …/state` | + Firestore-backed view | **2128 ms** |
| `GET …/portfolio` | + engine team view | 2075 ms |

The Python engine is **not** the bottleneck — a complete engine call adds nothing
measurable over a cookie-only request. The floor is the ~600 ms container round trip, and
a state read adds ~1.5 s of sequential Firestore work. `FirestoreStore.transact` reads the
session document, then funds and members, then the round, then that round's decisions: four
dependent round trips, on every view build.

## 6. The blocker: concurrency, not correctness

The full load scenario — join burst, model lock, bidding, a mid-round reconnect burst, a
submit-versus-close race, a results burst, a management round, isolation — passes **57 of
57 checks** at 12 students across three sessions. Nothing in the game logic fails.

What fails is time. At that same 12 students:

| Phase | p50 | p95 |
| --- | --- | --- |
| Join burst | 14.7 s | 23.8 s |
| Model lock | 16.3 s | 28.7 s |
| Deal bidding | 13.6 s | 22.3 s |
| Results burst | 14.0 s | 15.6 s |

The classroom gate is p95 < 1 s for a read and < 1.5 s for a submission, so the gate is
already missed by an order of magnitude at a third of a class. The 50-student measurement
below is where it stops merely being slow.

### 50 concurrent students

All 50 concurrent, one session:

| Route | Result |
| --- | --- |
| `GET /healthz` | 50/50 succeeded, wall 8.9 s, p50 5.3 s |
| `GET /v1/whoami` | 50/50 succeeded, wall 4.6 s, p50 3.8 s |
| `GET …/state` | 50/50 succeeded, wall **41.3 s**, p50 **27.6 s** |
| `POST /v1/join` | **46/50 timed out at 60 s** — 4 seated |

Two compounding causes, both evidenced:

1. **One `lite` container instance** (`max_instances: 1`, 1/16 vCPU). Even routes that
   touch nothing else degrade 6–9× under 50 concurrent requests.
2. **Every write serialises on the same session document.** Joining a session is a write
   transaction on it; fifty of them contend with each other, retry, and blow past any
   classroom deadline. Reads degrade 13× (27.6 s) without contention conflicts, so the
   container matters too — but the write path is what actually fails.

A classroom cannot join. This needs an infrastructure/architecture decision, not a
gameplay change, so it is reported rather than patched here. Cheapest things to try
first: raise the instance type and `max_instances`, then take fund/member writes out of
the hot session-document transaction.

## 7. Things that did pass

All of these are asserted by the harness and were green on the deployed build after
`325d56c5`; the load run finished **57/57 checks**.

- **Persistence across the container lifecycle.** A 310 session created an hour before,
  after many container sleep/wake cycles, re-authenticated and returned `phase: finale`,
  `resolvedRounds: 2`, `revision: 27`, all three funds locked, finale standings intact.
- **No state corruption anywhere.** Across every run: no double ownership (total assets
  always equalled the number of sold buildings), no double-resolved round, no order lost.
- **Reconnect.** A hard refresh with no cookie is refused (`401`), and restoring the cookie
  returns the same seat with the same submitted decision — `[[200,true],[200,true],
  [200,true]]`. No seat, bid or stance was lost.
- **Race semantics are deterministic.** Submissions landing during a close get a clean
  `409`, never a 5xx; the close succeeded and the round reported `resolvedRounds=1`. A
  second close is refused.
- **Session isolation.** A student cannot read another session's fund (`403`); no fund of
  one session appears in another (0 leaked); three sessions ran concurrently with no
  cross-talk.
- **Session identity (the §7 fix).** With two seats in one cookie jar, an explicit
  `?session=` hint resolves to the right one, and without a hint the answer is
  `ambiguous: true, sessionId: null` rather than a guess — which is the whole point of the
  change.
- **Professor visibility.** The round grid listed every fund (6/6), reported stances set
  and the mix per approach, and distinguished submitted from waiting.
- **Export.** Seven CSVs including `round_management_stances.csv`
  (`round,fund,property_id,stance`), whose stance values match the engine's published list,
  and `session_summary.csv` identifying the session.
- **605 is untouched.** No management surface, no stance fields, and a stance is refused.

## 8. Defects found and fixed (PR #3)

**Every request carrying an `Idempotency-Key` returned 500.** The service scopes a key as
`actorId:route:key`, and real routes are slash-separated. Firestore read the slash as a
path separator and rejected the odd-segment path:

```
Value for argument "documentPath" must point to a document, but was
"mem_b413bb35fd754bd4a23d:rounds/decision:probe-key".
Your path does not contain an even number of components.
```

Reproduced live: an unkeyed submit returned 200, the identical keyed submit returned 500 —
on `rounds/decision` (×4) and `model/manual` (×2). The in-memory store is a plain Map, so
every local test passed; the existing emulator test passed because its fixture route was
the literal word `route`. The store now encodes the key and the regression test pins a
slash-scoped key.

Verified on the deployed build after `325d56c5` rolled out, on the same sequence that
failed before:

```
submit WITHOUT idempotency-key: 200
submit WITH idempotency-key:    200   (was 500)
same key again:                 200   (was 500) - identical submittedAt, a replay
keyed finalize:                 409   illegal_phase - business logic, not a crash
```

The repeat carries the *same* `submittedAt` as the first call, which is the property that
matters: the second call replays the stored response instead of re-executing the write.

**The final standings rendered nameless rows.** The service publishes the engine's
`finalize` verbatim, so rows carry `team_id`/`team_name`, while the debrief and the
bigscreen read `fund_id`/`fund_name`. Against the live payload the standings table showed
no fund names, the winner banner had no name, and "your fund" could never match.
Pre-existing (untouched since `6f803f4`). Both surfaces now normalize through one helper,
pinned by tests built from the captured live row.

## 9. One smaller finding, not fixed

The first request to reach a container that has **just restarted** (a deploy, or a crash)
can return `500` while `start.sh`'s engine process is still coming up: the session-create
path calls the engine before checking that it is listening. The first create after the
`325d56c5` rollout returned 500, and three retries seconds later all returned 201. It is a
narrow window, but the honest fix is for the service to report a retryable
"engine is starting" state rather than a 500 — the same reason `/healthz` already reports
`degraded`.

## 10. Not covered here

- **Service restart and engine restart drills on a live session** were not run as isolated,
  instrumented drills. The persistence evidence in §7 covers the container being replaced
  between requests, which is the same durability claim but not the same evidence.
- **Firestore failure injection** was not attempted.
- **Deployed UI width checks** (mobile / small laptop / desktop) were not run; the harness
  is API-level by design.
- **Cloud Run** and any IAM work: out of scope for this milestone, as instructed.

## 11. Reproducing

```bash
node scripts/classroom_load.mjs --scenario smoke     --students 3   # tier contract, export, NAV
node scripts/classroom_load.mjs --scenario latency   --reps 8      # container vs engine vs store
node scripts/classroom_load.mjs --scenario idempotency             # repeated/keyed submits
node scripts/classroom_load.mjs --scenario load      --students 50 # the classroom gate
```

The load scenario expects to fail until §6 is addressed; that is its value.
