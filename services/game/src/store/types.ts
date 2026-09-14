/**
 * The persistence port.
 *
 * The design goal is narrow and worth stating plainly: **no process may ever hold
 * game state that another process cannot see.** Cloud Run recycles instances, runs
 * several at once, and scales to zero, so anything kept in a module-level variable
 * is a classroom bug waiting for a cold start.
 *
 * Everything mutable therefore goes through `transact`, which read-modify-writes
 * one session aggregate against a revision. Two consequences fall out of that and
 * neither is an accident:
 *
 * - A stale writer loses. `If-Match` on a professor's "close round" is checked
 *   against the revision the caller actually saw, so a double-click cannot resolve
 *   a round twice.
 * - An operation is re-runnable. Every operation's effect is a function of the
 *   aggregate it read, so a retry after a crash reproduces it rather than
 *   compounding it.
 *
 * `subscribe` is deliberately *not* part of the durability story. It is an
 * in-process notifier that carries a revision number and nothing else; a client
 * that misses every event still converges, because its next poll reads the
 * authoritative document. That is what makes process death harmless.
 */

import type {
  DecisionState,
  FundState,
  IdempotencyRecord,
  MemberState,
  ModelRecord,
  RoundRecord,
  SessionState,
} from "../domain.js";

/** One session's working set, loaded for the duration of a transaction. */
export interface Aggregate {
  session: SessionState;
  funds: Map<string, FundState>;
  members: Map<string, MemberState>;
  /** The active round's record, or null before any round has opened. */
  round: RoundRecord | null;
  /** The active round's submissions, keyed by fund id. Empty when no round is open. */
  decisions: Map<string, DecisionState>;
}

export interface Transaction {
  readonly aggregate: Aggregate;

  putFund(fund: FundState): void;
  putMember(member: MemberState): void;
  putRound(record: RoundRecord): void;
  putDecision(decision: DecisionState): void;

  /** Delete a submission (only used by tests that probe the frozen-decision guard). */
  deleteDecision(fundId: string): void;

  /**
   * Mark the session document itself as changed. Bumps the revision, which is what
   * clients observe. Ordinary presence updates deliberately do *not* call this.
   */
  touch(): void;

  isDirty(): boolean;
}

export type TransactionBody<T> = (tx: Transaction) => T | Promise<T>;

export interface Store {
  readonly kind: string;
  ensureReady(): Promise<void>;

  /**
   * Insert a session and (usually) one fund atomically, claiming the join code.
   * Fails if the code is already claimed.
   *
   * `firstFund` is nullable because a professor may legitimately open a class with no
   * funds and let each team create its own. Forcing a placeholder "Fund 1" would make
   * that professor's roster wrong from the first second.
   */
  createSession(session: SessionState, firstFund: FundState | null): Promise<void>;

  getSession(sessionId: string): Promise<SessionState | null>;
  findSessionByJoinCode(code: string): Promise<string | null>;
  listSessions(): Promise<SessionState[]>;

  /** Read-modify-write one aggregate. The only path to mutation. */
  transact<T>(sessionId: string, body: TransactionBody<T>): Promise<T>;

  /**
   * Update a member's `lastSeenAt` without bumping the session revision.
   *
   * Kept out of `transact` on purpose: presence changes on every page load, and if
   * it moved the revision then every poll from every browser would tell all the
   * others to refetch. Presence is not a game event.
   */
  recordPresence(sessionId: string, memberId: string, at: string): Promise<void>;

  // Models are immutable once locked, so they are read outside the aggregate
  // rather than dragged through every transaction. A class's models are ~18 KB each,
  // which is why they are also never part of the revision short-circuit path.
  getModel(sessionId: string, fundId: string): Promise<ModelRecord | null>;
  listAllModels(sessionId: string): Promise<ModelRecord[]>;
  putModel(record: ModelRecord): Promise<void>;

  getIdempotency(sessionId: string, key: string): Promise<IdempotencyRecord | null>;
  putIdempotency(sessionId: string, record: IdempotencyRecord): Promise<void>;

  /** Notify subscribers that a session's revision moved. Best-effort by design. */
  subscribe(sessionId: string, listener: (revision: number) => void): () => void;

  /** Test-only: drop the join-code claim so a code can be re-used. */
  releaseJoinCode(code: string): Promise<void>;

  close(): Promise<void>;
}

/** Pages of output for the professor's session list. */
export function sortSessions(sessions: SessionState[]): SessionState[] {
  return [...sessions].sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));
}
