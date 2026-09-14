# CRE Investment Committee — game service (Phase 1)

The persistent classroom service. It owns sessions, identities, model check-in and the
round lifecycle, and it talks to the private Python engine; the browser talks to **this**
and nothing else.

```
STUDENT / PROFESSOR BROWSER
     │  HTTPS + SSE  (polling fallback).  Signed HttpOnly cookie.  No Firebase client SDK.
     ▼
CRE GAME SERVICE                       Node 22 + TypeScript + Fastify
     │
     ├── Firestore (Native)            SERVER-SIDE ONLY, via @google-cloud/firestore
     │
     └── CRE PYTHON ENGINE             private, server-to-server, IAM/OIDC
         this repo's adjudicator, unchanged economics
```

Architecture and rationale: `docs/CRE_INVESTMENT_COMMITTEE_ARCHITECTURE.md`.
Field-by-field visibility classification: `docs/CRE_DATA_VISIBILITY.md`.

## Run it locally

Two processes: the engine, then the game service.

```bash
# terminal 1 — the engine (from the repository root)
PORT=8081 uv run python scripts/serve_engine.py

# terminal 2 — the game service
cd services/game
npm install
export COOKIE_SECRET="$(openssl rand -base64 48)"
export ENGINE_URL=http://127.0.0.1:8081
export STORE=memory                 # no Firestore needed for local play
export COOKIE_INSECURE=1            # allows the cookie over plain HTTP
npm run dev
```

`COOKIE_SECRET` is required rather than generated on demand. A per-process secret works
in development and then invalidates every session on each Cloud Run cold start, which
shows up as "the site logged me out mid-class" long after the cause.

## Test it

```bash
npm run typecheck
npm test                 # 120 tests; ~5 s; no network, no emulator, no Python
npm run test:emulator    # +15 tests against the real Firestore emulator
```

`npm test` runs the correctness suites against a contract-shaped fake engine so they stay
fast. The **milestone suite** (`tests/milestone.test.ts`) spawns the real Python engine and
plays the whole classroom slice over HTTP — that is the one that proves the contract.

## HTTP surface

Every mutating route accepts `Idempotency-Key`; a retry replays rather than repeats.
Professor transitions require `If-Match: <revision>`.

| Method | Route | Who |
| --- | --- | --- |
| `GET` | `/v1/health` | anyone — service, store and engine identity |
| `GET` | `/v1/bundles` | anyone — datasets a professor may choose. **No seed field exists.** |
| `POST` | `/v1/sessions` | professor passcode — create a class |
| `GET` | `/v1/sessions` | professor passcode — recent classes |
| `POST` | `/v1/sessions/:id/professor` | professor passcode — re-issue a professor cookie |
| `POST` | `/v1/join` | a student, by join code |
| `POST` | `/v1/sessions/:id/reclaim` | by display name, when a browser lost its cookies |
| `GET` | `/v1/sessions/:id/state?since=<rev>` | cookie — the whole view; `since` short-circuits |
| `GET` | `/v1/sessions/:id/events` | cookie — SSE, carries a revision and nothing else |
| `POST` | `/v1/sessions/:id/checkin/begin` | professor |
| `POST` | `/v1/sessions/:id/game/start` | professor |
| `POST` | `/v1/sessions/:id/rounds/open` | professor |
| `POST` | `/v1/sessions/:id/rounds/close` | professor — locks and resolves |
| `POST` | `/v1/sessions/:id/rounds/decision` | a student, for their own fund |
| `POST` | `/v1/sessions/:id/funds/:fundId/model` | the owning fund (raw `text/csv` or `{csv}`) |
| `POST` | `/v1/sessions/:id/funds/:fundId/model/lock` | the owning fund — write-once |
| `GET` | `/v1/sessions/:id/funds/:fundId/model` | the owning fund or the professor |

## The three ideas worth knowing before reading the code

**The engine snapshot never leaves the server.** It is the whole hidden game — every
reserve price and every future outcome — and it lives on the session document as gzipped
JSON. Every player-visible payload is built by *naming* its fields in `src/views.ts`, and
`assertSafeView` fails closed on the way out.

**Every operation that calls the engine is split in two.** A short transaction claims the
transition, the engine call happens outside any transaction, and a second short
transaction commits against a guard. So transactions stay milliseconds long, retries
reproduce rather than compound (the engine is a pure function), and "resolve this round
exactly once" holds even if the first response never reached the browser.

**The client is told, never guessing.** `phase`, `revision` and `nextStep` are all
server-owned and come from the same consistent read, so a browser cannot disagree with
the professor's projector.
