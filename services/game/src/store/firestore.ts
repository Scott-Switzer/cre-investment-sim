/**
 * Firestore store — the production implementation.
 *
 * Reached **server-side only**, through `@google-cloud/firestore`. There is no
 * browser SDK and no security-rules model for game state, because the browser never
 * opens a Firestore connection at all. That is what makes it safe to persist the
 * engine snapshot here: it holds every reserve price and every future outcome, and
 * nothing unprivileged can address this collection.
 *
 * Layout
 *
 *   sessions/{sessionId}                                  SessionState
 *   sessions/{sessionId}/funds/{fundId}                   FundState
 *   sessions/{sessionId}/members/{memberId}               MemberState
 *   sessions/{sessionId}/rounds/{round}                   RoundRecord
 *   sessions/{sessionId}/rounds/{round}/decisions/{fundId} DecisionState
 *   sessions/{sessionId}/models/{fundId}                  ModelRecord (immutable)
 *   sessions/{sessionId}/idempotency/{key}                IdempotencyRecord
 *   join_codes/{code}                                     { sessionId }
 *
 * Three decisions here are load-bearing:
 *
 * **Optimistic concurrency is Firestore's, not ours.** A transaction that reads the
 * session document and writes it back aborts and retries if anyone else committed
 * in between. So the revision is not merely recorded, it is *enforced* — two
 * professors pressing "close round" cannot both commit.
 *
 * **The engine snapshot is gzipped.** Uncompressed it is 307 KB for two funds and
 * grows with every fund's model, which walks straight into Firestore's 1 MiB
 * document ceiling around a class-sized game. Gzipped it is ~19 KB, and the JSON is
 * extremely repetitive so the ratio holds as the game grows.
 *
 * **`subscribe` uses a real listener.** After a commit on instance A, instances B
 * and C have no idea anything happened; a purely in-process notifier would leave
 * their SSE clients waiting. A listener on the one session document fixes that for
 * the cost of one listener per live session. Clients still converge without it,
 * because the event carries only a revision and the next poll is authoritative.
 */

import { Firestore, type DocumentReference, type Transaction as FsTransaction } from "@google-cloud/firestore";
import { gunzipSync, gzipSync } from "node:zlib";

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

const SESSIONS = "sessions";
const JOIN_CODES = "join_codes";

/** Round -1 (practice) is a legal document id, so it is stored as its own name. */
export function roundKey(round: number): string {
  return round < 0 ? "practice" : String(round);
}

/**
 * Firestore rejects `undefined` outright, and the engine's projections are JSON that
 * can carry it. Dropping the key is the correct reading: an absent field and a
 * null one mean the same thing here, and the alternative — writing null — would
 * make "not recorded" indistinguishable from "recorded as nothing".
 */
function sanitize(value: unknown): unknown {
  if (value === undefined) return undefined;
  if (value === null) return null;
  if (value instanceof Uint8Array) return Buffer.from(value);
  if (Array.isArray(value)) return value.map((item) => sanitize(item) ?? null);
  if (typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [key, inner] of Object.entries(value as Record<string, unknown>)) {
      const cleaned = sanitize(inner);
      if (cleaned !== undefined) out[key] = cleaned;
    }
    return out;
  }
  return value;
}

/**
 * The session document, with the engine snapshot compressed on the way in.
 *
 * The compression is not an optimisation. Uncompressed, a two-fund snapshot is 307 KB
 * of JSON and it grows with every fund's model, so a class-sized game runs into
 * Firestore's 1 MiB per-document ceiling — and the failure would appear as a rejected
 * write mid-round rather than as anything legible. Gzipped, the same snapshot is ~19 KB
 * and the ratio holds as the game grows, because the JSON is extremely repetitive.
 *
 * An earlier version of this adapter had the compressor written but never called it,
 * and stored raw bytes while every test still passed. The emulator test that reads the
 * stored byte length is what makes that mistake impossible to repeat.
 */
function toDoc(session: SessionState): Record<string, unknown> {
  const encoded: SessionState = {
    ...session,
    engineState: encodeEngineState(session.engineState) as unknown as Uint8Array | null,
  };
  return sanitize(encoded) as Record<string, unknown>;
}

function fromSessionDoc(data: Record<string, unknown>): SessionState {
  const state = data as unknown as SessionState;
  state.engineState = decodeEngineState(data.engineState);
  return state;
}

function decodeEngineState(raw: unknown): Uint8Array | null {
  if (!raw) return null;
  if (raw instanceof Uint8Array) {
    // Written gzipped; read back as bytes. Falls back to the raw bytes when a
    // document predates compression, rather than throwing mid-class.
    try {
      return new Uint8Array(gunzipSync(raw));
    } catch {
      return new Uint8Array(raw);
    }
  }
  return null;
}

function encodeEngineState(state: Uint8Array | null): Buffer | null {
  return state ? gzipSync(Buffer.from(state), { level: 9 }) : null;
}

class FirestoreTransaction implements Transaction {
  readonly aggregate: Aggregate;
  private readonly sessionRef: DocumentReference;
  private readonly tx: FsTransaction;
  private readonly dirtyFunds = new Map<string, FundState>();
  private readonly dirtyMembers = new Map<string, MemberState>();
  private readonly dirtyDecisions = new Map<string, DecisionState>();
  private readonly removedDecisions = new Set<string>();
  private roundDirty = false;
  private sessionDirty = false;

  constructor(aggregate: Aggregate, sessionRef: DocumentReference, tx: FsTransaction) {
    this.aggregate = aggregate;
    this.sessionRef = sessionRef;
    this.tx = tx;
  }

  putFund(fund: FundState): void {
    this.aggregate.funds.set(fund.id, fund);
    this.dirtyFunds.set(fund.id, fund);
  }

  putMember(member: MemberState): void {
    this.aggregate.members.set(member.id, member);
    this.dirtyMembers.set(member.id, member);
  }

  putRound(record: RoundRecord): void {
    this.aggregate.round = record;
    this.roundDirty = true;
  }

  putDecision(decision: DecisionState): void {
    this.aggregate.decisions.set(decision.fundId, decision);
    this.dirtyDecisions.set(decision.fundId, decision);
    this.removedDecisions.delete(decision.fundId);
  }

  deleteDecision(fundId: string): void {
    this.aggregate.decisions.delete(fundId);
    this.dirtyDecisions.delete(fundId);
    this.removedDecisions.add(fundId);
  }

  touch(): void {
    this.sessionDirty = true;
  }

  isDirty(): boolean {
    return (
      this.sessionDirty ||
      this.roundDirty ||
      this.dirtyFunds.size > 0 ||
      this.dirtyMembers.size > 0 ||
      this.dirtyDecisions.size > 0 ||
      this.removedDecisions.size > 0
    );
  }

  commit(): void {
    if (!this.isDirty()) return;
    this.aggregate.session.revision += 1;
    this.aggregate.session.updatedAt = new Date().toISOString();
    const rounds = this.sessionRef.collection("rounds");
    const roundId = roundKey(this.aggregate.session.currentRound);

    if (this.roundDirty && this.aggregate.round) {
      this.tx.set(rounds.doc(roundId), sanitize(this.aggregate.round) as object);
    }
    for (const fund of this.dirtyFunds.values()) {
      this.tx.set(this.sessionRef.collection("funds").doc(fund.id), sanitize(fund) as object);
    }
    for (const member of this.dirtyMembers.values()) {
      this.tx.set(this.sessionRef.collection("members").doc(member.id), sanitize(member) as object);
    }
    for (const decision of this.dirtyDecisions.values()) {
      this.tx.set(
        rounds.doc(roundKey(decision.round)).collection("decisions").doc(decision.fundId),
        sanitize(decision) as object,
      );
    }
    for (const fundId of this.removedDecisions) {
      this.tx.delete(rounds.doc(roundId).collection("decisions").doc(fundId));
    }
    this.tx.set(this.sessionRef, toDoc(this.aggregate.session));
  }
}

export interface FirestoreStoreOptions {
  projectId?: string;
  databaseId?: string;
  /** Injected for tests; otherwise a default client is constructed. */
  firestore?: Firestore;
}

export class FirestoreStore implements Store {
  readonly kind = "firestore";
  private readonly db: Firestore;
  private readonly listeners = new Map<string, () => void>();

  constructor(options: FirestoreStoreOptions = {}) {
    this.db =
      options.firestore ??
      new Firestore({
        ...(options.projectId ? { projectId: options.projectId } : {}),
        ...(options.databaseId ? { databaseId: options.databaseId } : {}),
        ignoreUndefinedProperties: true,
      });
  }

  async ensureReady(): Promise<void> {
    // One cheap round trip so a misconfigured project fails at boot rather than on
    // a student's first join.
    await this.db.collection(SESSIONS).limit(1).get();
  }

  async createSession(session: SessionState, firstFund: FundState | null): Promise<void> {
    const code = canonicalJoinCode(session.joinCode);
    const sessionRef = this.db.collection(SESSIONS).doc(session.id);
    const codeRef = this.db.collection(JOIN_CODES).doc(code);
    await this.db.runTransaction(async (tx) => {
      // Reading both documents inside the transaction is what makes the join code
      // genuinely unique: two professors creating a class at the same instant cannot
      // both claim it, because the second transaction aborts on the read set.
      const [existingSession, existingCode] = await Promise.all([
        tx.get(sessionRef),
        tx.get(codeRef),
      ]);
      if (existingSession.exists) throw conflict(`session '${session.id}' already exists`);
      if (existingCode.exists) throw conflict(`join code '${code}' is already in use`);
      tx.set(codeRef, { sessionId: session.id, createdAt: session.createdAt });
      tx.set(sessionRef, toDoc(session));
      if (firstFund) {
        tx.set(sessionRef.collection("funds").doc(firstFund.id), sanitize(firstFund) as object);
      }
    });
  }

  async getSession(sessionId: string): Promise<SessionState | null> {
    const snap = await this.db.collection(SESSIONS).doc(sessionId).get();
    if (!snap.exists) return null;
    return fromSessionDoc(snap.data() as Record<string, unknown>);
  }

  async findSessionByJoinCode(code: string): Promise<string | null> {
    const snap = await this.db.collection(JOIN_CODES).doc(canonicalJoinCode(code)).get();
    if (!snap.exists) return null;
    return (snap.data() as { sessionId: string }).sessionId;
  }

  async listSessions(): Promise<SessionState[]> {
    const snap = await this.db.collection(SESSIONS).orderBy("createdAt", "desc").limit(50).get();
    return snap.docs.map((doc) => fromSessionDoc(doc.data() as Record<string, unknown>));
  }

  async transact<T>(sessionId: string, body: TransactionBody<T>): Promise<T> {
    const sessionRef = this.db.collection(SESSIONS).doc(sessionId);
    const committed = await this.db.runTransaction(async (tx): Promise<{ result: T; revision: number }> => {
      // ── every read happens here, before any write ──────────────────────
      // Firestore requires it, and doing it in one place means `body` cannot
      // accidentally break the rule: it has no store access other than the
      // aggregate it is handed.
      const sessionSnap = await tx.get(sessionRef);
      if (!sessionSnap.exists) throw notFound(`unknown session '${sessionId}'`);
      const session = fromSessionDoc(sessionSnap.data() as Record<string, unknown>);

      const [fundsSnap, membersSnap] = await Promise.all([
        tx.get(sessionRef.collection("funds")),
        tx.get(sessionRef.collection("members")),
      ]);

      const aggregate: Aggregate = {
        session,
        funds: new Map(fundsSnap.docs.map((d) => [d.id, d.data() as FundState])),
        members: new Map(membersSnap.docs.map((d) => [d.id, d.data() as MemberState])),
        round: null,
        decisions: new Map(),
      };

      const roundId = roundKey(session.currentRound);
      const roundSnap = await tx.get(sessionRef.collection("rounds").doc(roundId));
      if (roundSnap.exists) {
        aggregate.round = roundSnap.data() as RoundRecord;
        const decisionsSnap = await tx.get(
          sessionRef.collection("rounds").doc(roundId).collection("decisions"),
        );
        aggregate.decisions = new Map(
          decisionsSnap.docs.map((d) => [d.id, d.data() as DecisionState]),
        );
      }

      const working = new FirestoreTransaction(aggregate, sessionRef, tx);
      const result = await body(working);
      working.commit();
      return { result, revision: working.aggregate.session.revision };
    });

    // Nothing to publish here: in production the Firestore listener installed by
    // `subscribe` fires on the committed write, on every instance, including the
    // ones that did not serve this request. Publishing locally as well would
    // double-notify; publishing *instead* would strand every other instance's
    // SSE clients, which is the failure the listener exists to prevent.
    void committed;
    return committed.result;
  }

  async recordPresence(sessionId: string, memberId: string, at: string): Promise<void> {
    await this.db
      .collection(SESSIONS)
      .doc(sessionId)
      .collection("members")
      .doc(memberId)
      .set({ lastSeenAt: at }, { merge: true });
  }

  async getModel(sessionId: string, fundId: string): Promise<ModelRecord | null> {
    const snap = await this.db
      .collection(SESSIONS)
      .doc(sessionId)
      .collection("models")
      .doc(fundId)
      .get();
    return snap.exists ? (snap.data() as ModelRecord) : null;
  }

  async listAllModels(sessionId: string): Promise<ModelRecord[]> {
    const snap = await this.db
      .collection(SESSIONS)
      .doc(sessionId)
      .collection("models")
      .get();
    return snap.docs
      .map((doc) => doc.data() as ModelRecord)
      .sort((a, b) => (a.fundId < b.fundId ? -1 : 1));
  }

  async putModel(record: ModelRecord): Promise<void> {
    await this.db
      .collection(SESSIONS)
      .doc(record.sessionId)
      .collection("models")
      .doc(record.fundId)
      .set(sanitize(record) as object);
  }

  async getIdempotency(sessionId: string, key: string): Promise<IdempotencyRecord | null> {
    const snap = await this.db
      .collection(SESSIONS)
      .doc(sessionId)
      .collection("idempotency")
      .doc(key)
      .get();
    return snap.exists ? (snap.data() as IdempotencyRecord) : null;
  }

  async putIdempotency(sessionId: string, record: IdempotencyRecord): Promise<void> {
    await this.db
      .collection(SESSIONS)
      .doc(sessionId)
      .collection("idempotency")
      .doc(record.key)
      .set(sanitize(record) as object);
  }

  subscribe(sessionId: string, listener: (revision: number) => void): () => void {
    const ref = this.db.collection(SESSIONS).doc(sessionId);
    const key = `${sessionId}:${Math.random().toString(36).slice(2)}`;
    const unsubscribe = ref.onSnapshot(
      (snap) => {
        const revision = (snap.data() as { revision?: number } | undefined)?.revision;
        if (typeof revision === "number") listener(revision);
      },
      () => {
        // A broken listener must not take the SSE route down with it: clients
        // still poll, and polling is authoritative.
        this.listeners.delete(key);
      },
    );
    this.listeners.set(key, () => {
      unsubscribe();
      this.listeners.delete(key);
    });
    return () => {
      unsubscribe();
      this.listeners.delete(key);
    };
  }

  async releaseJoinCode(code: string): Promise<void> {
    await this.db.collection(JOIN_CODES).doc(canonicalJoinCode(code)).delete();
  }

  async close(): Promise<void> {
    for (const unsubscribe of this.listeners.values()) unsubscribe();
    this.listeners.clear();
    await this.db.terminate();
  }
}
