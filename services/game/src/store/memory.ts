/**
 * In-memory store: the test and local-development implementation.
 *
 * It is not a lesser version of the Firestore store. It enforces the *same*
 * contract — serialised transactions, revision bumps, join-code uniqueness — so a
 * race that fails here fails for real, and a race that passes here is a statement
 * about the contract rather than about this implementation's good luck.
 *
 * The one thing it adds is determinism: tests can drive two "instances" that share
 * nothing but this store, which is how the process-restart case is exercised
 * without launching a second server.
 */

import type { Aggregate, Store, Transaction, TransactionBody } from "./types.js";
import { conflict, notFound } from "../errors.js";
import { canonicalJoinCode } from "../ids.js";
import type {
  DecisionState,
  FundState,
  IdempotencyRecord,
  MemberState,
  ModelRecord,
  RoundRecord,
  SessionState,
} from "../domain.js";

function clone<T>(value: T): T {
  return structuredClone(value);
}

class MemoryTransaction implements Transaction {
  readonly aggregate: Aggregate;
  private readonly original: Aggregate;
  private dirtyFlag = false;

  constructor(aggregate: Aggregate) {
    this.original = aggregate;
    // Work on a copy so a throw leaves the stored aggregate untouched. Without
    // this, a rejected bid would still appear submitted.
    this.aggregate = clone(aggregate);
  }

  putFund(fund: FundState): void {
    this.aggregate.funds.set(fund.id, fund);
    this.dirtyFlag = true;
  }

  putMember(member: MemberState): void {
    this.aggregate.members.set(member.id, member);
    this.dirtyFlag = true;
  }

  putRound(record: RoundRecord): void {
    this.aggregate.round = record;
    this.dirtyFlag = true;
  }

  putDecision(decision: DecisionState): void {
    this.aggregate.decisions.set(decision.fundId, decision);
    this.dirtyFlag = true;
  }

  deleteDecision(fundId: string): void {
    this.aggregate.decisions.delete(fundId);
    this.dirtyFlag = true;
  }

  touch(): void {
    this.dirtyFlag = true;
  }

  isDirty(): boolean {
    return this.dirtyFlag;
  }

  /** The store's commit step. Never returns the working copy to the caller. */
  commit(): void {
    if (!this.dirtyFlag) return;
    const next = this.aggregate;
    next.session.revision = this.original.session.revision + 1;
    this.original.session = next.session;
    this.original.funds = next.funds;
    this.original.members = next.members;
    this.original.round = next.round;
    this.original.decisions = next.decisions;
  }
}

export class MemoryStore implements Store {
  readonly kind = "memory";

  private readonly sessions = new Map<string, Aggregate>();
  private readonly joinCodes = new Map<string, string>();
  private readonly models = new Map<string, ModelRecord>();
  private readonly idempotency = new Map<string, IdempotencyRecord>();
  private readonly listeners = new Map<string, Set<(revision: number) => void>>();
  private readonly locks = new Map<string, Promise<unknown>>();
  /** Archived round records by `sessionId:round` — exports and audits read these. */
  private readonly roundArchive = new Map<string, RoundRecord>();
  /** Archived decisions by `sessionId:round:fundId`. */
  private readonly decisionArchive = new Map<string, DecisionState>();

  async ensureReady(): Promise<void> {}

  async createSession(session: SessionState, firstFund: FundState | null): Promise<void> {
    const code = canonicalJoinCode(session.joinCode);
    if (this.joinCodes.has(code)) {
      throw conflict(`join code '${code}' is already in use`);
    }
    if (this.sessions.has(session.id)) {
      throw conflict(`session '${session.id}' already exists`);
    }
    this.joinCodes.set(code, session.id);
    this.sessions.set(session.id, {
      session: clone(session),
      funds: new Map(firstFund ? [[firstFund.id, clone(firstFund)]] : []),
      members: new Map(),
      round: null,
      decisions: new Map(),
    });
  }

  async getSession(sessionId: string): Promise<SessionState | null> {
    const aggregate = this.sessions.get(sessionId);
    if (!aggregate) return null;
    // Returned by copy: a caller that mutated this could change game state without
    // a transaction, which is precisely the class of bug this store exists to stop.
    return clone(aggregate.session);
  }

  async findSessionByJoinCode(code: string): Promise<string | null> {
    return this.joinCodes.get(canonicalJoinCode(code)) ?? null;
  }

  async listSessions(): Promise<SessionState[]> {
    return [...this.sessions.values()].map((a) => clone(a.session));
  }

  async transact<T>(sessionId: string, body: TransactionBody<T>): Promise<T> {
    return this.withLock(sessionId, async () => {
      const aggregate = this.sessions.get(sessionId);
      if (!aggregate) throw notFound(`unknown session '${sessionId}'`);
      const tx = new MemoryTransaction(aggregate);
      const result = await body(tx);
      tx.commit();
      if (tx.isDirty()) {
        aggregate.session.updatedAt = new Date().toISOString();
        // Archive every committed round and decision so exports can read history
        // after later rounds have overwritten the aggregate's "current" slots.
        if (aggregate.round) {
          this.roundArchive.set(`${sessionId}:${aggregate.round.round}`, clone(aggregate.round));
        }
        for (const decision of aggregate.decisions.values()) {
          this.decisionArchive.set(
            `${sessionId}:${decision.round}:${decision.fundId}`,
            clone(decision),
          );
        }
        this.notify(sessionId, aggregate.session.revision);
      }
      return result;
    });
  }

  async listRounds(sessionId: string): Promise<RoundRecord[]> {
    const prefix = `${sessionId}:`;
    const out: RoundRecord[] = [];
    for (const [key, record] of this.roundArchive) {
      if (key.startsWith(prefix)) out.push(clone(record));
    }
    return out.sort((a, b) => a.round - b.round);
  }

  async listDecisions(sessionId: string, round: number): Promise<DecisionState[]> {
    const prefix = `${sessionId}:${round}:`;
    const out: DecisionState[] = [];
    for (const [key, record] of this.decisionArchive) {
      if (key.startsWith(prefix)) out.push(clone(record));
    }
    return out.sort((a, b) => (a.fundId < b.fundId ? -1 : 1));
  }

  async recordPresence(sessionId: string, memberId: string, at: string): Promise<void> {
    const aggregate = this.sessions.get(sessionId);
    const member = aggregate?.members.get(memberId);
    if (!member) return;
    member.lastSeenAt = at;
  }

  async getModel(sessionId: string, fundId: string): Promise<ModelRecord | null> {
    return clone(this.models.get(`${sessionId}/${fundId}`) ?? null);
  }

  async listAllModels(sessionId: string): Promise<ModelRecord[]> {
    const prefix = `${sessionId}/`;
    const out: ModelRecord[] = [];
    for (const [key, record] of this.models) {
      if (key.startsWith(prefix)) out.push(clone(record));
    }
    return out.sort((a, b) => (a.fundId < b.fundId ? -1 : 1));
  }

  async putModel(record: ModelRecord): Promise<void> {
    this.models.set(`${record.sessionId}/${record.fundId}`, clone(record));
  }

  async getIdempotency(sessionId: string, key: string): Promise<IdempotencyRecord | null> {
    return clone(this.idempotency.get(`${sessionId}/${key}`) ?? null);
  }

  async putIdempotency(sessionId: string, record: IdempotencyRecord): Promise<void> {
    this.idempotency.set(`${sessionId}/${record.key}`, clone(record));
  }

  subscribe(sessionId: string, listener: (revision: number) => void): () => void {
    let set = this.listeners.get(sessionId);
    if (!set) {
      set = new Set();
      this.listeners.set(sessionId, set);
    }
    set.add(listener);
    return () => {
      set?.delete(listener);
    };
  }

  async releaseJoinCode(code: string): Promise<void> {
    this.joinCodes.delete(canonicalJoinCode(code));
  }

  async close(): Promise<void> {
    this.sessions.clear();
    this.joinCodes.clear();
    this.models.clear();
    this.idempotency.clear();
    this.listeners.clear();
  }

  // ── test affordances ────────────────────────────────────────────────────

  /** Snapshot the raw stored aggregate, bypassing the copy-on-read rule. */
  inspect(sessionId: string): Aggregate | undefined {
    return this.sessions.get(sessionId);
  }

  /** Simulate a fresh process: the same persisted data, no in-flight state. */
  forkForRestart(): MemoryStore {
    const next = new MemoryStore();
    for (const [id, aggregate] of this.sessions) next.sessions.set(id, clone(aggregate));
    for (const [code, id] of this.joinCodes) next.joinCodes.set(code, id);
    for (const [key, record] of this.models) next.models.set(key, clone(record));
    for (const [key, record] of this.idempotency) next.idempotency.set(key, clone(record));
    for (const [key, record] of this.roundArchive) next.roundArchive.set(key, clone(record));
    for (const [key, record] of this.decisionArchive) next.decisionArchive.set(key, clone(record));
    return next;
  }

  private notify(sessionId: string, revision: number): void {
    for (const listener of this.listeners.get(sessionId) ?? []) {
      try {
        listener(revision);
      } catch {
        // A subscriber that throws must not roll back a committed transaction.
      }
    }
  }

  /**
   * Serialise transactions per session.
   *
   * A promise chain rather than a mutex library: it is a dozen lines, it has one
   * ordering rule, and it cannot deadlock because nothing ever waits on two locks.
   */
  private withLock<T>(sessionId: string, fn: () => Promise<T>): Promise<T> {
    const previous = this.locks.get(sessionId) ?? Promise.resolve();
    const run = previous.then(fn, fn);
    // Keep the chain alive even if this transaction rejects, or the next caller
    // would inherit the rejection instead of running.
    this.locks.set(
      sessionId,
      run.then(
        () => undefined,
        () => undefined,
      ),
    );
    return run;
  }
}

