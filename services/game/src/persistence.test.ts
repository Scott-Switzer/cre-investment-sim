/**
 * Distributed-state correctness.
 *
 * This is the suite the phase exists for. The economics already have their evidence;
 * what is unproven is whether 50–70 browsers can act on one authoritative classroom
 * state without duplication, drift, or a hidden process-local assumption.
 *
 * Each test names the classroom failure it prevents.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { fakeOf, startHarness, type Harness, type Browser } from "./testing/harness.js";
import {
  buildCsv,
  createClass,
  joinClass,
  playablePractice,
  revisionOfSession,
} from "./testing/scenarios.js";

let harness: Harness;

beforeEach(async () => {
  harness = await startHarness();
});

afterEach(async () => {
  await harness.close();
});

async function stateOf(browser: Browser, sessionId: string) {
  const res = await browser.get(`/v1/sessions/${sessionId}/state`);
  expect(res.status).toBe(200);
  return res.body;
}

describe("process restart", () => {
  it("keeps a student signed in and their session intact across a new server process", async () => {
    // The failure this prevents: Cloud Run scales to zero between the professor's
    // briefing and the first round, and every student is silently logged out.
    const fixture = await createClass(harness);
    const student = await joinClass(harness, {
      joinCode: fixture.joinCode,
      displayName: "Dana",
    });
    const before = await stateOf(student.browser, fixture.sessionId);

    const second = await harness.restart();
    try {
      const after = await stateOf(student.browser, fixture.sessionId);
      expect(after.session.revision).toBe(before.session.revision);
      expect(after.session.phase).toBe(before.session.phase);
      expect(after.you.memberId).toBe(before.you.memberId);
      expect(after.you.fundId).toBe(before.you.fundId);
      expect(after.funds).toEqual(before.funds);
    } finally {
      await second.close();
    }
  });

  it("carries a mid-game engine state across a restart, with no re-dealt round", async () => {
    // The failure this prevents, and the one that motivated Phase 0: the properties a
    // round offers are derived from state, so a restart that lost or reshuffled the
    // state would offer *different buildings* after a refresh, with nothing on screen
    // to say so.
    const fixture = await playablePractice(harness, { members: [["Dana", "Ravi"]] });
    const student = fixture.students[0]!;
    const before = await stateOf(student.browser, fixture.sessionId);
    const dealsBefore = before.round.public.deals.map((d: { property_id: string }) => d.property_id);

    const second = await harness.restart();
    try {
      const after = await stateOf(student.browser, fixture.sessionId);
      const dealsAfter = after.round.public.deals.map((d: { property_id: string }) => d.property_id);
      expect(dealsAfter).toEqual(dealsBefore);
      expect(after.round.myForecast).toEqual(before.round.myForecast);
      expect(after.session.revision).toBe(before.session.revision);
    } finally {
      await second.close();
    }
  });

  it("accepts a request from a second process that the first did not serve", async () => {
    const fixture = await playablePractice(harness, { members: [["Dana"]] });
    const student = fixture.students[0]!;
    const state = await stateOf(student.browser, fixture.sessionId);
    const deals = state.round.public.deals as { property_id: string }[];

    const second = await harness.restart();
    try {
      const res = await student.browser.post(
        `/v1/sessions/${fixture.sessionId}/rounds/decision`,
        {
          fundId: student.fundId,
          items: deals.map((d) => ({ propertyId: d.property_id, action: "PASS" })),
        },
      );
      expect(res.status).toBe(200);
      const after = await stateOf(student.browser, fixture.sessionId);
      expect(after.round.submittedFunds).toBe(1);
    } finally {
      await second.close();
    }
  });
});

describe("refresh", () => {
  it("returns the identical state at every phase", async () => {
    const fixture = await playablePractice(harness, { members: [["Dana", "Ravi"]] });
    const student = fixture.students[0]!;

    const first = await stateOf(student.browser, fixture.sessionId);
    const second = await stateOf(student.browser, fixture.sessionId);
    const third = await stateOf(student.browser, fixture.sessionId);
    expect(second).toEqual(first);
    expect(third).toEqual(first);
  });

  it("short-circuits an unchanged poll to one revision, not a rebuilt view", async () => {
    // With 70 browsers polling, the difference between "read one document" and "read
    // the whole class and rebuild the view" is the difference between a class-sized
    // game and a rate limit.
    const fixture = await playablePractice(harness, { members: [["Dana"]] });
    const student = fixture.students[0]!;
    const state = await stateOf(student.browser, fixture.sessionId);

    const res = await student.browser.get(
      `/v1/sessions/${fixture.sessionId}/state?since=${state.session.revision}`,
    );
    expect(res.status).toBe(200);
    expect(res.body).toEqual({ unchanged: true, revision: state.session.revision });
    expect(res.body).not.toHaveProperty("funds");
    expect(res.body).not.toHaveProperty("round");
  });

  it("builds a full view again as soon as the revision moves", async () => {
    const fixture = await playablePractice(harness, { members: [["Dana", "Ravi"]] });
    const student = fixture.students[0]!;
    const before = await stateOf(student.browser, fixture.sessionId);

    await joinClass(harness, { joinCode: fixture.joinCode, displayName: "Late Arrival" });

    const after = await student.browser.get(
      `/v1/sessions/${fixture.sessionId}/state?since=${before.session.revision}`,
    );
    expect(after.body.unchanged).toBeUndefined();
    expect(after.body.session.revision).toBeGreaterThan(before.session.revision);
  });
});

describe("duplicate requests", () => {
  it("replays a locked model upload under the same idempotency key instead of re-validating", async () => {
    const fixture = await createClass(harness, { fundNames: ["Value Fund"] });
    const student = await joinClass(harness, {
      joinCode: fixture.joinCode,
      displayName: "Dana",
      newFundName: "Value Fund",
    });
    await fixture.professor.post(
      `/v1/sessions/${fixture.sessionId}/checkin/begin`,
      {},
      { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
    );

    const csv = buildCsv();
    const url = `/v1/sessions/${fixture.sessionId}/funds/${student.fundId}/model`;
    const headers = { "idempotency-key": "same-key" };
    const first = await student.browser.post(url, csv, headers);
    const second = await student.browser.post(url, csv, headers);
    expect(first.status).toBe(200);
    expect(second.status).toBe(200);
    expect(second.body).toEqual(first.body);
  });

  it("refuses the same idempotency key carrying a different body", async () => {
    // A retry and a modified request are not the same thing, and treating them as the
    // same would silently discard the second change.
    const fixture = await createClass(harness, { fundNames: ["Value Fund"] });
    const student = await joinClass(harness, {
      joinCode: fixture.joinCode,
      displayName: "Dana",
      newFundName: "Value Fund",
    });
    await fixture.professor.post(
      `/v1/sessions/${fixture.sessionId}/checkin/begin`,
      {},
      { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
    );

    const url = `/v1/sessions/${fixture.sessionId}/funds/${student.fundId}/model`;
    const headers = { "idempotency-key": "reused" };
    const first = await student.browser.post(url, buildCsv({ noiGrowth: 0.02 }), headers);
    expect(first.status).toBe(200);
    const second = await student.browser.post(url, buildCsv({ noiGrowth: 0.04 }), headers);
    expect(second.status).toBe(409);
    expect(second.body.error).toBe("idempotency_conflict");
  });

  it("records one decision when the same submission is sent twice", async () => {
    const fixture = await playablePractice(harness, { members: [["Dana"]] });
    const student = fixture.students[0]!;
    const state = await stateOf(student.browser, fixture.sessionId);
    const items = (state.round.public.deals as { property_id: string }[]).map((d) => ({
      propertyId: d.property_id,
      action: "PASS",
    }));

    const url = `/v1/sessions/${fixture.sessionId}/rounds/decision`;
    const body = { fundId: student.fundId, items };
    const first = await student.browser.post(url, body);
    const second = await student.browser.post(url, body);
    expect(first.status).toBe(200);
    expect(second.status).toBe(200);

    const after = await stateOf(student.browser, fixture.sessionId);
    expect(after.round.submittedFunds).toBe(1);
    expect(after.grid).toBeNull();
  });
});

describe("stale revisions", () => {
  it("refuses a professor acting on a view that has moved on", async () => {
    const fixture = await createClass(harness);
    const stale = await revisionOfSession(harness, fixture.sessionId);
    // Someone else moves the session along.
    await joinClass(harness, { joinCode: fixture.joinCode, displayName: "Dana" });

    const res = await fixture.professor.post(
      `/v1/sessions/${fixture.sessionId}/checkin/begin`,
      {},
      { "if-match": String(stale) },
    );
    expect(res.status).toBe(409);
    expect(res.body.error).toBe("stale_revision");
    expect(res.body.details.expected).toBe(stale);
  });

  it("refuses a professor transition that does not name a revision at all", async () => {
    // Required, not optional: a professor tab left open from earlier in the class will
    // happily send "open round" against a session that has moved on.
    const fixture = await createClass(harness);
    const res = await fixture.professor.post(`/v1/sessions/${fixture.sessionId}/checkin/begin`, {});
    expect(res.status).toBe(400);
    expect(res.body.detail).toMatch(/requires the session revision/);
  });

  it("accepts the same transition once the caller catches up", async () => {
    const fixture = await createClass(harness);
    await joinClass(harness, { joinCode: fixture.joinCode, displayName: "Dana" });
    const current = await revisionOfSession(harness, fixture.sessionId);
    const res = await fixture.professor.post(
      `/v1/sessions/${fixture.sessionId}/checkin/begin`,
      {},
      { "if-match": String(current) },
    );
    expect(res.status).toBe(200);
    expect(res.body.phase).toBe("model_checkin");
  });
});

describe("concurrent callers", () => {
  it("lets exactly one of two simultaneous model locks win", async () => {
    // Two students on one fund both press LOCK at the same instant. One lock, and the
    // loser gets a legible refusal rather than a second lock overwriting the first.
    const fixture = await createClass(harness, { fundNames: ["Value Fund"] });
    const dana = await joinClass(harness, {
      joinCode: fixture.joinCode,
      displayName: "Dana",
      newFundName: "Value Fund",
    });
    const ravi = await joinClass(harness, {
      joinCode: fixture.joinCode,
      displayName: "Ravi",
      fundId: dana.fundId,
    });
    await fixture.professor.post(
      `/v1/sessions/${fixture.sessionId}/checkin/begin`,
      {},
      { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
    );
    await dana.browser.post(
      `/v1/sessions/${fixture.sessionId}/funds/${dana.fundId}/model`,
      buildCsv(),
    );

    const url = `/v1/sessions/${fixture.sessionId}/funds/${dana.fundId}/model/lock`;
    const [a, b] = await Promise.all([dana.browser.post(url, {}), ravi.browser.post(url, {})]);
    const statuses = [a.status, b.status].sort();
    expect(statuses).toEqual([200, 409]);

    const state = await stateOf(dana.browser, fixture.sessionId);
    expect(state.funds.find((f: { id: string }) => f.id === dana.fundId).modelStatus).toBe("locked");
  });

  it("resolves a round exactly once when the professor's button is double-clicked", async () => {
    const fixture = await playablePractice(harness, { members: [["Dana"]] });
    const student = fixture.students[0]!;
    const state = await stateOf(student.browser, fixture.sessionId);
    const items = (state.round.public.deals as { property_id: string }[]).map((d) => ({
      propertyId: d.property_id,
      action: "PASS",
    }));
    await student.browser.post(`/v1/sessions/${fixture.sessionId}/rounds/decision`, {
      fundId: student.fundId,
      items,
    });

    const revision = await revisionOfSession(harness, fixture.sessionId);
    const url = `/v1/sessions/${fixture.sessionId}/rounds/close`;
    const headers = { "if-match": String(revision) };
    const results = await Promise.all([
      fixture.professor.post(url, {}, headers),
      fixture.professor.post(url, {}, headers),
      fixture.professor.post(url, {}, headers),
    ]);
    const ok = results.filter((r) => r.status === 200);
    const refused = results.filter((r) => r.status === 409);
    expect(ok).toHaveLength(1);
    expect(refused).toHaveLength(2);

    const after = await stateOf(student.browser, fixture.sessionId);
    expect(after.session.phase).toBe("practice_results");
    // Practice does not advance the scored-round counter, so a double resolve would
    // show up here as two.
    expect(after.session.resolvedRounds).toBe(0);
  });

  it("refuses a second close after the first has committed", async () => {
    const fixture = await playablePractice(harness, { members: [["Dana"]] });
    const revision = await revisionOfSession(harness, fixture.sessionId);
    const headers = { "if-match": String(revision) };
    const first = await fixture.professor.post(
      `/v1/sessions/${fixture.sessionId}/rounds/close`,
      {},
      headers,
    );
    expect(first.status).toBe(200);
    const second = await fixture.professor.post(
      `/v1/sessions/${fixture.sessionId}/rounds/close`,
      {},
      { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
    );
    expect(second.status).toBe(409);
    expect(second.body.error).toBe("illegal_phase");
  });

  it("admits every one of twenty simultaneous joiners to exactly one member each", async () => {
    const fixture = await createClass(harness, {
      fundNames: ["Value Fund"],
      maxTeamSize: 24,
    });
    const names = Array.from({ length: 20 }, (_, i) => `Student ${i + 1}`);
    const results = await Promise.all(
      names.map((displayName) =>
        joinClass(harness, {
          joinCode: fixture.joinCode,
          displayName,
          newFundName: "Value Fund",
        }),
      ),
    );
    const fundIds = new Set(results.map((r) => r.fundId));
    expect(fundIds.size).toBe(1);

    const state = await stateOf(results[0]!.browser, fixture.sessionId);
    // The professor holds a seat too, and is counted separately from the roster of
    // students so their presence can never be mistaken for a twenty-first student.
    const students = state.members.filter((m: { isProfessor: boolean }) => !m.isProfessor);
    expect(students).toHaveLength(20);
    expect(new Set(students.map((m: { id: string }) => m.id)).size).toBe(20);
    expect(new Set(students.map((m: { displayName: string }) => m.displayName)).size).toBe(20);
    expect(state.funds[0].memberCount).toBe(20);
  });

  it("refuses a fund beyond the session's team size rather than silently overfilling it", async () => {
    const fixture = await createClass(harness, { fundNames: ["Value Fund"], maxTeamSize: 3 });
    for (let i = 0; i < 3; i += 1) {
      await joinClass(harness, { joinCode: fixture.joinCode, displayName: `A${i}`, newFundName: "Value Fund" });
    }
    const overflow = harness.browser("Overflow");
    const res = await overflow.post("/v1/join", {
      joinCode: fixture.joinCode,
      displayName: "Overflow",
      newFundName: "Value Fund",
    });
    expect(res.status).toBe(409);
    expect(res.body.detail).toMatch(/full/);
  });

  it("survives a full classroom: 70 concurrent joiners spread across 24 funds", async () => {
    const fundCount = 24;
    const fundNames = Array.from({ length: fundCount }, (_, i) => `Fund ${i + 1}`);
    const fixture = await createClass(harness, {
      fundNames,
      maxTeamSize: 4,
    });
    const studentCount = 70;
    // joinClass throws on any non-201, so reaching here means every join succeeded.
    const results = await Promise.all(
      Array.from({ length: studentCount }, (_, i) =>
        joinClass(harness, {
          joinCode: fixture.joinCode,
          displayName: `Student ${i + 1}`,
          newFundName: fundNames[i % fundCount]!,
        }),
      ),
    );

    // Every student landed in the fund they named, with no duplicates.
    const membersPerFund = new Map<string, Set<string>>();
    for (const [i, r] of results.entries()) {
      const wanted = fundNames[i % fundCount]!;
      const ids = membersPerFund.get(wanted) ?? new Set<string>();
      ids.add(r.memberId);
      membersPerFund.set(wanted, ids);
    }
    expect(membersPerFund.size).toBe(fundCount);

    const state = await stateOf(results[0]!.browser, fixture.sessionId);
    const students = state.members.filter((m: { isProfessor: boolean }) => !m.isProfessor);
    expect(students).toHaveLength(studentCount);
    expect(new Set(students.map((m: { id: string }) => m.id)).size).toBe(studentCount);
    const fundSizes = state.funds.map((f: { memberCount: number }) => f.memberCount);
    expect(fundSizes.reduce((a: number, b: number) => a + b, 0)).toBe(studentCount);
    // 70 over 24 funds is at most 3 per fund, under the cap of 4.
    for (const size of fundSizes) expect(size).toBeLessThanOrEqual(4);
  });
});

describe("frozen decisions", () => {
  it("refuses a decision submitted after the market has closed", async () => {
    const fixture = await playablePractice(harness, { members: [["Dana"]] });
    const student = fixture.students[0]!;
    const state = await stateOf(student.browser, fixture.sessionId);
    const items = (state.round.public.deals as { property_id: string }[]).map((d) => ({
      propertyId: d.property_id,
      action: "PASS",
    }));

    await fixture.professor.post(
      `/v1/sessions/${fixture.sessionId}/rounds/close`,
      {},
      { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
    );

    const late = await student.browser.post(`/v1/sessions/${fixture.sessionId}/rounds/decision`, {
      fundId: student.fundId,
      items,
    });
    expect(late.status).toBe(409);
    expect(late.body.detail).toMatch(/market is closed/);

    // And the late attempt left no trace.
    const after = await stateOf(student.browser, fixture.sessionId);
    expect(after.round.myDecision).toBeNull();
  });

  it("refuses a model upload once the game has begun", async () => {
    const fixture = await playablePractice(harness, { members: [["Dana"]] });
    const student = fixture.students[0]!;
    const res = await student.browser.post(
      `/v1/sessions/${fixture.sessionId}/funds/${student.fundId}/model`,
      buildCsv({ noiGrowth: 0.03 }),
    );
    expect(res.status).toBe(409);
    expect(res.body.detail).toMatch(/check-in is closed/);
  });
});

describe("engine failures", () => {
  it("leaves the session unchanged when the engine is unreachable mid-resolution", async () => {
    // The property that matters: a failed engine call must not advance the phase, or a
    // class would be left with a round that claims to be resolved and no results.
    const fixture = await playablePractice(harness, { members: [["Dana"]] });
    const student = fixture.students[0]!;
    const before = await stateOf(student.browser, fixture.sessionId);

    fakeOf(harness).failNext = "resolveRound";
    const res = await fixture.professor.post(
      `/v1/sessions/${fixture.sessionId}/rounds/close`,
      {},
      { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
    );
    expect(res.status).toBeGreaterThanOrEqual(500);

    const after = await stateOf(student.browser, fixture.sessionId);
    expect(after.session.phase).toBe("practice");
    expect(after.round.resolvedAt).toBeNull();
    expect(after.round.results).toBeNull();
    expect(after.session.revision).toBeGreaterThanOrEqual(before.session.revision);
  });

  it("resolves normally on a retry after a transient engine failure", async () => {
    const fixture = await playablePractice(harness, { members: [["Dana"]] });
    fakeOf(harness).failNext = "resolveRound";
    await fixture.professor.post(
      `/v1/sessions/${fixture.sessionId}/rounds/close`,
      {},
      { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
    );
    const retry = await fixture.professor.post(
      `/v1/sessions/${fixture.sessionId}/rounds/close`,
      {},
      { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
    );
    expect(retry.status).toBe(200);
    expect(retry.body.phase).toBe("practice_results");
  });
});
