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

import { AppError, conflict, forbidden, illegalPhase } from "./errors.js";
import type { AppContext } from "./context.js";
import {
  assertMayActForFund,
  assertRevision,
  offeredPropertyIds,
  requireFund,
  requireMember,
  roundAcceptsSubmissions,
} from "./context.js";
import { assertAction, phaseAfterResolve, PRACTICE_ROUND, type DecisionItem, type RoundRecord, type SessionState } from "./domain.js";
import { assertSafeView, roundView } from "./views.js";
import { decodeState, encodeState, type EngineDecision } from "./engineClient.js";
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
      fundCount: funds.length,
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
  );

  // 3. commit against the guard.
  return ctx.store.transact(args.sessionId, (tx) => {
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

    const record: RoundRecord = {
      sessionId: args.sessionId,
      round,
      openedAt,
      closedAt: null,
      resolvedAt: null,
      broadcast: created.public,
      results: null,
      rejected: [],
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

    const state = encodeState(opened.state);
    const round = roundNumberOf(opened.public);
    session.engineState = state;
    session.engineStateBytes = state.byteLength;
    session.currentRound = round;
    session.phase = "round";

    tx.putRound({
      sessionId: args.sessionId,
      round,
      openedAt: nowIso(),
      closedAt: null,
      resolvedAt: null,
      broadcast: opened.public,
      results: null,
      rejected: [],
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
  expectedRevision?: number | null;
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
    }
    return {
      round: record.round,
      state: requireEngineState(session),
      engineDecisions,
      submittedFunds: decisions.length,
      closedAt: record.closedAt,
    };
  });

  // 2. the engine resolves, outside any transaction.
  const resolved = await ctx.engine.resolveRound(decodeState(claim.state), claim.engineDecisions);

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

    record.resolvedAt = nowIso();
    record.results = resolved.public_results;
    record.rejected = resolved.rejected_decisions.map((r) => ({
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
    return {
      round: claim.round,
      phase: session.phase,
      rejected: record.rejected,
      gameComplete: resolved.game_complete,
      submittedFunds: claim.submittedFunds,
      results: resolved.public_results,
    };
  });
}
