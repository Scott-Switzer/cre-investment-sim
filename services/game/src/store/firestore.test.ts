/**
 * The Firestore adapter, against the real Firestore emulator.
 *
 * The in-memory store proves the *contract*; this proves the *implementation*. They
 * are not the same claim, and the differences are exactly where production bugs live:
 *
 *   - **Optimistic concurrency is Firestore's, not ours.** A transaction that reads the
 *     session document and writes it back aborts and retries if anyone else committed.
 *     That is what makes a double-clicked "close round" safe against a real database,
 *     and it cannot be tested against a hand-written store.
 *   - **The engine snapshot is gzipped, and Firestore has a 1 MiB document ceiling.**
 *     An uncompressed 307 KB snapshot with a class's worth of models walks into it. The
 *     round-trip test is what proves the encoding survives the database, byte for byte.
 *   - **`subscribe` is a real listener**, so it fires on other instances' writes.
 *
 * Skipped unless `FIRESTORE_EMULATOR_HOST` is set, so a plain `vitest run` stays fast
 * and offline. Run it with:
 *
 *     npm run test:emulator
 */

import { Firestore } from "@google-cloud/firestore";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { FirestoreStore, roundKey } from "./firestore.js";
import type { FundState, SessionState } from "../domain.js";

const EMULATOR = process.env.FIRESTORE_EMULATOR_HOST;
const describeEmulator = EMULATOR ? describe : describe.skip;

let db: Firestore;

/** Join codes are global, so a fixture must not reuse one. */
let codeCounter = 0;
function uniqueJoinCode(): string {
  codeCounter += 1;
  const alphabet = "ABCDEFGHJKMNPQRTUVWXYZ2346789";
  let n = codeCounter * 7919 + Math.floor(Date.now() / 1000);
  let out = "";
  for (let i = 0; i < 6; i += 1) {
    out += alphabet[n % alphabet.length];
    n = Math.floor(n / alphabet.length);
  }
  return out;
}

function sessionDoc(id: string, overrides: Partial<SessionState> = {}): SessionState {
  const now = new Date().toISOString();
  return {
    id,
    name: "Emulator Test",
    joinCode: uniqueJoinCode(),
    bundleId: "test-bundle-v1",
    bundleDisplayName: "Test Dataset",
    candidatePoolHash: "hash",
    poolCount: 4,
    mode: "team",
    maxTeamSize: 4,
    totalRounds: 4,
    practiceEnabled: true,
    phase: "lobby",
    currentRound: -1,
    resolvedRounds: 0,
    revision: 0,
    engineState: null,
    engineStateBytes: 0,
    engineCreatedAt: null,
    createdAt: now,
    updatedAt: now,
    ...overrides,
  };
}

function fundDoc(sessionId: string, id: string, overrides: Partial<FundState> = {}): FundState {
  return {
    id,
    sessionId,
    name: "Value Fund",
    memberIds: [],
    modelStatus: "none",
    modelName: null,
    modelLockedAt: null,
    modelRowCount: 0,
    modelValidatedAt: null,
    forecastSummary: null,
    createdAt: new Date().toISOString(),
    ...overrides,
  };
}

describeEmulator("FirestoreStore", () => {
  let store: FirestoreStore;
  let counter = 0;
  const nextId = () => `sess_emulator_${Date.now()}_${counter++}`;

  beforeAll(async () => {
    db = new Firestore({ projectId: process.env.GOOGLE_CLOUD_PROJECT ?? "demo-cre" });
    store = new FirestoreStore({ firestore: db });
    await store.ensureReady();
  });

  afterAll(async () => {
    await store?.close();
  });

  it("creates a session and reads it back unchanged", async () => {
    const id = nextId();
    await store.createSession(sessionDoc(id), fundDoc(id, "fund_1"));
    const session = await store.getSession(id);
    expect(session).not.toBeNull();
    expect(session!.id).toBe(id);
    expect(session!.phase).toBe("lobby");
    expect(session!.revision).toBe(0);
    const aggregateFunds = await store.transact(id, (tx) => [...tx.aggregate.funds.keys()]);
    expect(aggregateFunds).toEqual(["fund_1"]);
  });

  it("refuses a duplicate join code, which is what keeps codes unique across a class", async () => {
    const first = nextId();
    const second = nextId();
    const shared = uniqueJoinCode();
    await store.createSession(sessionDoc(first, { joinCode: shared }), null);
    await expect(
      store.createSession(sessionDoc(second, { joinCode: shared }), null),
    ).rejects.toThrow(/join code/);
  });

  it("supports a session with no funds, because a professor may open an empty class", async () => {
    const id = nextId();
    await store.createSession(sessionDoc(id), null);
    const funds = await store.transact(id, (tx) => [...tx.aggregate.funds.keys()]);
    expect(funds).toEqual([]);
  });

  it("finds a session by a code a student typed with the look-alikes", async () => {
    const id = nextId();
    const code = uniqueJoinCode();
    await store.createSession(sessionDoc(id, { joinCode: code }), null);
    expect(await store.findSessionByJoinCode(code)).toBe(id);
    // Folded the way a student typing from a whiteboard would produce it.
    expect(await store.findSessionByJoinCode(code.toLowerCase())).toBe(id);
  });

  it("bumps the revision on a committed mutation and not on a read", async () => {
    const id = nextId();
    await store.createSession(sessionDoc(id), fundDoc(id, "fund_1"));

    await store.transact(id, (tx) => [...tx.aggregate.funds.keys()]);
    expect((await store.getSession(id))!.revision).toBe(0);

    await store.transact(id, (tx) => {
      const fund = tx.aggregate.funds.get("fund_1")!;
      fund.memberIds = ["mem_1"];
      tx.putFund(fund);
    });
    expect((await store.getSession(id))!.revision).toBe(1);

    await store.transact(id, (tx) => {
      tx.aggregate.session.phase = "model_checkin";
      tx.touch();
    });
    expect((await store.getSession(id))!.revision).toBe(2);
  });

  it("round-trips the engine snapshot byte for byte through the compression", async () => {
    // 300 KB of repetitive JSON: the shape that hits Firestore's 1 MiB document limit
    // uncompressed, and the reason the adapter gzips.
    const id = nextId();
    const big = Buffer.from(
      JSON.stringify({
        pool: Array.from({ length: 120 }, (_, i) => ({
          property_id: `OC-INDU-${String(i).padStart(2, "0")}`,
          reserve_price: 1_000_000 + i * 7919,
          noise: "x".repeat(2000),
        })),
      }),
    );
    expect(big.byteLength).toBeGreaterThan(180_000);

    await store.createSession(sessionDoc(id), null);
    await store.transact(id, (tx) => {
      tx.aggregate.session.engineState = new Uint8Array(big);
      tx.aggregate.session.engineStateBytes = big.byteLength;
      tx.touch();
    });

    // Byte-for-byte identical on the way back out.
    const read = await store.getSession(id);
    expect(read!.engineStateBytes).toBe(big.byteLength);
    expect(Buffer.from(read!.engineState!).equals(big)).toBe(true);

    // And what actually sits in the database is far smaller than what the engine
    // produced, which is the difference between fitting under Firestore's 1 MiB
    // document ceiling and walking straight into it on a class-sized game.
    const stored = await db.collection("sessions").doc(id).get();
    const storedBytes = Buffer.from(stored.data()!.engineState as Buffer).byteLength;
    expect(storedBytes).toBeLessThan(big.byteLength * 0.1);
    // The document as a whole stays well inside the ceiling.
    expect(JSON.stringify(stored.data()).length).toBeLessThan(1_048_576);
  });

  it("gives exactly one winner when two transactions contend on the same document", async () => {
    // The property the whole phase rests on, and the one a hand-written store cannot
    // demonstrate: Firestore aborts the loser on its read set.
    const id = nextId();
    await store.createSession(sessionDoc(id), null);

    const attempt = (label: string) =>
      store.transact(id, (tx) => {
        const session = tx.aggregate.session;
        if (session.phase !== "lobby") {
          throw new Error(`${label}: already moved to ${session.phase}`);
        }
        session.phase = "model_checkin";
        tx.touch();
        return label;
      });

    const results = await Promise.allSettled([attempt("a"), attempt("b")]);
    const winners = results.filter((r) => r.status === "fulfilled");
    const losers = results.filter((r) => r.status === "rejected");
    expect(winners).toHaveLength(1);
    expect(losers).toHaveLength(1);

    const after = await store.getSession(id);
    expect(after!.phase).toBe("model_checkin");
    // One transition, so one revision — not two.
    expect(after!.revision).toBe(1);
  });

  it("stores a fund, a member, a round and a decision in the documented shape", async () => {
    const id = nextId();
    await store.createSession(sessionDoc(id, { currentRound: 0 }), fundDoc(id, "fund_1"));

    await store.transact(id, (tx) => {
      tx.putMember({
        id: "mem_1",
        sessionId: id,
        displayName: "Dana",
        fundId: "fund_1",
        isProfessor: false,
        joinedAt: "2026-01-01T00:00:00.000Z",
        lastSeenAt: "2026-01-01T00:00:00.000Z",
      });
      tx.putRound({
        sessionId: id,
        round: 0,
        openedAt: "2026-01-01T00:00:00.000Z",
        closedAt: null,
        resolvedAt: null,
        broadcast: { round_number: 0, deals: [{ property_id: "P1" }] },
        results: null,
        rejected: [],
        rejectedStances: [],
      });
      tx.putDecision({
        sessionId: id,
        round: 0,
        fundId: "fund_1",
        submittedBy: "mem_1",
        submittedAt: "2026-01-01T00:00:00.000Z",
        items: [{ propertyId: "P1", action: "BID", bid: 12, ltv: 0.5 }],
      });
    });

    const raw = await db
      .collection("sessions")
      .doc(id)
      .collection("rounds")
      .doc(roundKey(0))
      .get();
    expect(raw.exists).toBe(true);
    expect(raw.data()!.broadcast.round_number).toBe(0);

    const decision = await db
      .collection("sessions")
      .doc(id)
      .collection("rounds")
      .doc(roundKey(0))
      .collection("decisions")
      .doc("fund_1")
      .get();
    expect(decision.exists).toBe(true);
    expect(decision.data()!.items[0].bid).toBe(12);

    // And the aggregate reads all of it back.
    const restored = await store.transact(id, (tx) => ({
      funds: [...tx.aggregate.funds.keys()],
      members: [...tx.aggregate.members.keys()],
      round: tx.aggregate.round?.round ?? null,
      decisions: [...tx.aggregate.decisions.keys()],
    }));
    expect(restored).toEqual({
      funds: ["fund_1"],
      members: ["mem_1"],
      round: 0,
      decisions: ["fund_1"],
    });
  });

  it("keeps the practice round in its own document, not at round -1", async () => {
    const id = nextId();
    await store.createSession(sessionDoc(id, { currentRound: -1 }), null);
    await store.transact(id, (tx) => {
      tx.putRound({
        sessionId: id,
        round: -1,
        openedAt: "2026-01-01T00:00:00.000Z",
        closedAt: null,
        resolvedAt: null,
        broadcast: { round_number: -1, deals: [] },
        results: null,
        rejected: [],
        rejectedStances: [],
      });
    });
    expect(roundKey(-1)).toBe("practice");
    const raw = await db
      .collection("sessions")
      .doc(id)
      .collection("rounds")
      .doc("practice")
      .get();
    expect(raw.exists).toBe(true);
    expect((await store.transact(id, (tx) => tx.aggregate.round?.round))).toBe(-1);
  });

  it("stores and lists models, which are read outside the aggregate", async () => {
    const id = nextId();
    await store.createSession(sessionDoc(id), fundDoc(id, "fund_1"));
    await store.putModel({
      sessionId: id,
      fundId: "fund_1",
      modelName: "gbm_v1",
      rowCount: 2,
      validatedAt: "2026-01-01T00:00:00.000Z",
      lockedAt: null,
      rows: [
        {
          propertyId: "P1",
          forecast: {
            modelName: "gbm_v1",
            predictedFairValue: 10,
            predictedNoiGrowth: 0.02,
            probabilityOfDownside: 0.2,
            confidence: 0.8,
          },
          policy: { maxBid: 9, targetLtv: 0.5 },
        },
      ],
    });
    const one = await store.getModel(id, "fund_1");
    expect(one!.modelName).toBe("gbm_v1");
    expect(one!.rows[0]!.policy.maxBid).toBe(9);
    expect(await store.listAllModels(id)).toHaveLength(1);
    expect(await store.getModel(id, "fund_missing")).toBeNull();
  });

  it("keeps idempotency records scoped to a session", async () => {
    const one = nextId();
    const two = nextId();
    await store.createSession(sessionDoc(one), null);
    await store.createSession(sessionDoc(two), null);
    await store.putIdempotency(one, {
      key: "mem_1:route:abc",
      actorId: "mem_1",
      route: "route",
      requestHash: "hash",
      status: 200,
      body: { ok: true },
      createdAt: "2026-01-01T00:00:00.000Z",
    });
    expect((await store.getIdempotency(one, "mem_1:route:abc"))!.body).toEqual({ ok: true });
    expect(await store.getIdempotency(two, "mem_1:route:abc")).toBeNull();
  });

  it("stores an idempotency key whose route contains a slash", async () => {
    // Regression, found against the deployed stack: the service scopes a key as
    // `${actorId}:${route}:${key}`, and real routes are slash-separated
    // ("rounds/decision", "model/manual", "game/finalize"). The test above passed
    // only because its route was the literal word "route". Firestore reads that
    // slash as a path separator and rejects the resulting odd-segment path, so
    // every keyed request returned a 500 in production while the in-memory store —
    // a plain Map, which has no paths — kept returning one.
    const id = nextId();
    await store.createSession(sessionDoc(id), null);
    const key = "mem_1:rounds/decision:double-click";
    await store.putIdempotency(id, {
      key,
      actorId: "mem_1",
      route: "rounds/decision",
      requestHash: "hash",
      status: 200,
      body: { decision: { submittedAt: "2026-01-01T00:00:00.000Z" } },
      createdAt: "2026-01-01T00:00:00.000Z",
    });
    const read = await store.getIdempotency(id, key);
    expect(read, "a slash-scoped key must round-trip").not.toBeNull();
    expect(read!.key).toBe(key);
    expect(read!.body).toEqual({ decision: { submittedAt: "2026-01-01T00:00:00.000Z" } });
    // A different key that encodes the same way must not collide with it.
    expect(await store.getIdempotency(id, "mem_1:rounds decision:double-click")).toBeNull();
  });

  it("updates presence without moving the revision", async () => {
    // Presence changes on every page load. If it moved the revision, every poll from
    // every browser would tell all the others to refetch.
    const id = nextId();
    await store.createSession(sessionDoc(id), null);
    await store.transact(id, (tx) => {
      tx.putMember({
        id: "mem_1",
        sessionId: id,
        displayName: "Dana",
        fundId: null,
        isProfessor: false,
        joinedAt: "2026-01-01T00:00:00.000Z",
        lastSeenAt: "2026-01-01T00:00:00.000Z",
      });
    });
    const before = (await store.getSession(id))!.revision;
    await store.recordPresence(id, "mem_1", "2026-01-02T00:00:00.000Z");
    expect((await store.getSession(id))!.revision).toBe(before);

    const member = await db
      .collection("sessions")
      .doc(id)
      .collection("members")
      .doc("mem_1")
      .get();
    expect(member.data()!.lastSeenAt).toBe("2026-01-02T00:00:00.000Z");
  });

  it("behaves like a second process when a second store instance reads the same data", async () => {
    // The Cloud Run case: instance A commits, instance B serves the next request.
    const id = nextId();
    await store.createSession(sessionDoc(id), fundDoc(id, "fund_1"));
    const other = new FirestoreStore({
      firestore: new Firestore({ projectId: process.env.GOOGLE_CLOUD_PROJECT ?? "demo-cre" }),
    });
    try {
      const session = await other.getSession(id);
      expect(session!.id).toBe(id);
      await other.transact(id, (tx) => {
        const fund = tx.aggregate.funds.get("fund_1")!;
        fund.modelStatus = "locked";
        fund.modelLockedAt = "2026-01-01T00:00:00.000Z";
        tx.putFund(fund);
      });
      // The first instance sees the second's commit.
      const seen = await store.transact(id, (tx) => tx.aggregate.funds.get("fund_1")!.modelStatus);
      expect(seen).toBe("locked");
      expect((await store.getSession(id))!.revision).toBe(1);
    } finally {
      await other.close();
    }
  });

  it("fires a subscription for a write committed by another instance", async () => {
    const id = nextId();
    await store.createSession(sessionDoc(id), null);
    const other = new FirestoreStore({
      firestore: new Firestore({ projectId: process.env.GOOGLE_CLOUD_PROJECT ?? "demo-cre" }),
    });
    try {
      const seen: number[] = [];
      const unsubscribe = store.subscribe(id, (revision) => seen.push(revision));
      try {
        await other.transact(id, (tx) => {
          tx.aggregate.session.phase = "model_checkin";
          tx.touch();
        });
        const deadline = Date.now() + 8000;
        while (seen.length === 0 && Date.now() < deadline) {
          await new Promise((r) => setTimeout(r, 100));
        }
        expect(seen.length).toBeGreaterThan(0);
        expect(seen.at(-1)).toBe(1);
      } finally {
        unsubscribe();
      }
    } finally {
      await other.close();
    }
  });

  it("lists sessions most recent first, for a professor's landing page", async () => {
    const id = nextId();
    await store.createSession(
      sessionDoc(id, { createdAt: new Date(Date.now() + 60_000).toISOString() }),
      null,
    );
    const sessions = await store.listSessions();
    expect(sessions.length).toBeGreaterThan(0);
    const times = sessions.map((s) => s.createdAt);
    expect(times).toEqual([...times].sort().reverse());
  });
});
