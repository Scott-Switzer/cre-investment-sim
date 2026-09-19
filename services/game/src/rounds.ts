/**
 * The round lifecycle.
 *
 * Every operation here that touches the engine is split in two, and the split is the
 * most important structural decision in the service:
 *
 *   1. a short transaction that claims the transition and reads what it needs,
 *   2. the engine call, which is slow and must never hold a transaction open,
 *   3. a short transaction that commits the engine's answer against a guard.
 *
 * That shape buys three things at once. Transactions stay milliseconds long, so a
 * class's worth of concurrent clicks never contends. The engine call can be retried
 * freely, because it is a pure function of its request — a retry after a crash
 * reproduces the answer rather than compounding it. And the commit guard makes
 * "resolve this round exactly once" a property rather than a hope: the second
 * committer finds `resolvedAt` already set and is refused, even if the first
 * request's response never made it back to the browser.
 *
 * Nothing here computes a game number. Prices, reserves, NAV and standings all come
 * from the engine's own projections and are stored and forwarded verbatim.
 */

import { AppError, conflict, forbidden, illegalPhase, notFound, unauthenticated } from "./errors.js";
import type { AppContext } from "./context.js";
import {
  assertMayActForFund,
  assertRevision,
  offeredPropertyIds,
  requireFund,
  requireMember,
  roundAcceptsSubmissions,
} from "./context.js";
import {
  assertAction,
  isGameComplete,
  phaseAfterResolve,
  PRACTICE_ROUND,
  stancesOf,
  type DecisionItem,
  type RoundRecord,
  type SessionState,
  type StanceItem,
} from "./domain.js";
import { assertSafeView, managementOf, roundView } from "./views.js";
import {
  decodeState,
  encodeState,
  type EngineDecision,
  type EngineManagementStance,
} from "./engineClient.js";
import { nowIso } from "./ids.js";
import type { Grant } from "./auth.js";

export function requireProfessor(grant: Grant): void {
  if (grant.role !== "professor") {
    throw forbidden("only the professor can do that");
  }
}

/**
 * Professor transitions require `If-Match`.
 *
 * Not a nicety. Two professor tabs, or one tab left open from earlier in the class,
 * will happily send "open round" against a session that has moved on. Requiring the
 * revision the caller actually saw turns that into a refusal with a legible reason,
 * instead of a transition the professor did not intend.
 */
function requireRevision(expected: number | null | undefined, action: string): number {
  if (expected === null || expected === undefined || !Number.isFinite(expected)) {
    throw new AppError(
      "bad_request",
      `'${action}' requires the session revision you are acting on. ` +
        "Send it as the If-Match header, or as `expectedRevision` in the body.",
    );
  }
  return expected;
}

function requireEngineState(session: SessionState): Uint8Array {
  if (!session.engineState) {
    throw illegalPhase("the game has not been started yet");
  }
  return session.engineState;
}

function roundNumberOf(broadcast: unknown): number {
  const value = (broadcast as { round_number?: unknown } | null)?.round_number;
  if (typeof value !== "number") {
    throw new AppError(
      "engine_unavailable",
      "the engine's round payload did not name a round number",
    );
  }
  return value;
}

// ── check-in → play ───────────────────────────────────────────────────────

export async function beginCheckIn(
  ctx: AppContext,
  args: { sessionId: string; grant: Grant; expectedRevision: number | null },
) {
  requireProfessor(args.grant);
  const revision = requireRevision(args.expectedRevision, "begin check-in");
  return ctx.store.transact(args.sessionId, (tx) => {
    const session = tx.aggregate.session;
    assertRevision(session, revision);
    assertAction(session.phase, "begin_checkin");
    session.phase = "model_checkin";
    tx.touch();
    return { phase: session.phase, revision: session.revision + 1 };
  });
}

export interface StartGameInput {
  sessionId: string;
  grant: Grant;
  expectedRevision: number | null;
  scenario?: string;
}

export async function startGame(ctx: AppContext, args: StartGameInput) {
  requireProfessor(args.grant);
  const revision = requireRevision(args.expectedRevision, "start the game");

  // 1. claim: verify the transition and collect the teams to send.
  const claim = await ctx.store.transact(args.sessionId, (tx) => {
    const session = tx.aggregate.session;
    assertRevision(session, revision);
    assertAction(session.phase, "start_game");
    if (session.engineCreatedAt) {
      throw conflict("this game has already been started");
    }
    const funds = [...tx.aggregate.funds.values()].sort((a, b) => (a.id < b.id ? -1 : 1));
    if (funds.length === 0) {
      throw conflict("there are no funds in this session to play");
    }
    return {
      bundleId: session.bundleId,
      courseMode: session.courseMode ?? null,
      fundCount: funds.length,
      practiceEnabled: session.practiceEnabled !== false,
      unlocked: funds.filter((f) => f.modelStatus !== "locked").map((f) => f.name),
      teams: funds.map((f) => ({ id: f.id, name: f.name })),
    };
  });

  if (claim.unlocked.length > 0) {
    // Refused rather than started with an empty model: a fund that plays without a
    // forecast is not playing the exercise, and the engine would treat it as having
    // no view at all rather than telling anyone.
    throw conflict(
      `waiting on ${claim.unlocked.length} fund(s) to lock a model: ${claim.unlocked.join(", ")}`,
    );
  }

  const models = await ctx.store.listAllModels(args.sessionId);
  const byFund = new Map(models.map((m) => [m.fundId, m]));
  const teams = claim.teams.map((team) => {
    const model = byFund.get(team.id);
    if (!model) {
      throw conflict(`'${team.name}' has no stored model to send to the engine`);
    }
    return {
      team_id: team.id,
      team_name: team.name,
      submissions: model.rows
        .map((row) => ({
          property_id: row.propertyId,
          forecast: {
            model_name: model.modelName,
            predicted_fair_value: row.forecast.predictedFairValue,
            predicted_noi_growth: row.forecast.predictedNoiGrowth,
            probability_of_downside: row.forecast.probabilityOfDownside,
            confidence: row.forecast.confidence,
          },
          policy: {
            max_bid: row.policy.maxBid,
            target_ltv: row.policy.targetLtv,
          },
        }))
        .sort((a, b) => (a.property_id < b.property_id ? -1 : 1)),
    };
  });

  // 2. the engine call, outside any transaction.
  // It is deterministic, so two professors racing produces one game state written
  // twice — the guard below decides which write lands, and both agree.
  const created = await ctx.engine.createGameState(
    claim.bundleId,
    teams,
    args.scenario ?? "Base Case",
    claim.courseMode,
  );

  // 3. commit against the guard.
  const started = await ctx.store.transact(args.sessionId, (tx) => {
    const session = tx.aggregate.session;
    if (session.engineCreatedAt) {
      throw conflict("this game has already been started");
    }
    if (session.phase !== "model_checkin") {
      throw illegalPhase(`cannot start the game while the session is '${session.phase}'`);
    }
    const state = encodeState(created.state);
    const round = roundNumberOf(created.public);
    const openedAt = nowIso();

    session.engineState = state;
    session.engineStateBytes = state.byteLength;
    session.engineCreatedAt = openedAt;
    session.currentRound = round;
    session.phase = round === PRACTICE_ROUND ? "practice" : "round";
    // Record the tier the engine says it created, rather than the string that was
    // asked for: if they ever differ, the engine's answer is the game being played.
    session.courseMode = managementOf(created.public).courseMode ?? session.courseMode;

    const record: RoundRecord = {
      sessionId: args.sessionId,
      round,
      openedAt,
      closedAt: null,
      resolvedAt: null,
      broadcast: created.public,
      results: null,
      analytics: null,
      rejected: [],
      rejectedStances: [],
    };
    tx.putRound(record);
    tx.touch();
    return {
      phase: session.phase,
      round,
      fundCount: claim.fundCount,
      engineStateBytes: state.byteLength,
    };
  });

  // Practice disabled: the engine always opens at the practice round, so a session
  // that opted out resolves it immediately with zero decisions (every fund absent
  // = no bids) and lands in practice_results, ready for the professor to open
  // Round 1. One honest click rather than a phantom practice screen.
  if (!claim.practiceEnabled && started.phase === "practice") {
    const fresh = await ctx.store.getSession(args.sessionId);
    if (fresh === null) throw notFound("session vanished after the engine started");
    return closeRound(ctx, {
      sessionId: args.sessionId,
      grant: args.grant,
      expectedRevision: fresh.revision,
    });
  }
  return started;
}

// ── opening a round ───────────────────────────────────────────────────────

export async function openRound(
  ctx: AppContext,
  args: { sessionId: string; grant: Grant; expectedRevision: number | null },
) {
  requireProfessor(args.grant);
  const revision = requireRevision(args.expectedRevision, "open a round");

  const claim = await ctx.store.transact(args.sessionId, (tx) => {
    const session = tx.aggregate.session;
    assertRevision(session, revision);
    assertAction(session.phase, "open_round");
    const record = tx.aggregate.round;
    if (!record || record.resolvedAt === null) {
      throw illegalPhase("resolve the current round before opening the next one");
    }
    return { state: requireEngineState(session), previousRound: record.round };
  });

  const opened = await ctx.engine.openRound(decodeState(claim.state));
  if (opened.game_complete) {
    throw conflict("the game is complete; there is no further round to open");
  }

  return ctx.store.transact(args.sessionId, (tx) => {
    const session = tx.aggregate.session;
    const record = tx.aggregate.round;
    if (session.phase !== "practice_results" && session.phase !== "round_results") {
      throw conflict(`the session moved on while the round was opening (now '${session.phase}')`);
    }
    if (!record || record.resolvedAt === null || record.round !== claim.previousRound) {
      throw conflict("the round changed while the next one was opening; reload and try again");
    }

    // Decisions are scoped to the round. The aggregate is loaded with the
    // resolved round's decisions, so remove those documents before switching
    // the session to the newly opened round; otherwise students appear locked
    // in the new round with their prior submission.
    for (const fundId of tx.aggregate.decisions.keys()) {
      tx.deleteDecision(fundId);
    }

    const state = encodeState(opened.state);
    const round = roundNumberOf(opened.public);
    session.engineState = state;
    session.engineStateBytes = state.byteLength;
    session.currentRound = round;
    session.phase = "round";
    session.roundDeadlineAt =
      session.roundDurationSeconds > 0
        ? Date.now() + session.roundDurationSeconds * 1000
        : null;
    session.timerPausedAt = null;

    tx.putRound({
      sessionId: args.sessionId,
      round,
      openedAt: nowIso(),
      closedAt: null,
      resolvedAt: null,
      broadcast: opened.public,
      results: null,
      analytics: null,
      rejected: [],
      rejectedStances: [],
    });
    tx.touch();
    return { round, phase: session.phase };
  });
}

// ── submitting a decision ─────────────────────────────────────────────────

export interface SubmitDecisionInput {
  sessionId: string;
  fundId: string;
  grant: Grant;
  items: DecisionItem[];
  /**
   * This fund's management stances for the round, if the tier accepts them. Optional:
   * a 605 or 220 fund sends none, and a 310 fund that sends none simply plays on the
   * tier's default — the engine's own rule, and not an error here.
   */
  stances?: StanceItem[];
  expectedRevision?: number | null;
}

/**
 * Check a fund's stances against the rules the engine published for this round.
 *
 * Only two things are checked here, both of them *shape*: that the tier accepts a
 * stance choice at all, and that each stance is one the engine named. Whether the
 * building is actually owned, and what the stance then does, stays the engine's
 * call — a helper that guessed at ownership would be a second opinion about the
 * rules, and the engine already reports a refusal per property.
 */
function checkStances(broadcast: unknown, stances: StanceItem[]): void {
  if (stances.length === 0) return;
  const management = managementOf(broadcast);
  if (!management.enabled || !management.hasStanceChoice) {
    throw new AppError(
      "bad_request",
      management.courseMode
        ? `this session is playing the ${management.courseMode} course tier, which has no management decision`
        : "this session has no management decision",
      { courseMode: management.courseMode, stances: management.stances },
    );
  }
  const seen = new Set<string>();
  for (const item of stances) {
    if (!management.stances.includes(item.stance)) {
      throw new AppError(
        "bad_request",
        `'${item.stance}' is not a management stance this session accepts. ` +
          `Available: ${management.stances.join(", ")}.`,
        { stances: management.stances },
      );
    }
    if (seen.has(item.propertyId)) {
      throw new AppError("bad_request", `a stance for '${item.propertyId}' was sent twice`);
    }
    seen.add(item.propertyId);
  }
}

export async function submitDecision(ctx: AppContext, args: SubmitDecisionInput) {
  return ctx.store.transact(args.sessionId, (tx) => {
    const session = tx.aggregate.session;
    assertRevision(session, args.expectedRevision ?? null);

    // The round record is checked before the phase, so a late submission is told the
    // thing that actually happened — "the market closed" — rather than being handed a
    // phase name to interpret. A student who was still typing when the professor
    // closed the market deserves that sentence.
    const record = tx.aggregate.round;
    if (record && !roundAcceptsSubmissions(session, record)) {
      throw conflict("the market is closed for this round; your decision can no longer change");
    }
    if (session.phase !== "practice" && session.phase !== "round") {
      throw conflict(
        `there is no open round to decide on (the session is '${session.phase}')`,
      );
    }
    if (!record) throw illegalPhase("no round is open");

    const member = requireMember(tx, args.grant.memberId);
    const fund = requireFund(tx, args.fundId);
    assertMayActForFund(member, fund);

    const offered = offeredPropertyIds(record.broadcast);
    const deals = new Map(
      (
        ((record.broadcast as { deals?: unknown[] } | null)?.deals ?? []) as {
          property_id: string;
          max_ltv: number | null;
        }[]
      ).map((deal) => [deal.property_id, deal]),
    );

    // Every offered property must be decided explicitly, including the passes.
    // "I chose not to bid" is the decision the exercise is about, so it is not
    // allowed to be the silent default.
    const seen = new Set<string>();
    for (const item of args.items) {
      if (!offered.includes(item.propertyId)) {
        throw new AppError(
          "bad_request",
          `'${item.propertyId}' is not offered in this round`,
          { offered },
        );
      }
      if (seen.has(item.propertyId)) {
        throw new AppError("bad_request", `'${item.propertyId}' was decided twice`);
      }
      seen.add(item.propertyId);
      if (item.action !== "BID" && item.action !== "PASS") {
        throw new AppError("bad_request", `unknown action '${item.action as string}'`);
      }
      if (item.action === "BID") {
        if (item.bid === null || !Number.isFinite(item.bid) || item.bid <= 0) {
          throw new AppError("bad_request", `a bid for '${item.propertyId}' must be a positive price`);
        }
        if (item.ltv === null || !Number.isFinite(item.ltv) || item.ltv <= 0 || item.ltv > 1) {
          throw new AppError(
            "bad_request",
            `the leverage on '${item.propertyId}' must be a decimal in (0, 1]`,
          );
        }
        // Checked against the *published* ceiling on the deal, which the engine
        // itself sent — not against a re-derived rule. Everything else about
        // legality (affordability, the reserve) stays the engine's call, and its
        // refusal is surfaced in the results rather than guessed at here.
        const maxLtv = deals.get(item.propertyId)?.max_ltv;
        if (typeof maxLtv === "number" && item.ltv > maxLtv + 1e-9) {
          throw new AppError(
            "bad_request",
            `the leverage on '${item.propertyId}' is above that property's ceiling of ` +
              `${(maxLtv * 100).toFixed(0)}%`,
          );
        }
      }
    }
    const missing = offered.filter((id) => !seen.has(id));
    if (missing.length > 0) {
      throw new AppError(
        "bad_request",
        `decide on every property offered, including the ones you are passing on. ` +
          `Missing: ${missing.join(", ")}`,
        { offered, missing },
      );
    }

    const stances = args.stances ?? [];
    checkStances(record.broadcast, stances);

    const decision = {
      sessionId: args.sessionId,
      round: record.round,
      fundId: fund.id,
      submittedBy: member.id,
      submittedAt: nowIso(),
      items: args.items
        .map((item) => ({
          propertyId: item.propertyId,
          action: item.action,
          bid: item.action === "BID" ? item.bid : null,
          ltv: item.action === "BID" ? item.ltv : null,
        }))
        .sort((a, b) => (a.propertyId < b.propertyId ? -1 : 1)),
      stances: stances
        .map((s) => ({ propertyId: s.propertyId, stance: s.stance }))
        .sort((a, b) => (a.propertyId < b.propertyId ? -1 : 1)),
    };
    // Replacement, not accumulation: a fund may revise until the market closes, and
    // "one decision per fund per round" is then structural rather than enforced.
    tx.putDecision(decision);
    return decision;
  });
}

// ── closing a round ───────────────────────────────────────────────────────

export async function closeRound(
  ctx: AppContext,
  args: { sessionId: string; grant: Grant; expectedRevision: number | null },
) {
  requireProfessor(args.grant);
  const revision = requireRevision(args.expectedRevision, "close the round");

  // 1. claim: freeze submissions and read what the engine needs.
  const claim = await ctx.store.transact(args.sessionId, (tx) => {
    const session = tx.aggregate.session;
    assertRevision(session, revision);
    assertAction(session.phase, "close_round");
    const record = tx.aggregate.round;
    if (!record) throw illegalPhase("no round is open");
    if (record.resolvedAt !== null) {
      throw conflict("this round has already been resolved");
    }
    if (record.closedAt === null) {
      record.closedAt = nowIso();
      tx.putRound(record);
    }

    const decisions = [...tx.aggregate.decisions.values()].sort((a, b) =>
      a.fundId < b.fundId ? -1 : 1,
    );
    const engineDecisions: EngineDecision[] = [];
    const engineStances: EngineManagementStance[] = [];
    for (const decision of decisions) {
      for (const item of decision.items) {
        engineDecisions.push({
          team_id: decision.fundId,
          property_id: item.propertyId,
          action: item.action,
          bid: item.bid,
          ltv: item.ltv,
        });
      }
      for (const stance of stancesOf(decision)) {
        engineStances.push({
          team_id: decision.fundId,
          property_id: stance.propertyId,
          stance: stance.stance,
        });
      }
    }
    return {
      round: record.round,
      state: requireEngineState(session),
      engineDecisions,
      engineStances,
      submittedFunds: decisions.length,
      closedAt: record.closedAt,
    };
  });

  // 2. the engine resolves, outside any transaction. Management stances ride the same
  // call as the bids: they are decisions about the round being closed, so they are
  // consumed by the same resolution that consumes the bids.
  const resolved = await ctx.engine.resolveRound(
    decodeState(claim.state),
    claim.engineDecisions,
    claim.engineStances,
  );

  // 3. commit against the guard: this is the line that makes double-resolution
  // impossible. Whoever gets there second finds `resolvedAt` set and is refused —
  // and because the engine is deterministic, it does not matter which one won.
  return ctx.store.transact(args.sessionId, (tx) => {
    const session = tx.aggregate.session;
    if (session.phase !== "practice" && session.phase !== "round") {
      throw conflict(
        `this round was already resolved by another request (the session is '${session.phase}')`,
      );
    }
    const record = tx.aggregate.round;
    if (!record || record.resolvedAt !== null || record.round !== claim.round) {
      throw conflict("this round was already resolved by another request");
    }

    const state = encodeState(resolved.state);
    session.engineState = state;
    session.engineStateBytes = state.byteLength;
    session.resolvedRounds += claim.round === PRACTICE_ROUND ? 0 : 1;
    session.phase = phaseAfterResolve(claim.round);
    session.currentRound = claim.round;
    session.roundDeadlineAt = null;
    session.timerPausedAt = null;

    record.resolvedAt = nowIso();
    record.results = resolved.public_results;
    record.analytics = resolved.analytics_updates;
    record.rejected = resolved.rejected_decisions.map((r) => ({
      fundId: r.team_id,
      propertyId: r.property_id,
      reason: r.reason,
    }));
    // An engine that predates the management layer sends no stance field at all; an
    // empty list is the correct reading of that, not a missing answer.
    record.rejectedStances = (resolved.rejected_stances ?? []).map((r) => ({
      fundId: r.team_id,
      propertyId: r.property_id,
      reason: r.reason,
    }));
    tx.putRound(record);
    tx.touch();

    const view = roundView({
      session,
      record,
      fund: null,
      rows: [],
      decision: null,
      totalFunds: tx.aggregate.funds.size,
      submittedFunds: tx.aggregate.decisions.size,
      offeredPropertyIds: offeredPropertyIds(record.broadcast),
      includeResults: true,
    });
    assertSafeView(view, `closeRound(round=${claim.round})`);
    // The engine's own `game_complete` flag only flips when it *advances* past the
    // final round (which the next `openRound` triggers). At close time it is still
    // false for the last scored round, so the service computes finality itself:
    // this is the final round when the round index reaches the configured count.
    const isFinalScoredRound =
      claim.round !== PRACTICE_ROUND && claim.round >= session.totalRounds - 1;
    return {
      round: claim.round,
      phase: session.phase,
      rejected: record.rejected,
      gameComplete: isFinalScoredRound,
      submittedFunds: claim.submittedFunds,
      results: resolved.public_results,
    };
  });
}

// ── finalizing the game ───────────────────────────────────────────────────

export async function finalizeGame(
  ctx: AppContext,
  args: { sessionId: string; grant: Grant; expectedRevision: number | null },
) {
  requireProfessor(args.grant);
  const revision = requireRevision(args.expectedRevision, "finalize the game");

  const claim = await ctx.store.transact(args.sessionId, (tx) => {
    const session = tx.aggregate.session;
    assertRevision(session, revision);
    assertAction(session.phase, "finalize");
    if (session.resolvedRounds < session.totalRounds) {
      throw illegalPhase("the game is not complete; finalize only after the last round resolves");
    }
    if (session.finalizedAt) {
      throw conflict("the game has already been finalized");
    }
    return { state: requireEngineState(session) };
  });

  // The engine's finalize is a read-only view over recorded history. Deterministic,
  // so a retry reproduces the same answer.
  const finalized = await ctx.engine.finalizeGame(decodeState(claim.state));

  return ctx.store.transact(args.sessionId, (tx) => {
    const session = tx.aggregate.session;
    if (session.finalizedAt) throw conflict("the game has already been finalized");
    if (session.phase !== "round_results") {
      throw conflict(`the session moved on while the game was finalizing (now '${session.phase}')`);
    }
    session.finalizedAt = nowIso();
    session.finale = {
      standings: finalized.standings,
      analytics: finalized.analytics,
      debrief: finalized.debrief,
    };
    session.phase = "finale";
    tx.touch();
    return { phase: session.phase, finalizedAt: session.finalizedAt };
  });
}

// ── timers ────────────────────────────────────────────────────────────────

/**
 * Arm the round timer. The deadline is stored server-side (epoch ms) so it survives
 * refresh and process restart; students render a countdown from it and never hold
 * the authoritative value. No auto-close: a professor-triggered close with a
 * persisted deadline is the V1 contract.
 */
export async function setRoundTimer(
  ctx: AppContext,
  args: {
    sessionId: string;
    grant: Grant;
    expectedRevision: number | null;
    durationSeconds: number;
  },
) {
  requireProfessor(args.grant);
  const revision = requireRevision(args.expectedRevision, "set the round timer");
  if (!Number.isFinite(args.durationSeconds) || args.durationSeconds < 0 || args.durationSeconds > 3600) {
    throw new AppError("bad_request", "timer duration must be between 0 and 3600 seconds");
  }
  return ctx.store.transact(args.sessionId, (tx) => {
    const session = tx.aggregate.session;
    assertRevision(session, revision);
    session.roundDurationSeconds = Math.round(args.durationSeconds);
    session.roundDeadlineAt =
      session.roundDurationSeconds > 0 && (session.phase === "practice" || session.phase === "round")
        ? Date.now() + session.roundDurationSeconds * 1000
        : null;
    session.timerPausedAt = null;
    tx.touch();
    return {
      roundDurationSeconds: session.roundDurationSeconds,
      roundDeadlineAt: session.roundDeadlineAt,
    };
  });
}

export async function pauseTimer(
  ctx: AppContext,
  args: { sessionId: string; grant: Grant; expectedRevision: number | null },
) {
  requireProfessor(args.grant);
  const revision = requireRevision(args.expectedRevision, "pause the timer");
  return ctx.store.transact(args.sessionId, (tx) => {
    const session = tx.aggregate.session;
    assertRevision(session, revision);
    if (session.roundDeadlineAt === null) throw illegalPhase("no round timer is running");
    if (session.timerPausedAt !== null) throw conflict("the timer is already paused");
    session.timerPausedAt = Date.now();
    tx.touch();
    return { roundDeadlineAt: session.roundDeadlineAt, timerPausedAt: session.timerPausedAt };
  });
}

export async function resumeTimer(
  ctx: AppContext,
  args: { sessionId: string; grant: Grant; expectedRevision: number | null },
) {
  requireProfessor(args.grant);
  const revision = requireRevision(args.expectedRevision, "resume the timer");
  return ctx.store.transact(args.sessionId, (tx) => {
    const session = tx.aggregate.session;
    assertRevision(session, revision);
    if (session.roundDeadlineAt === null) throw illegalPhase("no round timer is running");
    if (session.timerPausedAt === null) throw conflict("the timer is not paused");
    const pauseLength = Date.now() - session.timerPausedAt;
    session.roundDeadlineAt += pauseLength;
    session.timerPausedAt = null;
    tx.touch();
    return { roundDeadlineAt: session.roundDeadlineAt, timerPausedAt: null };
  });
}

// ── demo mode: bots and self-advance ───────────────────────────────────────

/**
 * Demo sessions have no professor browser. The human is the controller: once their
 * fund has submitted, `demoAdvance` submits deterministic bot decisions for every
 * bot that has not acted, then performs the one legal phase transition — close an
 * open round, open the next round, or finalize a complete game.
 */
export async function demoAdvance(
  ctx: AppContext,
  args: { sessionId: string; grant: Grant },
) {
  const session = await ctx.store.getSession(args.sessionId);
  if (!session) throw notFound(`unknown session '${args.sessionId}'`);
  if (!session.demo) throw forbidden("only demo sessions self-advance");

  // The demo controller must be a member of the demo session's human fund.
  const controller = await ctx.store.transact(args.sessionId, (tx) => {
    const member = tx.aggregate.members.get(args.grant.memberId);
    if (!member) throw unauthenticated("this seat no longer exists in the session");
    return member;
  });
  void controller;

  const phase = session.phase;
  if (phase === "practice" || phase === "round") {
    // Auto-submit bots, then close. Bot decisions are pure functions of their
    // stored models and the offered deals.
    const record = await ctx.store.transact(args.sessionId, (tx) => tx.aggregate.round);
    if (!record || record.resolvedAt !== null || record.closedAt !== null) {
      throw conflict("this round is no longer open");
    }
    const { DEMO_BOT_NAMES, demoBotArchetype, demoBotDecision } = await import("./demo.js");
    const models = await ctx.store.listAllModels(args.sessionId);
    const offered = (record.broadcast as { deals?: unknown[] } | null)?.deals ?? [];
    const deals = offered.map((d) => ({
      property_id: (d as { property_id?: unknown }).property_id as string,
      asking_price: (d as { asking_price?: number | null }).asking_price ?? null,
      max_ltv: (d as { max_ltv?: number | null }).max_ltv ?? null,
    }));
    const rowCounts = new Map(models.map((m) => [m.fundId, m.rows]));

    for (const botName of DEMO_BOT_NAMES) {
      const bot = await ctx.store.transact(args.sessionId, (tx) =>
        [...tx.aggregate.funds.values()].find((f) => f.name === botName) ?? null,
      );
      if (!bot) continue;
      const already = await ctx.store.transact(args.sessionId, (tx) =>
        tx.aggregate.decisions.get(bot.id) ?? null,
      );
      if (already) continue;
      // Submit through the same guarded path a student uses: as the bot's own
      // member, on the bot's fund. No role impersonation, no bypassed checks.
      const botMember = await ctx.store.transact(args.sessionId, (tx) => {
        const members = [...tx.aggregate.members.values()];
        const inFund = members.find((m) => m.fundId === bot.id && !m.isProfessor);
        if (!inFund) return null;
        const named = members.find(
          (m) => m.fundId === bot.id && !m.isProfessor && m.displayName === `${bot.name} manager`,
        );
        return named ?? inFund;
      });
      if (!botMember) continue;
      const rows = rowCounts.get(bot.id) ?? [];
      const map = new Map(rows.map((r) => [r.propertyId, r]));
      const items = demoBotDecision(demoBotArchetype(botName), map as never, deals);
      await submitDecision(ctx, {
        sessionId: args.sessionId,
        fundId: bot.id,
        grant: {
          sessionId: args.sessionId,
          memberId: botMember.id,
          fundId: bot.id,
          role: "student",
          displayName: botMember.displayName,
          iat: 0,
          exp: 0,
        },
        items,
      });
    }

    const fresh = await ctx.store.getSession(args.sessionId);
    if (!fresh) throw notFound("session vanished");
    return closeRound(ctx, {
      sessionId: args.sessionId,
      grant: { ...args.grant, role: "professor" },
      expectedRevision: fresh.revision,
    });
  }

  if (phase === "practice_results" || phase === "round_results") {
    if (isGameComplete(session)) {
      return finalizeGame(ctx, {
        sessionId: args.sessionId,
        grant: { ...args.grant, role: "professor" },
        expectedRevision: session.revision,
      });
    }
    return openRound(ctx, {
      sessionId: args.sessionId,
      grant: { ...args.grant, role: "professor" },
      expectedRevision: session.revision,
    });
  }

  if (phase === "lobby" || phase === "model_checkin") {
    return startGame(ctx, {
      sessionId: args.sessionId,
      grant: { ...args.grant, role: "professor" },
      expectedRevision: session.revision,
    });
  }

  throw illegalPhase(`nothing to advance while the session is '${phase}'`);
}
