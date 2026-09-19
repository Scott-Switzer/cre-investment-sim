# V2 Product & Gameplay Spec — Management Layer

Implementation-grade source of truth for the V2 sprint. Requirements evidence
lives in `docs/SEPT18_REQUIREMENTS.md`; the economics baseline is
`docs/GAME_ECONOMICS.md`. This spec changes only what it names.

---

## 0. Requirement classification (summary)

| Class | Items |
| --- | --- |
| CONFIRMED | HTML deliverable (done); management layer; model ladder direction; ~5-round development; one coherent lifecycle; course tiering by config; dataset replaceability; anonymization + leakage red-team; per-round checkpoints; professor observability list; UX standard; model→decision pedagogy; economics audit before change; 60–70 user load target; Cloud Run as event target (not today) |
| IMPLIED | Exact management decision set + shock schedule; per-model contract details; `course_mode` config seam; restore-beyond-reset scope; combined-container Cloud Run shape |
| PROPOSED | US market expansion; richer tenant-agent behaviors; external data refresh cadence |
| DEFERRED | Live LLM tenants; national map; 3D; platform migration this sprint; Vanguard-dependent data |

---

## 1. The round loop (V2 target)

Preserves the verified auction/revaluation engine. Steps 1–4 and 6–10 exist
today; V2 adds the **asset-management step (5)** and richer feedback (8).

```text
 1. MARKET UPDATE      macro + type-level vacancy/rent/cap evolve (existing advance_market)
 2. UNDERWRITING       team applies its own model outputs to this round's listings (existing)
 3. CAPITAL ALLOCATION decide which listings to pursue, within cash + LTV limits (existing)
 4. AUCTION            sealed bid; hidden reserve; tie → lower LTV → seeded draw (existing)
 5. ACQUISITION        winners pay equity + acquisition costs; debt booked (existing)
 6. ASSET MANAGEMENT   NEW — for each owned building, resolve the operating year:
                       operating shocks (maintenance, interruption, market) hit;
                       each team's management response is applied; NOI path reflects both
 7. PORTFOLIO UPDATE   NOI collected → revalue → reserves → interest (existing order, unchanged)
 8. FEEDBACK           round results show, per owned asset: NOI change, shock, response,
                       value change — enough to learn before the next bid
 9. LEADERBOARD        NAV + analytics boards (existing), decomposable for the debrief
10. CHECKPOINT         complete round state persisted (existing engine snapshot per commit)
```

The whole round must stay inside the existing `QUICK CLASS` budget
(≈9 min/round + 6 practice + 18 debrief ≈ 60–70 min). The management step is
designed to add **no new professor wait**: responses are entered during the
existing decision window.

## 2. The management layer (the V2 vertical slice)

### 2.1 What a student decides

After acquiring, each owned property carries one **management stance** the team
sets during the round-open decision window:

| Stance | Effect | Trade-off |
| --- | --- | --- |
| **RUN LEAN** (`run_lean`) | lower operating cost drag | higher vacancy-shock impact |
| **STANDARD** (`standard`) | neutral (default; matches today's economics exactly) | none |
| **INVEST & PROTECT** (`invest`) | reduces vacancy shock probability/severity | higher recurring cash cost |

One decision per property per round, three options, plain-language labels.
No new screens required — it rides the existing deal-card decision surface.

### 2.2 What the engine resolves

During `resolve_round`, after auctions and **before** `collect_property_income`:

1. Each owned holding draws its operating year from a **seeded, pure** function
   (`resolve_operating_year`) keyed on `(seed, property_id, round_number)` —
   same reproducibility discipline as `realized_year_outcome`.
2. Shocks are Bernoulli draws by property type + stance + market conditions
   (office shocks more; multifamily less; `invest` damps; `run_lean` amplifies).
   Shock kinds: **maintenance surge**, **tenant interruption** (temporary
   occupancy dip → NOI haircut), **market rent miss** (NOI growth penalty).
3. The year is a **cash-flow** event, not a re-underwriting of the asset. An
   operating interruption is netted out of the income the fund collects this
   round; upkeep (including the `invest` protection premium) is charged to cash
   through the existing `cumulative_reserves` channel. The holding's NOI and
   value stay on the **market** path — the same `realized_year_outcome` the round
   feedback reports — so what a fund is told happened is exactly what the engine
   applied.
4. Consequence, and why the design ended up this way: no new ledger, no second
   scoring path, and the five-channel cash and NAV identities still close
   *exactly*. An impairment model (a shock lowering the asset's own NOI basis)
   was implemented first and **rejected**: it broke the reported-equals-applied
   invariant asserted by `tests/test_game_submission.py::\`
   TestRoundFeedbackConsistency` and would have needed a sixth cash channel for
   the debrief's bridge arithmetic to keep adding up. Both halves of that
   trade-off are tested now (`tests/test_management_layer.py`).

### 2.3 Accounting identities (invariants, unchanged by V2)

```text
NAV = cash + Σ current_value − debt
NAV − starting_equity = Σ(current_value − purchase_price) + cumulative_income
                        − cumulative_interest
                        − cumulative_acquisition_costs
                        − cumulative_reserves          (existing five channels)
cash = 100 − equity_paid − cumulative_acquisition_costs + cumulative_income
       − cumulative_reserves − cumulative_interest    (no sixth channel)
```

A managed year reports *net* income (gross NOI − this year's interruption) and
puts upkeep in `cumulative_reserves`, so both identities are untouched. The
per-building record (`operating_history`) and the NOI each holding pays are in
the snapshot, so every figure above is recomputable from stored state.

Seeded replay must produce identical NAVs — the existing full-game test already
asserts exact NAV equality against a direct engine replay, and V2 keeps that test
passing unchanged. Round accounting also sums holdings in **property-id order**,
never dict order: a state restored from canonical JSON has its keys re-sorted, and
an order-dependent float sum drifts by an ULP between a replay and the run that
produced it, which the frozen-contract fixtures caught.

### 2.5 What the student sees (round feedback)

For each owned building, the round results show the stance chosen, whether a
stance could be chosen at all at this tier, the shock probability the engine used,
and what the year actually did: interruption cost, upkeep paid, and the total cash
effect. The same record reaches the professor's monitoring view, so the debrief can
narrate *why* a fund's NAV moved rather than only by how much.

### 2.4 Model → decision mapping (the pedagogy contract)

| Model | Target | Task | Trains on | Student sees | Decision it informs | Hidden | Reality resolves via | Feedback |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **VALUATION** (M1) | next-year value / fair value | regression | packet historical CSV | per-property fair value + upside vs ask | maximum bid | reserve, others' bids, future outcomes | auction + `realized_year_outcome` revaluation | round results: value vs your prediction |
| **VACANCY** (M2) | probability of occupancy drop ≥ threshold | binary classification | packet historical features incl. WALT, tenant concentration, lease expiry | risk score per property | bid aggressiveness + **management stance** (protect vs lean) | realized occupancy path | shock draw + occupancy feedback | round results: occupancy change vs your risk score |
| **RENT/INCOME** (M3) | NOI growth | regression | packet historical outcomes | NOI trajectory per property | expected return, hold vs sell posture (post-V2), stance cost-benefit | realized NOI path | `realized_year_outcome` NOI arm | round results: NOI growth vs your forecast |

A model that informs no decision is removed. In V2, M2 and M3 gain their decision
surface **through the management stance** — before V2, M2/M3 outputs existed only
as check-in analytics.

## 3. Course-mode configuration

One engine; `course_mode` scales complexity. Existing seam: `GameConfig` +
`config/bundles/*.json` (professor selects a dataset, never a seed).

The implemented seam is `CourseProfile` in `src/game/manager.py` plus two optional
bundle keys. A tier declares: the model ladder the packet requires, whether the
operating year is simulated, and which stances a fund may set. Gameplay logic
reads those fields and nothing else.

```jsonc
// config/bundles/*.json gains two optional keys:
"course_mode": "605",          // "605" | "310" | "220"; absent means 605
"management_enabled": false,   // absent means "whatever the tier declares"
```

| Aspect | 605 | 310 | 220 |
| --- | --- | --- | --- |
| Model ladder required | valuation | valuation + vacancy + income | valuation |
| Operating year simulated | **no** | yes | yes |
| Management stances | none accepted (no surface) | full three-stance play | STANDARD only |
| Method ceiling (guidance text) | Random Forest | XGBoost / logit | Excel/Solver regression |
| Shipped as | `real605-fall26-v1` (the classroom bundle) | a 310 bundle | a 220 bundle |

Three rules keep one engine from becoming three:

1. **The tier is recorded, not assumed.** A session's tier is written into its
   state, echoed in the public config (`economics.management`), and restored from
   the snapshot, so a session can always be asked which game it is playing.
2. **A bundle pins a dataset to a tier.** `real605-fall26-v1` declares 605 because
   that is the tested classroom configuration: the operating-year layer is off, so
   round resolution is byte-identical to the pre-V2 engine the class rehearsed on.
3. **Naming a tier at creation plays that tier.** `POST /v1/create-game-state`
   accepts an optional `course_mode` (with an optional `management_enabled`
   escape hatch). Naming a tier uses *that tier's* default for the operating year;
   carrying the bundle's flag across a tier change would let a 605 bundle's
   `management_enabled: false` silently neuter a 310 session. An unknown tier is
   refused, never defaulted.

Course mode is declared **data**, consumed by the engine; no `if course == ...`
code paths in gameplay logic beyond config lookups.

The management coefficients are inside `economics_digest()`, so a retuned shock
probability cannot reach a classroom without the frozen bundle's integrity check
noticing. That bump (economics 2026.09.1 → 2026.09.2) is why the contract fixtures
record a new digest; the *gameplay* numbers in them are unchanged, which is
tested by diffing the frozen contract against the branch point.

## 4. Data architecture (verify + extend, not rebuild)

Already true and kept: versioned bundles pin seed + candidate-pool hash;
packet and engine share `realized_year_outcome`; provenance tags on every
column; train/test separation; `available_at` point-in-time discipline.

V2 additions:
- `data/synthetic/` manifest gains shock/management calibration metadata
  (per-type shock rates, stance effect sizes) so the new dynamics are
  documented data, not tribal constants.
- Anonymization: properties are synthetic-calibrated around real OC anchors and
  carry non-literal naming; red-team re-verifies that no real address can be
  recovered and no outcome feature is student-visible (leakage red-team sign-off
  recorded in the sprint report).

## 5. Professor control plane (gaps V2 closes)

Existing and kept: phase machine (`TRANSITIONS` table), If-Match transitions,
round timers with pause, live monitoring, model check-in state, export ZIP,
bigscreen, demo mode, disconnect visibility.

V2: professor sees per-fund **stance summary** (who chose what) in round
monitoring, and per-asset **shock realization** in results, so the debrief can
be narrated. No new screens; extensions to existing views only.

## 6. Recovery / checkpoint

Existing: every commit rewrites the full gzipped engine snapshot on the session
document — state survives instance loss; export ZIP of revealed data exists.
V2 adds the **round checkpoint record** (see §7): each resolved round's
`RoundResult` is already stored on the round record; restore-to-round is
achieved by re-creating a session from a chosen round's snapshot + prior
decisions (documented runbook procedure; UI restore is scoped, not built, this
sprint — CLASSIFIED: restore via documented procedure now, UI later).

## 7. State & schema notes (minimal, versioned)

- Engine snapshot: `serde.SERDE_SCHEMA_VERSION` is now **3**, gaining
  `course_mode` + `management_enabled` on the config, `management_decisions` on
  teams, and `operating_history` (one entry per resolved round per holding).
- **v2 snapshots still restore**: every field v2 lacks has a default describing
  what a v2 session was actually running (the 605 tier, no stances, no history),
  so a deploy cannot strand a game that is mid-class. v1 and future schemas are
  still refused rather than guessed at (`READABLE_SCHEMA_VERSIONS`).
- The adjudicator is rebuilt on restore **with the config's own tier**, so
  restoring a 605 session cannot quietly switch the operating year on.
- Node session document: **no breaking change**; `engineState` remains opaque.
- Round record: `results` payload gains per-asset operating detail (public,
  leak-checked like every view), and `rejected_stances` joins
  `rejected_decisions` on the resolve response so a refused posture is reported
  to the fund that sent it rather than crashing a round.

## 8. Acceptance gates for V2

1. Full-game test still passes with **exact NAV equality** vs direct engine replay.
2. New engine tests: shock determinism (same seed → same outcomes), stance
   cost accounting (invariants in §2.3), practice rounds unaffected,
   course-mode config honored (605 = no stance decisions; 220 = standard only).
3. Node suite green; typecheck green; visibility tests still fail on any leak.
4. Load shape: bursts at join/check-in/bid/close verified by the existing
   milestone + concurrency tests; 70-user scale previously validated
   (507fda3) and re-validated only if engine round-resolution cost changes
   materially.
5. No staging deploy from this branch without explicit request.
