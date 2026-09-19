# Cloud Run path for the CRE game

Status: **prepared, not migrated.** The classroom application still runs on the
existing Cloudflare staging (`cre-game-preview.scswitzer.workers.dev`). Nothing in
this document was executed against a live environment, and no deploy of this
branch happened. It exists so the eventual move to Cloud Run is a configuration
exercise rather than an architecture project.

## 1. Why this is a small move rather than a rewrite

The two properties Cloud Run punishes — instance-local state and long-lived
connections — are already not part of this system:

| Cloud Run hazard | What the repository already does | Evidence |
| --- | --- | --- |
| Instances recycled between requests | The engine is a pure function of its request body: every call restores a `GameManager` from a snapshot, applies one operation, returns the next snapshot. Nothing is cached between calls. | `service/engine_api/engine.py` module docstring; `serde.restore_game` / `snapshot_game` |
| Session affinity "best effort" | The engine holds no session at all. Session state lives in Firestore (`engineState` is an opaque blob on the session document) or in the in-memory store used by tests/demo. | `services/game/src/store/firestore.ts`, `services/game/src/index.ts:23` |
| Reconnect after instance loss | The browser does not hold a socket to a specific instance: it subscribes to an SSE *doorbell* (`GET /v1/sessions/:id/events`) that only announces a revision number, then re-reads state. A dropped stream reconnects and re-reads; `retry: 3000` is sent explicitly. | `services/game/src/server.ts:762-812` |
| Response buffering turning live updates into a 20s delay | Already handled: `x-accel-buffering: no`, `cache-control: no-transform`, and a 15s comment heartbeat so an intermediary does not close an idle stream. | `services/game/src/server.ts:768-800` |
| Lost writes during a retry | Session mutations are guarded by a revision check (`assertRevision`) rather than last-write-wins, so a retried or replayed action is refused instead of double-applied. | `services/game/src/context.ts` (`assertRevision`) |
| Slow cold start / dead instance | Liveness is keyed off the same checks as `/v1/health` (`/healthz`), which verify Firestore and the engine. | `services/game/src/server.ts:224-245` |
| Long running requests | No request outlives a round: the SSE stream is the only long-lived one, and its lifetime is the browser's tab, with heartbeats every 15s. | `services/game/src/server.ts:792` |

Two images already exist and are the ones the CI Docker gate builds:

* `service/engine_api/Dockerfile` / `Dockerfile.engine` — private engine, binds
  `$PORT` via `scripts/serve_engine.py`, runs unprivileged (uid 10001), copies
  only `src/`, `service/`, `config/` (no dataset: the pool is generated from the
  bundle seed).
* `services/game/Dockerfile` — Fastify + built React client, `EXPOSE 8080`.

## 2. Target shape

Two Cloud Run services, which is the least change from today:

```text
students' browsers
      │  https (SSE + JSON)
      ▼
cre-game            Cloud Run, public, ingress all, min-instances 1 during class
  (Fastify :8080)   Firestore for sessions; calls the engine over IAM/OIDC
      │  https (private)
      ▼
cre-engine          Cloud Run, --no-allow-unauthenticated, engine only
  (FastAPI :8080)   stateless: request body in, next state out
```

A single combined container (Fastify on `:8080` fronting the engine on
`127.0.0.1:8081`) also works and removes one hop, but it gives up the property
that the engine is unreachable from the internet, and it makes the engine's
scaling independent of the ingress's. The two-service shape is preferred; the
combined shape is a fallback if the extra hop ever proves to matter.

## 3. Steps (not executed here)

```bash
# 0. One region, one project. Nothing below touches Cloudflare staging.
PROJECT=<gcp project>; REGION=us-central1
gcloud config set project "$PROJECT"

# 1. Engine: private, request-driven, no minimum instances.
gcloud run deploy cre-engine \
  --source . --region "$REGION" \
  --dockerfile Dockerfile.engine \
  --no-allow-unauthenticated \
  --cpu 1 --memory 512Mi --concurrency 40 \
  --min-instances 0 --max-instances 4 \
  --timeout 60

# 2. Game service: public ingress, one warm instance during a class window.
gcloud run deploy cre-game \
  --source . --region "$REGION" \
  --dockerfile services/game/Dockerfile \
  --allow-unauthenticated \
  --cpu 1 --memory 512Mi --concurrency 80 \
  --min-instances 1 --max-instances 6 \
  --timeout 300 --session-affinity \
  --set-env-vars ENGINE_URL=https://cre-engine-<hash>-uc.a.run.app

# 3. Firestore: the shared source of truth. Native mode, same project as the
#    game service so the runtime service account can reach it without a key file.
gcloud firestore databases create --region "$REGION"
```

Notes that matter more than the flags:

* **`--timeout`** must exceed the heartbeat interval of the SSE stream (15s) with
  room to spare; 300s is chosen so a quiet classroom does not get its doorbell
  cut mid-round. The stream itself is reconnected by the browser.
* **`--min-instances 1` during the class window only.** A cold start in front of
  a room is the one avoidable failure mode; outside the window, scale to zero.
* **`--session-affinity` is not relied on.** It is best effort on Cloud Run, and
  the application does not need it: the SSE stream re-reads state on reconnect.
* **Firestore is the source of truth, not instance memory.** Two instances may
  serve the same session; correctness comes from the revision check, not from
  routing both students to one process.
* **The engine URL is IAM-authenticated.** With `--no-allow-unauthenticated`, the
  game service must present an identity token. This is the one piece of code that
  does not exist yet: `services/game/src/engineClient.ts` currently sends no
  `Authorization` header, which is correct for the local sidecar and the
  Cloudflare path but not for a private Cloud Run engine. Add a token source
  (metadata server / `google-auth-library`) behind the existing client.
* **CORS/ingress:** the browser only ever talks to `cre-game`. Keep the engine
  private so a leaked engine URL cannot be used to read reserves.

## 4. Verification required before the class (not yet run here)

1. `docker build -f Dockerfile.engine -t cre-engine .` and
   `docker build -f services/game/Dockerfile -t cre-game .` (CI already does both).
2. A smoke run of the deployed stack: create a session, join two students, open a
   round, submit bids, resolve, confirm the SSE doorbell delivers revisions and
   that a killed instance mid-round loses nothing.
3. The load shape in `docs/V2_SPRINT_REPORT_2026-09-18.md` §6 against the deployed
   URL, not against localhost.
4. Confirm the engine refuses unauthenticated calls (`curl` without a token → 403)
   and that the game service still succeeds with one.

## 5. What must not happen

* Do not repoint or tear down the Cloudflare staging deployment from this branch.
* Do not treat instance memory as authoritative game state anywhere in the
  migration, including "just until the class".
* Do not migrate before the professor-facing deliverables (HTML, spec, 605 tier)
  are the accepted ones; a platform move and a gameplay change in the same window
  makes a failed class unattributable.
