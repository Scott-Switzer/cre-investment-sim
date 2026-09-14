/**
 * Sessions: creation, joining, and the state view every client polls.
 *
 * The read path is where a 70-browser class is won or lost, so it is built around
 * two decisions.
 *
 * **Reads are consistent, and free of revision bumps.** Building a view runs inside
 * a transaction with no writes: Firestore reads the session and its subcollections
 * at one commit, so the response cannot show a fund that has locked while the
 * session revision predates that lock. A cheaper eventual-consistency read would
 * produce exactly that, and it would look like a bug in the game rather than in the
 * read.
 *
 * **A poll that has nothing new costs one document.** `?since=<revision>` short-
 * circuits before any of the heavy work — no fund collection, no model rows, no view
 * construction. With SSE carrying the revision, a client fetches the full state only
 * when something actually changed.
 */

import { AppError, conflict, forbidden, notFound, unauthenticated } from "./errors.js";
import { canonicalJoinCode, isJoinCodeShaped, newId, newJoinCode, nowIso } from "./ids.js";
import { assertSafeView, fundOwnerView, fundView, memberView, professorSessionView, roundView, sessionView, submissionGrid } from "./views.js";
import { offeredPropertyIds, pool } from "./context.js";
import type { AppContext } from "./context.js";
import { passcodeMatches, newGrant, type Grant } from "./auth.js";
import { DEMO_BOT_NAMES } from "./demo.js";
import type { FundState, MemberState, ModelRow, SessionState } from "./domain.js";
import { PRACTICE_ROUND } from "./domain.js";
import type { BundleSummary } from "./engineClient.js";

export interface CreateSessionInput {
  name: string;
  bundleId?: string;
  professorPasscode: string;
  professorName?: string;
  /** Funds the professor pre-creates. Students may also create their own. */
  fundNames?: string[];
  maxTeamSize?: number;
  mode?: "team" | "individual";
  practiceEnabled?: boolean;
  totalRounds?: number;
  /** Round timer duration in seconds; 0 = no timer. */
  roundTimerSeconds?: number;
}

export interface CreateSessionResult {
  session: SessionState;
  grant: Grant;
  joinCode: string;
}

export interface JoinInput {
  joinCode: string;
  displayName: string;
  /** Join an existing fund by id, or omit and name a new one. */
  fundId?: string | null;
  newFundName?: string | null;
}

export interface JoinResult {
  sessionId: string;
  grant: Grant;
  fundId: string;
  createdFund: boolean;
}

export async function listBundles(ctx: AppContext): Promise<BundleSummary[]> {
  const { bundles } = await ctx.engine.listBundles();
  return bundles;
}

export async function createSession(
  ctx: AppContext,
  input: CreateSessionInput,
): Promise<CreateSessionResult> {
  if (!passcodeMatches(input.professorPasscode ?? "", ctx.config.professorPasscode)) {
    throw forbidden("that professor passcode is not correct");
  }
  const name = input.name?.trim();
  if (!name) throw new AppError("bad_request", "a session name is required");

  const available = await listBundles(ctx);
  const bundleId = input.bundleId ?? available[0]?.bundle_id;
  if (!bundleId) {
    throw new AppError("engine_unavailable", "the engine reports no datasets to choose from");
  }
  const chosen = available.find((b) => b.bundle_id === bundleId);
  if (!chosen) {
    throw new AppError("bad_request", `unknown dataset '${bundleId}'`, {
      available: available.map((b) => b.bundle_id),
    });
  }

  // The pool is fetched now, not at first upload, so a professor finds out
  // immediately that a dataset will not load rather than at check-in in class.
  const poolResponse = await pool(ctx, bundleId);

  const now = nowIso();
  const sessionId = newId("sess");
  // Clamped only to catch a typo, not to enforce pedagogy. A professor may legitimately
  // run one big fund for a whole class, so the ceiling is generous.
  const maxTeamSize = Math.max(1, Math.min(40, input.maxTeamSize ?? 4));
  const session: SessionState = {
    id: sessionId,
    name,
    joinCode: newJoinCode(),
    bundleId,
    bundleDisplayName: chosen.display_name,
    candidatePoolHash: poolResponse.candidate_pool_hash,
    poolCount: poolResponse.pool_count,
    mode: input.mode === "individual" ? "individual" : "team",
    maxTeamSize,
    totalRounds: Math.max(1, Math.min(8, input.totalRounds ?? 4)),
    practiceEnabled: input.practiceEnabled !== false,
    demo: false,
    roundDurationSeconds: Math.max(0, Math.min(3600, Math.round(input.roundTimerSeconds ?? 0))),
    roundDeadlineAt: null,
    timerPausedAt: null,
    phase: "lobby",
    currentRound: PRACTICE_ROUND,
    resolvedRounds: 0,
    revision: 0,
    engineState: null,
    engineStateBytes: 0,
    engineCreatedAt: null,
    finale: null,
    finalizedAt: null,
    createdAt: now,
    updatedAt: now,
  };

  // An omitted list means "make me one fund to start"; an explicitly empty list means
  // "no funds yet, my teams will create their own". Those are different requests, and
  // conflating them silently invents a fund the professor did not ask for.
  const names = (input.fundNames === undefined ? ["Fund 1"] : input.fundNames)
    .filter((f) => f.trim())
    .slice(0, 24);
  const funds: FundState[] = names.map((fundName, index) => makeFund(sessionId, fundName, now, index));

  await ctx.store.createSession(session, funds[0] ?? null);
  // A professor pre-creating several funds is one operation; the store's atomic
  // primitive only covers the session and its first fund, so the rest follow.
  for (const extra of funds.slice(1)) {
    await ctx.store.transact(sessionId, (tx) => {
      tx.putFund(extra);
    });
  }

  const professorMember: MemberState = {
    id: newId("prof"),
    sessionId,
    displayName: input.professorName?.trim() || "Professor",
    fundId: null,
    isProfessor: true,
    joinedAt: now,
    lastSeenAt: now,
  };
  await ctx.store.transact(sessionId, (tx) => {
    tx.putMember(professorMember);
  });

  const stored = (await ctx.store.getSession(sessionId)) ?? session;
  return {
    session: stored,
    grant: newGrant(
      {
        sessionId,
        memberId: professorMember.id,
        fundId: null,
        role: "professor",
        displayName: professorMember.displayName,
      },
      ctx.config.sessionTtlSeconds,
    ),
    joinCode: stored.joinCode,
  };
}

function makeFund(sessionId: string, name: string, now: string, index: number): FundState {
  return {
    id: `fund_${index + 1}_${newId("f").split("_")[1]}`,
    sessionId,
    name: name.trim(),
    memberIds: [],
    modelStatus: "none",
    modelName: null,
    modelLockedAt: null,
    modelRowCount: 0,
    modelValidatedAt: null,
    forecastSummary: null,
    createdAt: now,
  };
}

/** Put an existing session's professor cookie back in a browser after a refresh. */
export async function professorSignIn(
  ctx: AppContext,
  sessionId: string,
  passcode: string,
  displayName?: string,
): Promise<Grant> {
  if (!passcodeMatches(passcode ?? "", ctx.config.professorPasscode)) {
    throw forbidden("that professor passcode is not correct");
  }
  const session = await ctx.store.getSession(sessionId);
  if (!session) throw notFound(`unknown session '${sessionId}'`);
  const now = nowIso();
  const member: MemberState = {
    id: newId("prof"),
    sessionId,
    displayName: displayName?.trim() || "Professor",
    fundId: null,
    isProfessor: true,
    joinedAt: now,
    lastSeenAt: now,
  };
  await ctx.store.transact(sessionId, (tx) => {
    tx.putMember(member);
  });
  return newGrant(
    { sessionId, memberId: member.id, fundId: null, role: "professor", displayName: member.displayName },
    ctx.config.sessionTtlSeconds,
  );
}

export async function joinSession(ctx: AppContext, input: JoinInput): Promise<JoinResult> {
  const displayName = input.displayName?.trim();
  if (!displayName) throw new AppError("bad_request", "a display name is required");
  if (!isJoinCodeShaped(input.joinCode ?? "")) {
    throw new AppError("bad_request", "a six-character join code is required");
  }

  const sessionId = await ctx.store.findSessionByJoinCode(input.joinCode);
  if (!sessionId) {
    throw notFound(
      `no session has the join code '${canonicalJoinCode(input.joinCode)}'. Check it with your professor.`,
    );
  }

  const memberId = newId("mem");
  let createdFund = false;
  let fundId = "";

  await ctx.store.transact(sessionId, (tx) => {
    const session = tx.aggregate.session;
    if (session.phase === "finale") {
      throw conflict("this session has finished");
    }
    const now = nowIso();

    if (input.fundId) {
      const fund = tx.aggregate.funds.get(input.fundId);
      if (!fund) throw notFound(`unknown fund '${input.fundId}'`);
      if (session.mode === "team" && fund.memberIds.length >= session.maxTeamSize) {
        throw conflict(
          `'${fund.name}' is full (${fund.memberIds.length} of ${session.maxTeamSize}). ` +
            "Join another fund or create one.",
        );
      }
      fund.memberIds = [...fund.memberIds, memberId].sort();
      tx.putFund(fund);
      fundId = fund.id;
    } else {
      const requested = (input.newFundName ?? "").trim();
      if (!requested) {
        throw new AppError(
          "bad_request",
          "choose a fund to join, or give a name for a new one",
        );
      }
      if (tx.aggregate.funds.size >= 24) {
        throw conflict("this session already has the maximum number of funds");
      }
      const existing = [...tx.aggregate.funds.values()].find(
        (f) => f.name.toLowerCase() === requested.toLowerCase(),
      );
      if (existing) {
        // Joining by name is friendlier than by opaque id, and it is what a student
        // typing a teammate's fund name expects to happen.
        if (session.mode === "team" && existing.memberIds.length >= session.maxTeamSize) {
          throw conflict(`'${existing.name}' is full`);
        }
        existing.memberIds = [...existing.memberIds, memberId].sort();
        tx.putFund(existing);
        createdFund = false;
        fundId = existing.id;
      } else {
        const index = tx.aggregate.funds.size;
        const fund: FundState = {
          id: `fund_${index + 1}_${newId("f").split("_")[1]}`,
          sessionId,
          name: requested,
          memberIds: [memberId],
          modelStatus: "none",
          modelName: null,
          modelLockedAt: null,
          modelRowCount: 0,
          modelValidatedAt: null,
          forecastSummary: null,
          createdAt: now,
        };
        tx.putFund(fund);
        createdFund = true;
        fundId = fund.id;
      }
    }

    const member: MemberState = {
      id: memberId,
      sessionId,
      displayName,
      fundId,
      isProfessor: false,
      joinedAt: now,
      lastSeenAt: now,
    };
    tx.putMember(member);
  });

  return {
    sessionId,
    createdFund,
    fundId,
    grant: newGrant(
      { sessionId, memberId, fundId, role: "student", displayName },
      ctx.config.sessionTtlSeconds,
    ),
  };
}

/** Re-attach a seat by display name: the recovery path when a browser loses cookies. */
export async function reclaimSeat(
  ctx: AppContext,
  sessionId: string,
  displayName: string,
): Promise<Grant> {
  const wanted = displayName.trim().toLowerCase();
  if (!wanted) throw new AppError("bad_request", "a display name is required");
  const member = await ctx.store.transact(sessionId, (tx) => {
    return (
      [...tx.aggregate.members.values()].find(
        (m) => !m.isProfessor && m.displayName.toLowerCase() === wanted,
      ) ?? null
    );
  });
  if (!member) throw notFound(`no seat named '${displayName}' in this session`);
  return newGrant(
    {
      sessionId,
      memberId: member.id,
      fundId: member.fundId,
      role: "student",
      displayName: member.displayName,
    },
    ctx.config.sessionTtlSeconds,
  );
}

// ── the state view ────────────────────────────────────────────────────────

export interface StateQuery {
  sessionId: string;
  grant: Grant;
  /** A revision the client already holds. When it matches, the heavy work is skipped. */
  since?: number | null;
}

export interface UnchangedView {
  unchanged: true;
  revision: number;
}

export async function buildStateView(
  ctx: AppContext,
  query: StateQuery,
): Promise<Record<string, unknown> | UnchangedView> {
  const session = await ctx.store.getSession(query.sessionId);
  if (!session) throw notFound(`unknown session '${query.sessionId}'`);
  if (query.since !== null && query.since !== undefined && query.since === session.revision) {
    // The whole point of the short-circuit: a browser that is already current costs
    // one document read and no view construction, however many are open.
    return { unchanged: true, revision: session.revision };
  }

  const isProfessor = query.grant.role === "professor";
  // Models are read before the transaction rather than inside it: the aggregate
  // deliberately excludes ~18 KB of rows per fund, and rows are immutable once
  // locked. The window is harmless — a fund's *status* comes from the aggregate, so
  // the lobby cannot show a lock that has not committed; only the forecast body a
  // team is looking at could be one edit stale, for a moment, during check-in.
  const models = await ctx.store.listAllModels(query.sessionId);
  const rowsByFund = new Map<string, ModelRow[]>(
    models.map((m) => [m.fundId, m.rows as ModelRow[]]),
  );

  const view = await ctx.store.transact(query.sessionId, (tx) => {
    const aggregate = tx.aggregate;
    const live = aggregate.session;
    const funds = [...aggregate.funds.values()].sort((a, b) => (a.name < b.name ? -1 : 1));
    const members = [...aggregate.members.values()].sort((a, b) =>
      a.displayName < b.displayName ? -1 : 1,
    );
    const me = aggregate.members.get(query.grant.memberId);
    if (!me) {
      // A signed cookie whose member is gone: the session was reset, or the record
      // was deleted. Distinguished from "bad signature" so the client can say
      // "this seat no longer exists" rather than "you are not signed in".
      throw unauthenticated("this seat no longer exists in the session; join again");
    }
    const myFund = me.fundId ? (aggregate.funds.get(me.fundId) ?? null) : null;

    const record = aggregate.round;
    const myDecision = myFund ? (aggregate.decisions.get(myFund.id) ?? null) : null;
    const offered = record ? offeredPropertyIds(record.broadcast) : [];
    const includeResults = record !== null && record.resolvedAt !== null;

    const round = roundView({
      session: live,
      record,
      fund: myFund,
      rows: myFund ? (rowsByFund.get(myFund.id) ?? []) : [],
      decision: myDecision,
      totalFunds: funds.length,
      submittedFunds: aggregate.decisions.size,
      offeredPropertyIds: offered,
      includeResults,
    });

    const payload: Record<string, unknown> = {
      session: isProfessor ? professorSessionView(live) : sessionView(live),
      you: {
        memberId: me.id,
        displayName: me.displayName,
        role: me.isProfessor ? "professor" : "student",
        fundId: me.fundId,
      },
      funds: funds.map(fundView),
      members: members.map(memberView),
      yourFund: myFund ? fundOwnerView(myFund) : null,
      round,
      // Final standings, analytics and debrief — present only after the professor
      // finalizes, and the same payload for every audience.
      finale: live.phase === "finale" ? live.finale : null,
      // Only for the professor, and only counts plus override tallies: never the
      // sealed amounts, because this screen is routinely projected.
      grid: isProfessor
        ? submissionGrid({
            funds,
            decisions: aggregate.decisions,
            rows: rowsByFund,
          })
        : null,
    };
    return payload;
  });

  assertSafeView(view, `stateView(session=${query.sessionId})`);
  return view;
}

export function requireGrant(grant: Grant | null, sessionId: string): Grant {
  if (!grant) throw unauthenticated("join this session first");
  if (grant.sessionId !== sessionId) {
    throw forbidden("your session cookie is for a different session");
  }
  return grant;
}

// ── demo sessions ──────────────────────────────────────────────────────────

/**
 * Create a demo session: one human fund plus three deterministic bots, with every
 * model pre-locked so the game can start immediately. Returns a student grant for
 * the human fund. Demo sessions self-advance through the demo endpoint — no
 * professor browser exists.
 */
export async function createDemoSession(
  ctx: AppContext,
  input: { displayName: string },
): Promise<{
  session: SessionState;
  grant: Grant;
  humanFundId: string;
  joinCode: string;
}> {
  const displayName = input.displayName?.trim() || "Demo Player";
  const available = await listBundles(ctx);
  const bundleId = available[0]?.bundle_id;
  if (!bundleId) {
    throw new AppError("engine_unavailable", "the engine reports no datasets to choose from");
  }
  const poolResponse = await pool(ctx, bundleId);

  const now = nowIso();
  const sessionId = newId("sess");
  const session: SessionState = {
    id: sessionId,
    name: "CRE Investment Committee — Demo",
    joinCode: newJoinCode(),
    bundleId,
    bundleDisplayName: available[0]!.display_name,
    candidatePoolHash: poolResponse.candidate_pool_hash,
    poolCount: poolResponse.pool_count,
    mode: "individual",
    maxTeamSize: 1,
    totalRounds: 4,
    practiceEnabled: false,
    demo: true,
    roundDurationSeconds: 0,
    roundDeadlineAt: null,
    timerPausedAt: null,
    // Models are pre-locked below, so the session is born one phase ahead of the
    // lobby: the demo controller's first advance is "start the game".
    phase: "model_checkin",
    currentRound: PRACTICE_ROUND,
    resolvedRounds: 0,
    revision: 0,
    engineState: null,
    engineStateBytes: 0,
    engineCreatedAt: null,
    finale: null,
    finalizedAt: null,
    createdAt: now,
    updatedAt: now,
  };

  const fundNames = ["You", ...DEMO_BOT_NAMES];
  const funds: FundState[] = fundNames.map((fundName, index) =>
    makeFund(sessionId, fundName, now, index),
  );
  const humanFund = funds[0]!;

  await ctx.store.createSession(session, humanFund);
  for (const extra of funds.slice(1)) {
    await ctx.store.transact(sessionId, (tx) => {
      tx.putFund(extra);
    });
  }

  // Lock a deterministic model for every fund, through the same ModelRecord path
  // a student's upload takes. The human's rows are the DEMO FORECAST archetype.
  const { HUMAN_ARCHETYPE, demoBotArchetype, demoModelRows } = await import("./demo.js");
  const poolDeals = (poolResponse.properties as unknown as {
    property_id: string;
    asking_price: number | null;
    max_ltv: number | null;
  }[]).map((p) => ({
    property_id: p.property_id,
    asking_price: p.asking_price,
    max_ltv: p.max_ltv,
  }));

  for (const fund of funds) {
    const archetype =
      fund.id === humanFund.id ? HUMAN_ARCHETYPE : demoBotArchetype(fund.name);
    const modelName =
      fund.id === humanFund.id ? "DEMO FORECAST (illustrative — not your own model)" : fund.name;
    const rows = demoModelRows(archetype, poolDeals, modelName);
    await ctx.store.putModel({
      sessionId,
      fundId: fund.id,
      modelName,
      rowCount: rows.length,
      validatedAt: now,
      lockedAt: now,
      rows,
    });
    await ctx.store.transact(sessionId, (tx) => {
      const stored = tx.aggregate.funds.get(fund.id);
      if (!stored) throw conflict(`fund '${fund.id}' vanished during demo setup`);
      stored.modelStatus = "locked";
      stored.modelName = modelName;
      stored.modelLockedAt = now;
      stored.modelValidatedAt = now;
      stored.modelRowCount = rows.length;
      tx.putFund(stored);
    });
  }

  const member: MemberState = {
    id: newId("mem"),
    sessionId,
    displayName,
    fundId: humanFund.id,
    isProfessor: false,
    joinedAt: now,
    lastSeenAt: now,
  };
  await ctx.store.transact(sessionId, (tx) => {
    tx.putMember(member);
  });

  const stored = (await ctx.store.getSession(sessionId)) ?? session;
  return {
    session: stored,
    grant: newGrant(
      {
        sessionId,
        memberId: member.id,
        fundId: humanFund.id,
        role: "student",
        displayName,
      },
      ctx.config.sessionTtlSeconds,
    ),
    humanFundId: humanFund.id,
    joinCode: stored.joinCode,
  };
}
