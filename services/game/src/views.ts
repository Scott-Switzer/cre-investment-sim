/**
 * Player-visible projections.
 *
 * Every payload that reaches a browser is built here, by **naming** the fields it
 * exposes. Nothing is produced by taking a stored document and deleting keys:
 * subtraction fails open the first time a field is added, and the field that would
 * leak is the engine snapshot — the whole game, including every reserve price and
 * every future outcome.
 *
 * `assertSafeView` is called on the way out, so the guarantee is enforced at runtime
 * rather than documented and hoped for. It checks three things that are each a real
 * failure mode:
 *
 *   1. No engine snapshot reaches a client, under any key name.
 *   2. No `Uint8Array` reaches a client — that type *is* the snapshot in this
 *      service, so its presence anywhere is a leak by construction.
 *   3. A student's own forecast and decision are present only for their own fund.
 *
 * Two things this module deliberately does *not* do: it does not compute game
 * numbers (the engine's projections are passed through verbatim, because the engine
 * is the only authority and it already asserts its own payloads are clean), and it
 * does not decide what phase the client is in.
 */

import type {
  DecisionState,
  FundState,
  MemberState,
  ModelRow,
  RoundRecord,
  SessionState,
} from "./domain.js";
import { isGameComplete, PRACTICE_ROUND, roundLabel } from "./domain.js";

/** The engine snapshot and anything shaped like it must never appear in a view. */
export function assertSafeView(view: unknown, where: string): void {
  const found: string[] = [];
  walk(view, where, found, 0);
  if (found.length > 0) {
    throw new Error(
      `integrity: ${where} would leak server-only state (${found.join(", ")}). ` +
        "This is a bug in a view builder, not a client error.",
    );
  }
}

function walk(value: unknown, path: string, found: string[], depth: number): void {
  if (depth > 12) return;
  if (value === null || value === undefined) return;
  if (value instanceof Uint8Array) {
    found.push(`${path} is a byte buffer (the engine snapshot shape)`);
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, i) => walk(item, `${path}[${i}]`, found, depth + 1));
    return;
  }
  if (typeof value === "object") {
    for (const [key, inner] of Object.entries(value as Record<string, unknown>)) {
      if (key === "engineState" || key === "engine_state" || key === "engineStateBytes") {
        found.push(`${path}.${key}`);
        continue;
      }
      walk(inner, `${path}.${key}`, found, depth + 1);
    }
  }
}

// ── session ───────────────────────────────────────────────────────────────

/** What a student should be able to answer without being told: where are we, and
 * what happens next. Server-owned, because a client that guesses the phase is
 * wrong exactly once, in front of a class. */
function nextStepFor(session: SessionState): string {
  switch (session.phase) {
    case "lobby":
      return "Waiting for your professor to open model check-in.";
    case "model_checkin":
      return session.engineCreatedAt
        ? "Your professor has started the game."
        : "Upload your team's model and lock it. Your professor starts the game when every fund has locked.";
    case "practice":
      return "Practice is open. Submit your decision; your professor will close the market.";
    case "practice_results":
      return "Practice is resolved. Your professor opens Round 1 next.";
    case "round":
      // Through `roundLabel`, not `currentRound + 1`, so this cannot render "Round 0"
      // for the practice round if the phase and the round number ever disagree.
      return `${roundLabel(session.currentRound, session.totalRounds)} is open. Submit your decision before your professor closes the market.`;
    case "round_results":
      return isGameComplete(session)
        ? "All rounds are complete. Your professor will open the final debrief."
        : "Results are in. Your professor opens the next round.";
    case "finale":
      return "The game is complete.";
  }
}

export interface SessionView {
  id: string;
  name: string;
  phase: SessionState["phase"];
  currentRound: number;
  roundLabel: string;
  isPracticeRound: boolean;
  totalRounds: number;
  practiceEnabled: boolean;
  resolvedRounds: number;
  gameComplete: boolean;
  revision: number;
  mode: SessionState["mode"];
  maxTeamSize: number;
  bundleId: string;
  bundleDisplayName: string;
  poolCount: number;
  candidatePoolHash: string;
  nextStep: string;
}

export function sessionView(session: SessionState): SessionView {
  return {
    id: session.id,
    name: session.name,
    phase: session.phase,
    currentRound: session.currentRound,
    roundLabel: roundLabel(session.currentRound, session.totalRounds),
    isPracticeRound: session.currentRound === PRACTICE_ROUND,
    totalRounds: session.totalRounds,
    practiceEnabled: session.practiceEnabled,
    resolvedRounds: session.resolvedRounds,
    gameComplete: isGameComplete(session),
    revision: session.revision,
    mode: session.mode,
    maxTeamSize: session.maxTeamSize,
    bundleId: session.bundleId,
    bundleDisplayName: session.bundleDisplayName,
    poolCount: session.poolCount,
    candidatePoolHash: session.candidatePoolHash,
    nextStep: nextStepFor(session),
  };
}

/** The professor's view of a session adds the join code and nothing hidden. */
export function professorSessionView(session: SessionState): SessionView & { joinCode: string } {
  return { ...sessionView(session), joinCode: session.joinCode };
}

// ── funds and members ─────────────────────────────────────────────────────

export interface FundView {
  id: string;
  name: string;
  memberCount: number;
  modelStatus: FundState["modelStatus"];
  modelName: string | null;
  modelLockedAt: string | null;
  modelRowCount: number;
}

/**
 * A fund, as anyone may see it.
 *
 * Note what a fund's model status *does* reveal and what it must not: whether a team
 * has locked, which is a lobby/classroom fact, versus what their forecast says, which
 * is theirs alone until the reveal.
 */
export function fundView(fund: FundState): FundView {
  return {
    id: fund.id,
    name: fund.name,
    memberCount: fund.memberIds.length,
    modelStatus: fund.modelStatus,
    modelName: fund.modelName,
    modelLockedAt: fund.modelLockedAt,
    modelRowCount: fund.modelRowCount,
  };
}

/** The owning fund's own view, which additionally carries its check-in report. */
export function fundOwnerView(fund: FundState): FundView & { forecastSummary: FundState["forecastSummary"] } {
  return { ...fundView(fund), forecastSummary: fund.forecastSummary };
}

export interface MemberView {
  id: string;
  displayName: string;
  fundId: string | null;
  isProfessor: boolean;
}

export function memberView(member: MemberState): MemberView {
  return {
    id: member.id,
    displayName: member.displayName,
    fundId: member.fundId,
    isProfessor: member.isProfessor,
  };
}

// ── the round, for one fund ───────────────────────────────────────────────

/**
 * The fund's own forecast and policy, restricted to the properties actually offered.
 *
 * Restricted deliberately: the stored model covers all 120 candidates, and a round
 * offers four. Sending all 120 on every round view would put a rival's screen one
 * accidental render away from showing a fund's whole forecast, and it would make the
 * response 30× larger for no benefit.
 */
export function forecastForProperties(rows: ModelRow[], propertyIds: readonly string[]) {
  const offered = new Set(propertyIds);
  return rows
    .filter((row) => offered.has(row.propertyId))
    .sort((a, b) => (a.propertyId < b.propertyId ? -1 : 1))
    .map((row) => ({
      propertyId: row.propertyId,
      forecast: row.forecast,
      policy: row.policy,
    }));
}

export function decisionView(decision: DecisionState) {
  return {
    fundId: decision.fundId,
    round: decision.round,
    submittedAt: decision.submittedAt,
    items: [...decision.items]
      .sort((a, b) => (a.propertyId < b.propertyId ? -1 : 1))
      .map((item) => ({ ...item })),
  };
}

export interface RoundView {
  round: number;
  roundLabel: string;
  isPractice: boolean;
  openedAt: string;
  closedAt: string | null;
  resolvedAt: string | null;
  isOpenForSubmissions: boolean;
  /** The engine's own player-safe projection, passed through verbatim. */
  public: unknown;
  /** The fund's own forecast, for the offered properties only. */
  myForecast: ReturnType<typeof forecastForProperties>;
  /** The fund's own submission, or null. Never another fund's. */
  myDecision: ReturnType<typeof decisionView> | null;
  submittedFunds: number;
  totalFunds: number;
  results: unknown | null;
  rejected: { fundId: string; propertyId: string; reason: string }[];
}

export function roundView(args: {
  session: SessionState;
  record: RoundRecord | null;
  fund: FundState | null;
  rows: ModelRow[];
  decision: DecisionState | null;
  totalFunds: number;
  submittedFunds: number;
  offeredPropertyIds: readonly string[];
  includeResults: boolean;
}): RoundView | null {
  const { session, record } = args;
  if (!record) return null;
  return {
    round: record.round,
    roundLabel: roundLabel(record.round, session.totalRounds),
    isPractice: record.round === PRACTICE_ROUND,
    openedAt: record.openedAt,
    closedAt: record.closedAt,
    resolvedAt: record.resolvedAt,
    isOpenForSubmissions: record.resolvedAt === null && record.closedAt === null,
    public: record.broadcast,
    myForecast: args.fund ? forecastForProperties(args.rows, args.offeredPropertyIds) : [],
    myDecision: args.decision ? decisionView(args.decision) : null,
    submittedFunds: args.submittedFunds,
    totalFunds: args.totalFunds,
    results: args.includeResults ? record.results : null,
    rejected: record.rejected.map((r) => ({ ...r })),
  };
}

/**
 * The professor's submission grid.
 *
 * Withholds the bids themselves even from the professor. The grid exists to answer
 * "who is in" and "who deviated from their own policy", and a professor's screen is
 * routinely projected for the room. Amounts would make that projection a leak, so
 * they are simply not in the payload — the sealed auction stays sealed until the
 * reveal, for every audience.
 *
 * A naming note that is really a correctness note. The engine's analytics report
 * `override_count`, which counts only overrides on properties a fund **won** — it is
 * written when the auction result comes back. The two counts below are about
 * submissions: a manager who bid above their own ceiling *chose* to do so whether or
 * not the market awarded them the asset, and that is the fact worth showing a
 * professor mid-round. They are therefore named for submissions rather than reusing
 * the engine's word, because two different numbers under one name is how a debrief
 * ends up arguing with itself.
 */
export function submissionGrid(args: {
  funds: FundState[];
  decisions: Map<string, DecisionState>;
  rows: Map<string, ModelRow[]>;
}) {
  return args.funds
    .map((fund) => {
      const decision = args.decisions.get(fund.id) ?? null;
      const modelRows = args.rows.get(fund.id) ?? [];
      const policyFor = new Map(modelRows.map((row) => [row.propertyId, row.policy]));
      let bidsAboveOwnCeiling = 0;
      let ltvAboveOwnTarget = 0;
      let bids = 0;
      for (const item of decision?.items ?? []) {
        if (item.action !== "BID") continue;
        bids += 1;
        const policy = policyFor.get(item.propertyId);
        if (!policy) continue;
        if (item.bid !== null && item.bid > policy.maxBid + 1e-9) bidsAboveOwnCeiling += 1;
        if (item.ltv !== null && item.ltv > policy.targetLtv + 1e-9) ltvAboveOwnTarget += 1;
      }
      return {
        fundId: fund.id,
        fundName: fund.name,
        submitted: decision !== null,
        submittedAt: decision?.submittedAt ?? null,
        bids,
        passes: (decision?.items.length ?? 0) - bids,
        bidsAboveOwnCeiling,
        ltvAboveOwnTarget,
      };
    })
    .sort((a, b) => (a.fundName < b.fundName ? -1 : 1));
}
