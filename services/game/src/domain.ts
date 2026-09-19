/**
 * The persisted shapes of a session, and the phase machine that governs it.
 *
 * Two rules govern everything below.
 *
 * **1. The engine is the only authority on game state.** Nothing in these documents
 * is a portfolio, a NAV or a ranking. The session holds one opaque engine snapshot
 * (`engineState`) and the engine's own published projections for the current round.
 * This service orders operations and stores results; it never does game arithmetic.
 *
 * **2. The phase is server-owned.** The client never decides which screen it is on.
 * A client that guesses will disagree with the professor's projector exactly once,
 * in front of a class. Every view carries `phase` and `revision`, and `/play` renders
 * from them.
 */

import type { ErrorCode } from "./errors.js";
import { AppError } from "./errors.js";

export const PRACTICE_ROUND = -1;

export type Phase =
  | "lobby"
  | "model_checkin"
  | "practice"
  | "practice_results"
  | "round"
  | "round_results"
  | "finale";

export type RoundStateName = "open" | "locked" | "resolved";

export type ModelStatus = "none" | "validated" | "locked";

/**
 * The seven phases and the single legal move out of each.
 *
 * Written as data rather than as nested `if`s so it can be asserted directly: the
 * transitions a professor may make are a *specification*, and a specification that
 * lives in a table is one a test can read and a reviewer can check. `null` means
 * "this phase is not advanced by a professor action" — `finale` is terminal, and the
 * two in-progress phases are left by resolving a round rather than by stepping.
 */
export interface Transition {
  readonly from: Phase;
  readonly action: ProfessorAction;
  readonly to: Phase;
}

export type ProfessorAction =
  | "begin_checkin"
  | "start_game"
  | "open_round"
  | "close_round"
  | "finalize";

export const TRANSITIONS: readonly Transition[] = [
  { from: "lobby", action: "begin_checkin", to: "model_checkin" },
  { from: "model_checkin", action: "start_game", to: "practice" },
  { from: "practice", action: "close_round", to: "practice_results" },
  { from: "practice_results", action: "open_round", to: "round" },
  { from: "round", action: "close_round", to: "round_results" },
  { from: "round_results", action: "open_round", to: "round" },
  { from: "round_results", action: "finalize", to: "finale" },
];

export function assertAction(phase: Phase, action: ProfessorAction): void {
  const legal = TRANSITIONS.some((t) => t.from === phase && t.action === action);
  if (!legal) {
    const available = TRANSITIONS.filter((t) => t.from === phase).map((t) => t.action);
    throw new AppError(
      "illegal_phase",
      `'${action}' is not legal while the session is in '${phase}'. ` +
        (available.length
          ? `Available here: ${available.join(", ")}.`
          : `'${phase}' is terminal.`),
    );
  }
}

/** True once the last scored round has been resolved. Derived, never stored twice. */
export function isGameComplete(session: SessionState): boolean {
  return session.resolvedRounds >= session.totalRounds;
}

/** The phase a session enters once its current round has resolved. */
export function phaseAfterResolve(round: number): Phase {
  return round === PRACTICE_ROUND ? "practice_results" : "round_results";
}

export function roundLabel(round: number, totalRounds: number): string {
  if (round === PRACTICE_ROUND) return "Practice";
  return `Round ${round + 1} of ${totalRounds}`;
}

// ── documents ─────────────────────────────────────────────────────────────

/**
 * The session document.
 *
 * `engineState` is the whole hidden game: it contains every reserve price and every
 * future outcome. In Firestore it is stored gzipped, which is not an optimisation —
 * a two-fund snapshot is 307 KB of JSON and a full class pushes past Firestore's
 * 1 MiB document ceiling. Compressed it is ~19 KB, and repetition across funds
 * compresses well, so the ceiling stops being a design constraint.
 *
 * It is classified SERVER_ONLY_ALWAYS in `docs/CRE_DATA_VISIBILITY.md`. No view
 * builder ever reads it, and a test asserts that a projection containing it fails.
 */
export interface SessionState {
  id: string;
  name: string;
  joinCode: string;
  bundleId: string;
  bundleDisplayName: string;
  /**
   * The instructional tier the engine reported when the game was created (605 / 310 /
   * 220), or null for a session created before tiering existed. Recorded rather than
   * re-derived so the console can state which game is being played before the first
   * round payload exists. The engine remains the authority on what the tier *does*.
   */
  courseMode: string | null;
  /** The bundle's pool fingerprint, pinned at creation so uploads can be checked. */
  candidatePoolHash: string;
  poolCount: number;
  mode: "team" | "individual";
  maxTeamSize: number;
  totalRounds: number;
  practiceEnabled: boolean;
  /** Demo sessions play 1 human fund against deterministic bots, no professor. */
  demo: boolean;
  /** Round timer, in seconds. 0 means no deadline. */
  roundDurationSeconds: number;
  /** Server-owned deadline for the open round, in epoch ms. Null when no timer or closed. */
  roundDeadlineAt: number | null;
  /** When the timer is paused, the deadline is shifted forward by the pause length. */
  timerPausedAt: number | null;
  phase: Phase;
  /** -1 is the practice round; 0..totalRounds-1 are scored. Mirrors the engine. */
  currentRound: number;
  resolvedRounds: number;
  /** Monotonic. Every committed mutation increments it. Clients poll or SSE on it. */
  revision: number;
  engineState: Uint8Array | null;
  engineStateBytes: number;
  /** Set once the engine has been asked to build the game; guards double-start. */
  engineCreatedAt: string | null;
  /** The finalized debrief payload (standings/analytics/debrief), set once. */
  finale: unknown | null;
  finalizedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ForecastSummary {
  propertiesMatched: number;
  meanPredictedUpsideVsAsk: number | null;
  meanPredictedNoiGrowth: number | null;
  meanDownsideProbability: number | null;
  meanMaxBidDiscountToAsk: number | null;
  meanTargetLtv: number | null;
  modelName: string;
  /** Explicit: check-in can describe a forecast, but never score one. */
  scored: false;
  note: string;
}

export interface FundState {
  id: string;
  sessionId: string;
  name: string;
  memberIds: string[];
  modelStatus: ModelStatus;
  modelName: string | null;
  modelLockedAt: string | null;
  modelRowCount: number;
  modelValidatedAt: string | null;
  forecastSummary: ForecastSummary | null;
  createdAt: string;
}

export interface MemberState {
  id: string;
  sessionId: string;
  displayName: string;
  fundId: string | null;
  isProfessor: boolean;
  joinedAt: string;
  lastSeenAt: string;
}

export interface RejectedDecision {
  fundId: string;
  propertyId: string;
  reason: string;
}

/** One round's server-side record. `results` carries the reveal, once it exists. */
export interface RoundRecord {
  sessionId: string;
  round: number;
  openedAt: string;
  closedAt: string | null;
  resolvedAt: string | null;
  /** The engine's `public` payload for this round, verbatim. */
  broadcast: unknown;
  /** The engine's `public_results` payload, verbatim. Null until resolved. */
  results: unknown | null;
  /** The engine's analytics leaderboard at this round's resolution. Null until resolved. */
  analytics: unknown | null;
  rejected: RejectedDecision[];
  /** Stances the engine refused at resolution, reported to the fund that sent them. */
  rejectedStances: RejectedStance[];
}

export interface DecisionItem {
  propertyId: string;
  action: "PASS" | "BID";
  bid: number | null;
  ltv: number | null;
}

/**
 * The management postures the engine defines. These are the engine's own names, not
 * this service's: a second vocabulary here would be a second authority on what a fund
 * chose, and the two would disagree the first time either moved.
 *
 *   RUN LEAN          defer upkeep, keep costs down, carry more operating risk
 *   STANDARD          neutral; the pre-V2 economics
 *   INVEST & PROTECT  pay for protection: less likely to be interrupted, at a cost
 *
 * Which of these a session may use is the engine's published course-tier config, not
 * a constant: 605 accepts none, 310 all three, 220 only STANDARD.
 */
export type ManagementStance = "RUN LEAN" | "STANDARD" | "INVEST & PROTECT";

export interface StanceItem {
  propertyId: string;
  stance: ManagementStance;
}

export interface DecisionState {
  sessionId: string;
  round: number;
  fundId: string;
  submittedBy: string;
  submittedAt: string;
  items: DecisionItem[];
  /**
   * This fund's management stance for each building it owns. Absent (or empty) for a
   * tier that does not simulate an operating year, which is why it is optional on
   * read: a decision stored before the management layer existed still loads.
   */
  stances: StanceItem[];
}

export function stancesOf(decision: DecisionState | null | undefined): StanceItem[] {
  return decision?.stances ?? [];
}

export interface RejectedStance {
  fundId: string;
  propertyId: string;
  reason: string;
}

/** One per fund. Immutable once written; the lock lives on the fund document. */
export interface ModelRecord {
  sessionId: string;
  fundId: string;
  modelName: string;
  rowCount: number;
  validatedAt: string;
  lockedAt: string | null;
  rows: ModelRow[];
}

export interface ModelRow {
  propertyId: string;
  forecast: {
    modelName: string;
    predictedFairValue: number;
    predictedNoiGrowth: number;
    probabilityOfDownside: number | null;
    confidence: number | null;
  };
  policy: {
    maxBid: number;
    targetLtv: number;
  };
}

export interface IdempotencyRecord {
  key: string;
  actorId: string;
  route: string;
  requestHash: string;
  status: number;
  body: unknown;
  createdAt: string;
}

export function isPhase(value: string): value is Phase {
  return (
    value === "lobby" ||
    value === "model_checkin" ||
    value === "practice" ||
    value === "practice_results" ||
    value === "round" ||
    value === "round_results" ||
    value === "finale"
  );
}

export type { ErrorCode };
