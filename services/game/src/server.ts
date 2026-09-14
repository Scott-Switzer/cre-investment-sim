/**
 * The HTTP surface.
 *
 * Three things in here are not boilerplate.
 *
 * **Cookies are parsed and signed here, by hand.** No cookie plugin, no session
 * middleware: identity is one HMAC over a small payload (`auth.ts`), so the whole
 * mechanism is readable in one screen and there is no framework behaviour between
 * "the browser sent this" and "this is who they are".
 *
 * **`GET /events` sends a revision and nothing else.** SSE here is a doorbell, not a
 * data channel. If a client misses every event, or the event came from a different
 * Cloud Run instance that has since died, the next poll reads the authoritative
 * document and converges. That is what makes process death survivable rather than
 * merely unlikely.
 *
 * **Every mutating route is idempotent.** With `Idempotency-Key`, a retried request
 * replays the stored response instead of applying the effect twice; the same key with
 * a different body is refused rather than silently resolved in someone's favour.
 */

import Fastify, { type FastifyInstance, type FastifyReply, type FastifyRequest } from "fastify";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import fastifyStatic from "@fastify/static";

import { AppError, asAppError, badRequest, forbidden, illegalPhase, notFound } from "./errors.js";
import { buildCookie, verifyGrant, type CookieSpec, type Grant } from "./auth.js";
import type { AppContext } from "./context.js";
import { buildStateView, createDemoSession, createSession, joinSession, listBundles, professorSignIn, reclaimSeat, requireGrant } from "./sessions.js";
import { canonicalJoinCode, isJoinCodeShaped } from "./ids.js";
import { lockModel, readModel, uploadModel } from "./checkin.js";
import { beginCheckIn, closeRound, demoAdvance, finalizeGame, openRound, pauseTimer, resumeTimer, setRoundTimer, startGame, submitDecision } from "./rounds.js";
import { assertSafeView } from "./views.js";
import { buildExport, zipStore } from "./export.js";
import { decodeState } from "./engineClient.js";
import type { DecisionItem } from "./domain.js";
import type { ServiceConfig } from "./config.js";

interface Deps {
  config: ServiceConfig;
  context: AppContext;
}

/**
 * The built React client, served by this same process.
 *
 * One service, one origin: on Cloud Run the API and the frontend are the same
 * deployment, so the session cookie is first-party and no CORS exists at all. The
 * directory may be absent (pure-API deployments, tests); serving is then skipped
 * rather than failing boot, because the API surface does not depend on it.
 */
function mountClient(app: FastifyInstance): void {
  const root = resolve(process.env.CLIENT_DIST ?? "dist/client");
  const indexHtml = join(root, "index.html");
  if (!existsSync(indexHtml)) return;

  app.register(fastifyStatic, { root, prefix: "/", index: "index.html", wildcard: true });
  // `index: 'index.html'` serves the app at `/`; with `index: false` the plugin
  // refuses the bare root path outright. Every URL that is not a real file still
  // falls through the wildcard route's 404 into the SPA handler below.

  // The SPA's own routes (`/join`, `/lobby`, `/game/...`, `/professor`). The static
  // plugin answers files; everything that is not a file and not the API is the app.
  app.setNotFoundHandler((req, reply) => {
    const url = (req.raw.url ?? "/").split("?")[0] ?? "/";
    if (url.startsWith("/v1/") || url.startsWith("/assets/")) {
      reply.status(404).send({ error: "not_found", detail: `no route for ${url}` });
      return;
    }
    // Read per request: a rebuilt client swaps hashed asset names on disk, and an
    // index cached at boot would point at files that no longer exist. Cloud Run
    // images are immutable so this costs nothing there; locally it keeps the
    // standing review stack honest across rebuilds.
    reply
      .header("content-type", "text/html; charset=utf-8")
      .header("cache-control", "no-store")
      .send(readFileSync(indexHtml, "utf8"));
  });
}

/** Cookies, parsed from the one header that carries them. */
function readCookies(req: FastifyRequest): Map<string, string> {
  const out = new Map<string, string>();
  const raw = req.headers.cookie;
  if (!raw) return out;
  for (const part of raw.split(";")) {
    const eq = part.indexOf("=");
    if (eq < 0) continue;
    out.set(part.slice(0, eq).trim(), decodeURIComponent(part.slice(eq + 1).trim()));
  }
  return out;
}

function setCookie(reply: FastifyReply, spec: CookieSpec): void {
  const parts = [
    `${spec.name}=${encodeURIComponent(spec.value)}`,
    `Path=${spec.options.path}`,
    `Max-Age=${spec.options.maxAge}`,
    `SameSite=${spec.options.sameSite === "lax" ? "Lax" : "Strict"}`,
    "HttpOnly",
  ];
  if (spec.options.secure) parts.push("Secure");
  reply.header("set-cookie", parts.join("; "));
}

function grantFor(
  req: FastifyRequest,
  config: ServiceConfig,
  sessionId: string,
): Grant | null {
  const cookie = readCookies(req).get(`${config.cookieName}_${sessionId}`);
  return verifyGrant(cookie, config.cookieSecret);
}

/** `If-Match` is the standard way to say "act on this exact version". */
function ifMatch(req: FastifyRequest): number | null {
  const raw = req.headers["if-match"];
  if (typeof raw !== "string" || raw.trim() === "" || raw.trim() === "*") return null;
  const parsed = Number(raw.replace(/"/g, ""));
  return Number.isFinite(parsed) ? parsed : null;
}

function revisionHeader(reply: FastifyReply, revision: unknown): void {
  if (typeof revision === "number") reply.header("etag", `"${revision}"`);
}

export function buildServer(deps: Deps): FastifyInstance {
  const { config, context } = deps;
  const app = Fastify({ logger: false, bodyLimit: 8 * 1024 * 1024 });
  mountClient(app);

  // Raw CSV uploads: a student posts the file, not a JSON envelope.
  app.addContentTypeParser(
    ["text/csv", "application/csv", "text/plain"],
    { parseAs: "string" },
    (_req, body, done) => done(null, body),
  );

  app.setErrorHandler((error, req, reply) => {
    const appError = asAppError(error);
    if (appError.code === "internal") {
      req.log.error({ err: error }, "unhandled");
    }
    reply.status(appError.status).send(appError.toBody());
  });

  if (config.allowedOrigins.length > 0) {
    app.addHook("onRequest", async (req, reply) => {
      const origin = req.headers.origin;
      if (typeof origin === "string" && config.allowedOrigins.includes(origin)) {
        reply.header("access-control-allow-origin", origin);
        reply.header("access-control-allow-credentials", "true");
        reply.header("access-control-allow-headers", "content-type, if-match, idempotency-key");
        reply.header("access-control-allow-methods", "GET, POST, OPTIONS");
        reply.header("vary", "origin");
      }
      if (req.method === "OPTIONS") {
        reply.status(204).send();
      }
    });
  }

  /** Wrap a mutation so a retried request replays its answer rather than repeating itself. */
  async function idempotent<T>(
    req: FastifyRequest,
    sessionId: string,
    actorId: string,
    route: string,
    run: () => Promise<{ status: number; body: T }>,
  ): Promise<{ status: number; body: T }> {
    const key = req.headers["idempotency-key"];
    if (typeof key !== "string" || key.trim() === "") return run();
    const scoped = `${actorId}:${route}:${key.trim()}`;
    const requestHash = createHash("sha256")
      .update(JSON.stringify(req.body ?? null))
      .digest("hex");

    const existing = await context.store.getIdempotency(sessionId, scoped);
    if (existing) {
      if (existing.requestHash !== requestHash) {
        throw new AppError(
          "idempotency_conflict",
          "this Idempotency-Key was already used with a different request body",
        );
      }
      return { status: existing.status, body: existing.body as T };
    }

    const result = await run();
    await context.store.putIdempotency(sessionId, {
      key: scoped,
      actorId,
      route,
      requestHash,
      status: result.status,
      body: result.body,
      createdAt: new Date().toISOString(),
    });
    return result;
  }

  // ── health and datasets ─────────────────────────────────────────────────

  /**
   * Which session, if any, this browser's cookies name. The client mounts by asking
   * this instead of parsing the URL: the cookie is per session and only the server
   * can read it, so a shared or stale link can never borrow another seat's screen.
   * Returns what the signature already asserts — ids and role, never game state.
   */
  app.get("/v1/whoami", async (req) => {
    for (const [name, token] of readCookies(req)) {
      if (!name.startsWith(`${config.cookieName}_`)) continue;
      const sessionId = name.slice(config.cookieName.length + 1);
      const grant = verifyGrant(token, config.cookieSecret);
      if (grant && grant.sessionId === sessionId) {
        return { sessionId, role: grant.role, memberId: grant.memberId };
      }
    }
    return { sessionId: null };
  });

  app.get("/v1/health", async () => {
    const engine = await context.engine.health().catch((err: unknown) => ({
      error: err instanceof Error ? err.message : String(err),
    }));
    return {
      status: "ok",
      service: "cre-investment-committee-game",
      store: context.store.kind,
      engine,
    };
  });

  /** Operational liveness, keyed off the same checks as /v1/health. */
  app.get("/healthz", async (req, reply) => {
    const engine = await context.engine.health().catch(() => null);
    const ok = engine !== null && (engine as { status?: string }).status === "ok";
    reply.status(ok ? 200 : 503);
    return {
      status: ok ? "ok" : "degraded",
      service: "cre-investment-committee-game",
      store: context.store.kind,
      engine: ok
        ? { version: (engine as { engine_version?: string }).engine_version ?? null }
        : "unreachable",
    };
  });

  app.get("/v1/bundles", async () => {
    const bundles = await listBundles(context);
    // The seed is engine metadata. A professor selects a dataset; a bundle summary
    // has no field in which a seed could be chosen (risk R3).
    return { bundles };
  });

  // ── sessions ────────────────────────────────────────────────────────────

  app.post("/v1/sessions", async (req, reply) => {
    const body = (req.body ?? {}) as {
      name?: string;
      bundleId?: string;
      professorPasscode?: string;
      professorName?: string;
      fundNames?: string[];
      maxTeamSize?: number;
      mode?: "team" | "individual";
      totalRounds?: number;
      practiceEnabled?: boolean;
      roundTimerSeconds?: number;
    };
    const result = await createSession(context, {
      name: body.name ?? "",
      bundleId: body.bundleId,
      professorPasscode: body.professorPasscode ?? "",
      professorName: body.professorName,
      fundNames: body.fundNames,
      maxTeamSize: body.maxTeamSize,
      mode: body.mode,
      totalRounds: body.totalRounds,
      practiceEnabled: body.practiceEnabled,
      roundTimerSeconds: body.roundTimerSeconds,
    });
    setCookie(
      reply,
      buildCookie(
        `${config.cookieName}_${result.session.id}`,
        result.grant,
        config.cookieSecret,
        config.sessionTtlSeconds,
        config.cookieSecure,
      ),
    );
    revisionHeader(reply, result.session.revision);
    reply.status(201);
    return {
      sessionId: result.session.id,
      joinCode: result.joinCode,
      session: {
        id: result.session.id,
        name: result.session.name,
        bundleId: result.session.bundleId,
        bundleDisplayName: result.session.bundleDisplayName,
        phase: result.session.phase,
        totalRounds: result.session.totalRounds,
        poolCount: result.session.poolCount,
        mode: result.session.mode,
        practiceEnabled: result.session.practiceEnabled,
        roundDurationSeconds: result.session.roundDurationSeconds,
      },
    };
  });

  app.get("/v1/sessions", async (req) => {
    const passcode = req.headers["x-professor-passcode"];
    if (typeof passcode !== "string" || passcode !== config.professorPasscode) {
      throw forbidden("a professor passcode is required to list sessions");
    }
    const sessions = await context.store.listSessions();
    return {
      sessions: sessions
        .sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1))
        .slice(0, 50)
        .map((s) => ({
          id: s.id,
          name: s.name,
          joinCode: s.joinCode,
          phase: s.phase,
          currentRound: s.currentRound,
          bundleDisplayName: s.bundleDisplayName,
          createdAt: s.createdAt,
          revision: s.revision,
        })),
    };
  });

  app.post("/v1/sessions/:sessionId/professor", async (req, reply) => {
    const params = req.params as { sessionId: string };
    const body = (req.body ?? {}) as { passcode?: string; displayName?: string };
    const grant = await professorSignIn(
      context,
      params.sessionId,
      body.passcode ?? "",
      body.displayName,
    );
    setCookie(
      reply,
      buildCookie(
        `${config.cookieName}_${params.sessionId}`,
        grant,
        config.cookieSecret,
        config.sessionTtlSeconds,
        config.cookieSecure,
      ),
    );
    return { sessionId: params.sessionId, role: "professor" };
  });

  app.post("/v1/join", async (req, reply) => {
    const body = (req.body ?? {}) as {
      joinCode?: string;
      displayName?: string;
      fundId?: string | null;
      newFundName?: string | null;
    };
    const result = await joinSession(context, {
      joinCode: body.joinCode ?? "",
      displayName: body.displayName ?? "",
      fundId: body.fundId ?? null,
      newFundName: body.newFundName ?? null,
    });
    setCookie(
      reply,
      buildCookie(
        `${config.cookieName}_${result.sessionId}`,
        result.grant,
        config.cookieSecret,
        config.sessionTtlSeconds,
        config.cookieSecure,
      ),
    );
    reply.status(201);
    return {
      sessionId: result.sessionId,
      fundId: result.fundId,
      createdFund: result.createdFund,
      displayName: result.grant.displayName,
    };
  });

  /** The join screen's fund picker. No cookie, no mutation, no PII — fund names and
   *  occupancy only, exactly what is already announced in a lobby. */
  app.get("/v1/join/preview", async (req) => {
    const query = req.query as { code?: string };
    const code = (query.code ?? "").trim();
    if (!isJoinCodeShaped(code)) {
      throw badRequest("a six-character join code is required");
    }
    const sessionId = await context.store.findSessionByJoinCode(code);
    if (!sessionId) {
      throw notFound(
        `no session has the join code '${canonicalJoinCode(code)}'. Check it with your professor.`,
      );
    }
    const session = await context.store.getSession(sessionId);
    if (!session) throw notFound("that session no longer exists");
    const aggregate = await context.store.transact(sessionId, (tx) => tx.aggregate);
    const funds = [...aggregate.funds.values()]
      .sort((a, b) => (a.name < b.name ? -1 : 1))
      .map((f) => ({
        id: f.id,
        name: f.name,
        memberCount: f.memberIds.length,
        modelStatus: f.modelStatus,
      }));
    return {
      session: {
        id: session.id,
        name: session.name,
        mode: session.mode,
        maxTeamSize: session.maxTeamSize,
        phase: session.phase,
        bundleDisplayName: session.bundleDisplayName,
      },
      funds,
    };
  });

  /** Recover a seat by name when cookies are gone. Anonymous identity is device-bound. */
  app.post("/v1/sessions/:sessionId/reclaim", async (req, reply) => {
    const params = req.params as { sessionId: string };
    const body = (req.body ?? {}) as { displayName?: string };
    const grant = await reclaimSeat(context, params.sessionId, body.displayName ?? "");
    setCookie(
      reply,
      buildCookie(
        `${config.cookieName}_${params.sessionId}`,
        grant,
        config.cookieSecret,
        config.sessionTtlSeconds,
        config.cookieSecure,
      ),
    );
    return { sessionId: params.sessionId, fundId: grant.fundId, displayName: grant.displayName };
  });

  // ── demo mode ────────────────────────────────────────────────────────────

  /**
   * One click on the landing page: mint a demo session (human fund + 3 bots,
   * models pre-locked) and hand the browser its student seat. No professor
   * passcode, no uploads — the demo self-advances through `/demo/advance`.
   */
  app.post("/v1/demo/session", async (req, reply) => {
    const body = (req.body ?? {}) as { displayName?: string };
    const result = await createDemoSession(context, {
      displayName: body.displayName ?? "Demo Player",
    });
    setCookie(
      reply,
      buildCookie(
        `${config.cookieName}_${result.session.id}`,
        result.grant,
        config.cookieSecret,
        config.sessionTtlSeconds,
        config.cookieSecure,
      ),
    );
    reply.status(201);
    return {
      sessionId: result.session.id,
      fundId: result.humanFundId,
      joinCode: result.joinCode,
      name: result.session.name,
    };
  });

  app.post("/v1/sessions/:sessionId/demo/advance", async (req, reply) => {
    const params = req.params as { sessionId: string };
    const grant = requireGrant(grantFor(req, config, params.sessionId), params.sessionId);
    const result = await demoAdvance(context, {
      sessionId: params.sessionId,
      grant,
    });
    return result;
  });

  // ── state ───────────────────────────────────────────────────────────────

  app.get("/v1/sessions/:sessionId/state", async (req, reply) => {
    const params = req.params as { sessionId: string };
    const query = req.query as { since?: string };
    const grant = requireGrant(grantFor(req, config, params.sessionId), params.sessionId);
    const since = query.since !== undefined && query.since !== "" ? Number(query.since) : null;

    const view = await buildStateView(context, {
      sessionId: params.sessionId,
      grant,
      since: since !== null && Number.isFinite(since) ? since : null,
    });
    revisionHeader(reply, (view as { revision?: number }).revision);
    return view;
  });

  // ── check-in and the round loop ──────────────────────────────────────────

  app.post("/v1/sessions/:sessionId/checkin/begin", async (req, reply) => {
    const params = req.params as { sessionId: string };
    const grant = requireGrant(grantFor(req, config, params.sessionId), params.sessionId);
    const expected = ifMatch(req) ?? (req.body as { expectedRevision?: number } | null)?.expectedRevision ?? null;
    const result = await beginCheckIn(context, {
      sessionId: params.sessionId,
      grant,
      expectedRevision: expected,
    });
    revisionHeader(reply, result.revision);
    return result;
  });

  app.post("/v1/sessions/:sessionId/game/start", async (req, reply) => {
    const params = req.params as { sessionId: string };
    const grant = requireGrant(grantFor(req, config, params.sessionId), params.sessionId);
    const body = (req.body ?? {}) as { expectedRevision?: number; scenario?: string };
    const result = await idempotent(req, params.sessionId, grant.memberId, "game/start", async () => ({
      status: 200,
      body: await startGame(context, {
        sessionId: params.sessionId,
        grant,
        expectedRevision: ifMatch(req) ?? body.expectedRevision ?? null,
        scenario: body.scenario,
      }),
    }));
    reply.status(result.status);
    return result.body;
  });

  app.post("/v1/sessions/:sessionId/rounds/open", async (req, reply) => {
    const params = req.params as { sessionId: string };
    const grant = requireGrant(grantFor(req, config, params.sessionId), params.sessionId);
    const body = (req.body ?? {}) as { expectedRevision?: number };
    const result = await openRound(context, {
      sessionId: params.sessionId,
      grant,
      expectedRevision: ifMatch(req) ?? body.expectedRevision ?? null,
    });
    revisionHeader(reply, (result as { round?: number }).round);
    return result;
  });

  app.post("/v1/sessions/:sessionId/rounds/close", async (req, reply) => {
    const params = req.params as { sessionId: string };
    const grant = requireGrant(grantFor(req, config, params.sessionId), params.sessionId);
    const body = (req.body ?? {}) as { expectedRevision?: number };
    const result = await closeRound(context, {
      sessionId: params.sessionId,
      grant,
      expectedRevision: ifMatch(req) ?? body.expectedRevision ?? null,
    });
    return result;
  });

  app.post("/v1/sessions/:sessionId/game/finalize", async (req, reply) => {
    const params = req.params as { sessionId: string };
    const grant = requireGrant(grantFor(req, config, params.sessionId), params.sessionId);
    const body = (req.body ?? {}) as { expectedRevision?: number };
    const result = await idempotent(req, params.sessionId, grant.memberId, "game/finalize", async () => ({
      status: 200,
      body: await finalizeGame(context, {
        sessionId: params.sessionId,
        grant,
        expectedRevision: ifMatch(req) ?? body.expectedRevision ?? null,
      }),
    }));
    reply.status(result.status);
    return result.body;
  });

  app.post("/v1/sessions/:sessionId/timer", async (req, reply) => {
    const params = req.params as { sessionId: string };
    const grant = requireGrant(grantFor(req, config, params.sessionId), params.sessionId);
    const body = (req.body ?? {}) as { expectedRevision?: number; durationSeconds?: number };
    return setRoundTimer(context, {
      sessionId: params.sessionId,
      grant,
      expectedRevision: ifMatch(req) ?? body.expectedRevision ?? null,
      durationSeconds: body.durationSeconds ?? 0,
    });
  });

  app.post("/v1/sessions/:sessionId/timer/pause", async (req, reply) => {
    const params = req.params as { sessionId: string };
    const grant = requireGrant(grantFor(req, config, params.sessionId), params.sessionId);
    const body = (req.body ?? {}) as { expectedRevision?: number };
    return pauseTimer(context, {
      sessionId: params.sessionId,
      grant,
      expectedRevision: ifMatch(req) ?? body.expectedRevision ?? null,
    });
  });

  app.post("/v1/sessions/:sessionId/timer/resume", async (req, reply) => {
    const params = req.params as { sessionId: string };
    const grant = requireGrant(grantFor(req, config, params.sessionId), params.sessionId);
    const body = (req.body ?? {}) as { expectedRevision?: number };
    return resumeTimer(context, {
      sessionId: params.sessionId,
      grant,
      expectedRevision: ifMatch(req) ?? body.expectedRevision ?? null,
    });
  });

  app.post("/v1/sessions/:sessionId/rounds/decision", async (req, reply) => {
    const params = req.params as { sessionId: string };
    const grant = requireGrant(grantFor(req, config, params.sessionId), params.sessionId);
    const body = (req.body ?? {}) as {
      fundId?: string;
      items?: DecisionItem[];
      expectedRevision?: number;
    };
    const fundId = body.fundId ?? grant.fundId;
    if (!fundId) throw badRequest("fundId is required");
    if (!Array.isArray(body.items)) throw badRequest("items must be an array");

    const result = await idempotent(req, params.sessionId, grant.memberId, "rounds/decision", async () => {
      const decision = await submitDecision(context, {
        sessionId: params.sessionId,
        fundId,
        grant,
        items: body.items!,
        expectedRevision: ifMatch(req) ?? body.expectedRevision ?? null,
      });
      return { status: 200, body: { decision } };
    });
    reply.status(result.status);
    return result.body;
  });

  // ── models ──────────────────────────────────────────────────────────────

  app.post("/v1/sessions/:sessionId/funds/:fundId/model", async (req, reply) => {
    const params = req.params as { sessionId: string; fundId: string };
    const grant = requireGrant(grantFor(req, config, params.sessionId), params.sessionId);
    const csv =
      typeof req.body === "string"
        ? req.body
        : ((req.body ?? {}) as { csv?: string }).csv ?? "";
    if (!csv.trim()) throw badRequest("the request body must contain the prediction CSV");

    const expected = ifMatch(req);
    const result = await idempotent(req, params.sessionId, grant.memberId, "model/upload", async () => {
      const outcome = await uploadModel(context, {
        sessionId: params.sessionId,
        fundId: params.fundId,
        grant,
        csv,
        expectedRevision: expected,
      });
      // A rejection is reportable, not exceptional: the student needs to read why.
      return { status: 200, body: outcome as unknown as Record<string, unknown> };
    });
    reply.status(result.status);
    return result.body;
  });

  app.post("/v1/sessions/:sessionId/funds/:fundId/model/lock", async (req, reply) => {
    const params = req.params as { sessionId: string; fundId: string };
    const grant = requireGrant(grantFor(req, config, params.sessionId), params.sessionId);
    const body = (req.body ?? {}) as { expectedRevision?: number };
    const result = await idempotent(req, params.sessionId, grant.memberId, "model/lock", async () => ({
      status: 200,
      body: { fund: await lockModel(context, {
        sessionId: params.sessionId,
        fundId: params.fundId,
        grant,
        expectedRevision: ifMatch(req) ?? body.expectedRevision ?? null,
      }) },
    }));
    reply.status(result.status);
    return result.body;
  });

  app.get("/v1/sessions/:sessionId/funds/:fundId/model", async (req) => {
    const params = req.params as { sessionId: string; fundId: string };
    const grant = requireGrant(grantFor(req, config, params.sessionId), params.sessionId);
    return { model: await readModel(context, {
      sessionId: params.sessionId,
      fundId: params.fundId,
      grant,
    }) };
  });

  // ── portfolio: one fund's own book, from the engine's team view ─────────

  /**
   * The owning fund's holdings, channels and override history — the engine's
   * `/v1/team-view`, served verbatim to the owning fund (and the professor, who
   * may project a fund's book during the debrief). Nobody else.
   */
  app.get("/v1/sessions/:sessionId/funds/:fundId/portfolio", async (req) => {
    const params = req.params as { sessionId: string; fundId: string };
    const grant = requireGrant(grantFor(req, config, params.sessionId), params.sessionId);
    const session = await context.store.getSession(params.sessionId);
    if (!session) throw notFound(`unknown session '${params.sessionId}'`);
    if (!session.engineState) throw illegalPhase("the game has not been started yet");

    if (grant.role !== "professor") {
      if (grant.fundId !== params.fundId) {
        throw forbidden("that is another fund's book");
      }
    }
    const view = await context.engine.teamView(decodeState(session.engineState), params.fundId);
    assertSafeView(view, `portfolio(${params.sessionId}/${params.fundId})`);
    return { portfolio: view };
  });

  // ── professor export ────────────────────────────────────────────────────

  app.get("/v1/sessions/:sessionId/export", async (req, reply) => {
    const params = req.params as { sessionId: string };
    const grant = requireGrant(grantFor(req, config, params.sessionId), params.sessionId);
    if (grant.role !== "professor") throw forbidden("only the professor can export a session");
    const session = await context.store.getSession(params.sessionId);
    if (!session) throw notFound(`unknown session '${params.sessionId}'`);
    const bundle = await buildExport(context, session);
    reply.header("content-type", "application/zip");
    reply.header("content-disposition", `attachment; filename="${bundle.filename}"`);
    return zipStore(bundle.files);
  });

  // ── the doorbell ────────────────────────────────────────────────────────

  app.get("/v1/sessions/:sessionId/events", async (req, reply) => {
    const params = req.params as { sessionId: string };
    const grant = requireGrant(grantFor(req, config, params.sessionId), params.sessionId);
    const session = await context.store.getSession(params.sessionId);
    if (!session) throw notFound(`unknown session '${params.sessionId}'`);

    reply.raw.writeHead(200, {
      "content-type": "text/event-stream",
      "cache-control": "no-cache, no-transform",
      connection: "keep-alive",
      // Cloud Run buffers responses by default, which turns a live stream into a
      // twenty-second delay. This is the header that switches that off.
      "x-accel-buffering": "no",
    });
    reply.raw.write(`retry: 3000\n\n`);
    reply.raw.write(`event: revision\ndata: ${JSON.stringify({ revision: session.revision })}\n\n`);

    let last = session.revision;
    const unsubscribe = context.store.subscribe(params.sessionId, (revision) => {
      // Skip a repeat: a Firestore listener fires for the write this instance just
      // made, and re-announcing the same revision is pure noise for the client.
      if (revision === last) return;
      last = revision;
      try {
        reply.raw.write(`event: revision\ndata: ${JSON.stringify({ revision })}\n\n`);
      } catch {
        unsubscribe();
      }
    });

    // A comment every 15s keeps intermediaries from closing an idle stream, and tells
    // a dead peer to go away.
    const heartbeat = setInterval(() => {
      try {
        reply.raw.write(`: ping\n\n`);
      } catch {
        clearInterval(heartbeat);
        unsubscribe();
      }
    }, 15_000);

    req.raw.on("close", () => {
      clearInterval(heartbeat);
      unsubscribe();
    });

    // Never resolve: the stream ends when the client disconnects.
    return reply;
  });

  return app;
}
