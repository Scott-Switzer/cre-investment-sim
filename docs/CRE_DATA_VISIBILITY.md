# CRE Investment Committee — Data Visibility Contract

**Status:** implemented and enforced at runtime.
**Code:** `service/engine_api/visibility.py`, applied by `service/engine_api/public.py`.
**Tests:** `tests/test_engine_api_visibility.py`.

This game's entire integrity rests on information the player must not have. If a
student can read the seller's reserve before bidding, the auction stops testing
valuation and starts testing `curl`. So visibility is not documented here and hoped
for — it is a set of classes, a set of allowed-key sets, and a runtime assertion that
every player-facing payload must pass.

---

## 1. The five classes

| Class | Meaning |
| --- | --- |
| `PUBLIC_BEFORE_ROUND` | Safe to show a player before they decide. |
| `PRIVATE_TEAM_ONLY` | Only the owning fund (and the instructor). Never another fund. |
| `SERVER_SECRET_UNTIL_RESOLVE` | Hidden until the round resolves, then deliberately revealed. |
| `PUBLIC_AFTER_RESOLVE` | Published once the round or the game is over. |
| `SERVER_ONLY_ALWAYS` | Never leaves the engine, under any phase. |

`FIELD_VISIBILITY` in `visibility.py` assigns one class to every field, and
`required_phase_for()` **defaults an unlisted field to `SERVER_ONLY_ALWAYS`**. New
fields are therefore private until somebody deliberately publishes them, which is
the only safe direction for this default to fail in.

---

## 2. The three forbidden sets

Public serialisers do not choose a policy each time. They pass one of three frozen
sets, so a new payload has to *pick* an audience:

| Set | Contains | Used for |
| --- | --- | --- |
| `FORBIDDEN_IN_BROADCAST` | server-only + team-private + pre-resolve secrets | anything at all funds can see during a round |
| `FORBIDDEN_IN_RESULTS` | server-only + team-private | the reveal; the reserve and outcomes are now public |
| `FORBIDDEN_IN_TEAM_VIEW` | server-only | a payload addressed to exactly one fund |

Nothing is built by copying the engine snapshot and deleting keys. Every public
payload is constructed by **naming** the fields it exposes — subtraction fails open
the first time a field is added, and the field that would leak is the reserve.

---

## 3. Where each sensitive thing lives

### The seller's reserve — `SERVER_SECRET_UNTIL_RESOLVE`

Held on `PropertyMarket.reserve_price` inside the server-side snapshot, which
`FORBIDDEN_IN_BROADCAST` includes via `SERVER_ONLY_ALWAYS`.

Two independent checks catch a leak:

1. **Key check.** No payload key may be named `reserve_price`, `all_bids`,
   `bid_price` or `ltv` before a round resolves.
2. **Value check.** Every numeric value in the payload is compared against the real
   reserves. Renaming the field to `min_price` or `floor` does not help, because the
   number itself is forbidden.

`public_round()` passes the live reserves to that second check explicitly, so the
guard knows what to look for rather than being told the answer in advance.

### Realised future outcomes — `SERVER_SECRET_UNTIL_RESOLVE`

`noi_growth_actual`, `cap_rate_actual`, `exit_value`, `exit_noi`,
`occupancy_change`. These are computed inside `resolve_round` and do not exist in
any payload beforehand. They are published in `public_results()` and never before
it — enforced by the same `FORBIDDEN_IN_BROADCAST` set, not by the order in which
the game happens to call things.

### Other funds' models — `PRIVATE_TEAM_ONLY`

`model_predictions` is per-fund and is never included in a broadcast or a results
payload. A payload addressed to one fund is additionally checked with
`assert_single_team()`, which fails if it names any other fund at all.

### Other funds' sealed bids — never published

The auction is sealed first-price: `all_bids` is `SERVER_SECRET_UNTIL_RESOLVE` and
is **not** in `public_results` either. A fund learns whether it won, the winning
bid, and the now-published reserve. It does not learn what anyone else bid, at any
phase — that is a deliberate design choice, not an oversight.

### Engine internals — `SERVER_ONLY_ALWAYS`

`config` (which carries the **seed**), `all_properties`, `round_history`,
`market_history`, `current_round_result`, `submitted_bids`, `event_log`,
`adjudicator_seed`, `adjudicator_rng_state`.

The full snapshot exists to reconstruct the engine in another process. It is
server-only in the strictest sense: the browser never receives it, and the game
service is expected to project it into DTOs before anything is stored. Storing the
raw snapshot in a place a browser can read would defeat this entire document.

---

## 4. The two structural properties that make this hold

1. **The reserve and the outcomes are *computed* in the engine, not *stored* in the
   client-visible layer.** They cannot leak from a database the client can read,
   because they are never written to one. This is why the engine is a private
   service rather than a library the game can call freely.
2. **There is one property DTO.** `public_deal()` is the only shape a property takes
   on the way to a player. When there is one construction path, there is one place to
   get it wrong, and one place the tests have to cover.

---

## 5. What a payload actually contains

For completeness, since omission is impossible to review:

**During a round** (`public_round`): property identity and physical facts; operations
(`current_noi`, `occupancy`, `market_rent`, `in_place_rent`, `walt`,
`tenant_concentration`, `opex_ratio`, `lease_expiry_profile`, `property_quality`,
`primary_risk`); capital markets (`asking_price`, `going_in_cap`, `debt_rate`,
`max_ltv`, `amortization_years`); the game's own charges (`acquisition_cost_rate`,
`capital_reserve_rate`); and the descriptive `indicative_capex_exposure` with its
note. Plus the market, the fund scoreboard line, and the round's stage.

**After a round** (`public_results`): the above, plus `sold`, `winning_team_id`,
`winning_bid`, the revealed `reserve_price`, and the realised `exit_value` /
`noi_growth_actual`. **No `all_bids`.**

**The candidate pool** (`GET /v1/bundles/{id}/pool`, added in Phase 1): one
`public_deal` per candidate property — the same DTO as a deal card, so the check-in
screen and the round screen cannot describe the same building differently. It is the
field set the published student packet already ships, and it carries no reserve and no
outcome. It exists because the game service must validate an upload *before* the round
loop, and `create-game-state` refuses a mismatched model only by declining to start.

**Never**: the seed, other funds' models, other funds' bids, or any engine internals.

### At the game-service layer

The engine's payloads are necessary but not sufficient. The service adds its own
rules, because it is the layer that knows who is asking:

| Thing | Reachable by |
| --- | --- |
| A fund's forecast and policy | the owning fund, and the professor |
| A fund's submitted decision | the owning fund, and the professor |
| All funds' decisions, in full | **nobody** — sealed until the engine's own reveal |
| Submission counts and override tallies | everyone ("17 of 18 have submitted" is a room fact) |
| Bid and LTV amounts on the professor's grid | **not even the professor** — the screen is routinely projected |
| The engine snapshot (`engineState`, gzipped) | `SERVER_ONLY_ALWAYS`; `src/views.ts::assertSafeView` fails closed on any projection that names it, or that carries a byte buffer at all |

---

## 6. `indicative_capex_exposure` — the terminology fix

`capex_need` was a per-property figure the engine **never charged**, while the engine
did charge a type-based `CAPITAL_RESERVE_RATE`. Two capex-flavoured numbers meaning
different things is exactly the kind of quiet inconsistency that costs credibility
with a practitioner in the room.

Resolution, chosen because relabelling is smaller and more honest than inventing a
charge that the balance work deliberately replaced:

- the field is now `indicative_capex_exposure`,
- it is documented as a **descriptive condition feature, not a NAV charge**,
- `capital_reserve_rate` is published beside it as the figure that actually recurs,
- and the payload carries the note verbatim, so a UI cannot render one without the
  other being available.

The instructor-facing rules are in `docs/GAME_ECONOMICS.md`.
