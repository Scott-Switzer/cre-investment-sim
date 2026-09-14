/**
 * The projection boundary.
 *
 * Risk R1 — the reserve price and every future outcome reaching the browser — is the
 * highest-consequence failure in the design, because it is the whole integrity of the
 * auction. Structure removes most of it (the engine never returns those fields before
 * a reveal), and `assertSafeView` removes the rest: it fails closed the moment a view
 * builder forgets itself, which is the failure mode subtraction-based serialisers have.
 *
 * The second theme here is that a *view* must not become a second engine. Every number
 * a player sees is the engine's; this service only decides what to include.
 */

import { describe, expect, it } from "vitest";

import { assertSafeView, forecastForProperties, submissionGrid } from "./views.js";
import { sessionView } from "./views.js";
import { PRACTICE_ROUND, type SessionState } from "./domain.js";
import { startHarness } from "./testing/harness.js";
import { playablePractice } from "./testing/scenarios.js";
import { FakeEngine } from "./testing/fakeEngine.js";

describe("assertSafeView", () => {
  it("passes an ordinary player view", () => {
    expect(() =>
      assertSafeView(
        {
          session: { id: "sess_1", phase: "practice", revision: 3 },
          round: { round: -1, public: { deals: [{ property_id: "P1" }] } },
        },
        "ordinary",
      ),
    ).not.toThrow();
  });

  it("catches the engine snapshot by key, at any depth", () => {
    expect(() => assertSafeView({ engineState: "…" }, "top")).toThrow(/engineState/);
    expect(() =>
      assertSafeView({ round: { inner: { engineState: "…" } } }, "nested"),
    ).toThrow(/round\.inner\.engineState/);
    expect(() => assertSafeView({ a: [{ engineState: "…" }] }, "array")).toThrow(
      /a\[0\]\.engineState/,
    );
  });

  it("catches the snapshot under a near-miss name", () => {
    expect(() => assertSafeView({ engine_state: 1 }, "snake")).toThrow();
    expect(() => assertSafeView({ engineStateBytes: 12 }, "size")).toThrow();
  });

  it("catches a byte buffer, because in this service that shape *is* the snapshot", () => {
    // The durable guard: a view builder that renamed the field would still be caught,
    // because nothing else in a player payload is ever bytes.
    expect(() => assertSafeView({ anything: new Uint8Array([1, 2, 3]) }, "bytes")).toThrow(
      /byte buffer/,
    );
  });
});

describe("the real state view", () => {
  it("carries no snapshot and no byte buffer, for either audience", async () => {
    const harness = await startHarness();
    try {
      const fixture = await playablePractice(harness, {
        members: [["Dana", "Ravi"]],
      });
      const student = fixture.students[0]!;
      const studentView = (await student.browser.get(`/v1/sessions/${fixture.sessionId}/state`))
        .body;
      const professorView = (
        await fixture.professor.get(`/v1/sessions/${fixture.sessionId}/state`)
      ).body;

      for (const [label, view] of [
        ["student", studentView],
        ["professor", professorView],
      ] as const) {
        expect(() => assertSafeView(view, label)).not.toThrow();
        expect(JSON.stringify(view)).not.toContain("engineState");
      }
    } finally {
      await harness.close();
    }
  });

  it("takes the sanctioned snapshot apart when it is injected into a view", async () => {
    // Proves the guard is wired to the real object, not to a string that happens to
    // match: the stored snapshot is a byte buffer, and injecting it must fail.
    const harness = await startHarness();
    try {
      const fixture = await playablePractice(harness, { members: [["Dana"]] });
      const session = harness.store.inspect(fixture.sessionId)!.session;
      expect(session.engineState).toBeInstanceOf(Uint8Array);
      expect(session.engineState!.byteLength).toBeGreaterThan(0);

      expect(() => assertSafeView({ ...sessionView(session) }, "leaked")).not.toThrow();
      expect(() => assertSafeView(session, "raw session document")).toThrow(
        /engineState|byte buffer/,
      );
    } finally {
      await harness.close();
    }
  });

  it("never names the dataset seed", async () => {
    // The seed plus the generator is the whole game, and the bundle carries it as
    // engine metadata precisely so that it stays server-side.
    const harness = await startHarness();
    try {
      const fixture = await playablePractice(harness, { members: [["Dana"]] });
      const view = (await fixture.professor.get(`/v1/sessions/${fixture.sessionId}/state`)).body;
      expect(view.session).not.toHaveProperty("seed");
      expect(JSON.stringify(view)).not.toContain('"seed"');
    } finally {
      await harness.close();
    }
  });

  it("scopes a fund's forecast to the properties this round offers", async () => {
    const harness = await startHarness();
    try {
      const fixture = await playablePractice(harness, { members: [["Dana"]] });
      const student = fixture.students[0]!;
      const engine = new FakeEngine();
      void engine;
      const view = (await student.browser.get(`/v1/sessions/${fixture.sessionId}/state`)).body;
      const offered = (view.round.public.deals as { property_id: string }[]).map(
        (d) => d.property_id,
      );
      const forecastIds = view.round.myForecast.map(
        (f: { propertyId: string }) => f.propertyId,
      );
      expect(forecastIds).toEqual([...offered].sort());
      // Four candidates in the pool; one is offered in practice. Sending all four would
      // make the response 4x larger and put the fund's whole forecast one render away.
      expect(forecastIds.length).toBeLessThan(4);
    } finally {
      await harness.close();
    }
  });
});

describe("forecastForProperties", () => {
  const rows = [
    {
      propertyId: "P3",
      forecast: {
        modelName: "m",
        predictedFairValue: 3,
        predictedNoiGrowth: 0.01,
        probabilityOfDownside: 0.2,
        confidence: null,
      },
      policy: { maxBid: 2, targetLtv: 0.5 },
    },
    {
      propertyId: "P1",
      forecast: {
        modelName: "m",
        predictedFairValue: 1,
        predictedNoiGrowth: 0.01,
        probabilityOfDownside: 0.2,
        confidence: null,
      },
      policy: { maxBid: 1, targetLtv: 0.5 },
    },
  ];

  it("filters to the offered ids and orders them, so a view is not order-dependent", () => {
    expect(forecastForProperties(rows, ["P3"]).map((r) => r.propertyId)).toEqual(["P3"]);
    expect(forecastForProperties(rows, ["P3", "P1"]).map((r) => r.propertyId)).toEqual([
      "P1",
      "P3",
    ]);
  });

  it("returns nothing when nothing is offered rather than the whole model", () => {
    expect(forecastForProperties(rows, [])).toEqual([]);
  });
});

describe("submissionGrid", () => {
  const fund = {
    id: "fund_1",
    sessionId: "sess_1",
    name: "Value Fund",
    memberIds: [],
    modelStatus: "locked" as const,
    modelName: "m",
    modelLockedAt: null,
    modelRowCount: 0,
    modelValidatedAt: null,
    forecastSummary: null,
    createdAt: "2026-01-01T00:00:00.000Z",
  };
  const rows = [
    {
      propertyId: "P1",
      forecast: {
        modelName: "m",
        predictedFairValue: 100,
        predictedNoiGrowth: 0.01,
        probabilityOfDownside: 0.2,
        confidence: null,
      },
      policy: { maxBid: 90, targetLtv: 0.5 },
    },
  ];

  it("counts a silent fund as not submitted", () => {
    const grid = submissionGrid({ funds: [fund], decisions: new Map(), rows: new Map() });
    expect(grid[0]).toMatchObject({ submitted: false, bids: 0, passes: 0 });
  });

  it("counts submissions above the fund's own ceiling separately from the engine's override count", () => {
    // Naming matters: the engine's `override_count` counts overrides on properties a
    // fund *won*. These are submission-time counts, which is the fact a professor wants
    // mid-round. Two different numbers must not share a name.
    const grid = submissionGrid({
      funds: [fund],
      decisions: new Map([
        [
          fund.id,
          {
            sessionId: "sess_1",
            round: 0,
            fundId: fund.id,
            submittedBy: "mem_1",
            submittedAt: "2026-01-01T00:00:00.000Z",
            items: [
              { propertyId: "P1", action: "BID", bid: 95, ltv: 0.6 },
              { propertyId: "P2", action: "PASS", bid: null, ltv: null },
            ],
          },
        ],
      ]),
      rows: new Map([[fund.id, rows]]),
    });
    expect(grid[0]).toMatchObject({
      submitted: true,
      bids: 1,
      passes: 1,
      bidsAboveOwnCeiling: 1,
      ltvAboveOwnTarget: 1,
    });
    expect(grid[0]).not.toHaveProperty("overrideCount");
  });

  it("does not count a bid exactly at the ceiling as an override", () => {
    const grid = submissionGrid({
      funds: [fund],
      decisions: new Map([
        [
          fund.id,
          {
            sessionId: "sess_1",
            round: 0,
            fundId: fund.id,
            submittedBy: "mem_1",
            submittedAt: "2026-01-01T00:00:00.000Z",
            items: [{ propertyId: "P1", action: "BID", bid: 90, ltv: 0.5 }],
          },
        ],
      ]),
      rows: new Map([[fund.id, rows]]),
    });
    expect(grid[0]!.bidsAboveOwnCeiling).toBe(0);
    expect(grid[0]!.ltvAboveOwnTarget).toBe(0);
  });
});

describe("what a client is told to do next", () => {
  const base: SessionState = {
    id: "sess_1",
    name: "REAL 605",
    joinCode: "ABCDEF",
    bundleId: "b",
    bundleDisplayName: "Dataset",
    candidatePoolHash: "h",
    poolCount: 120,
    mode: "team",
    maxTeamSize: 4,
    totalRounds: 4,
    practiceEnabled: true,
    phase: "lobby",
    currentRound: PRACTICE_ROUND,
    resolvedRounds: 0,
    revision: 0,
    engineState: null,
    engineStateBytes: 0,
    engineCreatedAt: null,
    createdAt: "2026-01-01T00:00:00.000Z",
    updatedAt: "2026-01-01T00:00:00.000Z",
  };

  it("is server-owned, present and specific in every phase", () => {
    // A client that decides its own phase is wrong exactly once, in front of a class.
    const cases: [Partial<SessionState>, RegExp][] = [
      [{ phase: "lobby" }, /Waiting for your professor/],
      [{ phase: "model_checkin" }, /Upload your team's model/],
      [{ phase: "practice", currentRound: -1 }, /Practice is open/],
      [{ phase: "practice_results", currentRound: -1 }, /Round 1 next/],
      [{ phase: "round", currentRound: 0 }, /Round 1 of 4 is open/],
      [{ phase: "round", currentRound: 2 }, /Round 3 of 4 is open/],
      [{ phase: "round_results", currentRound: 0 }, /next round/],
      [{ phase: "finale" }, /complete/],
    ];
    for (const [patch, pattern] of cases) {
      const view = sessionView({ ...base, ...patch });
      expect(view.nextStep).toMatch(pattern);
      expect(view.phase).toBe(patch.phase);
    }
  });

  it("labels the round in the terms a student is shown", () => {
    expect(sessionView({ ...base, currentRound: -1 }).roundLabel).toBe("Practice");
    expect(sessionView({ ...base, currentRound: 0 }).roundLabel).toBe("Round 1 of 4");
    expect(sessionView({ ...base, currentRound: 3 }).roundLabel).toBe("Round 4 of 4");
  });

  it("reports completion from resolved rounds, not from a stored flag", () => {
    expect(sessionView({ ...base, resolvedRounds: 3 }).gameComplete).toBe(false);
    expect(sessionView({ ...base, resolvedRounds: 4 }).gameComplete).toBe(true);
  });

  it("says the debrief is next once the last scored round is in", () => {
    const view = sessionView({
      ...base,
      phase: "round_results",
      resolvedRounds: 4,
      currentRound: 3,
    });
    expect(view.gameComplete).toBe(true);
    expect(view.nextStep).toMatch(/final debrief/);
  });
});
