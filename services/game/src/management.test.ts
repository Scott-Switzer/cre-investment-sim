/**
 * The management layer, at the service boundary.
 *
 * What this service owns is not the economics — the engine decides what a stance
 * costs. It owns the *plumbing*: that a fund's stance reaches the engine with the bids
 * for the same round, that a tier without a management decision cannot receive one,
 * that a refusal is reported rather than swallowed, and that a refresh shows what was
 * actually submitted.
 *
 * The tests run against the contract-shaped fake engine, so they are about shape and
 * sequence. Whether a stance for a building the fund does not own is refused is the
 * real engine's rule and is tested in the Python suite; here the fake injects a refusal
 * to prove the *reporting* path works.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { fakeOf, startHarness, type Harness } from "./testing/harness.js";
import {
  FAKE_COURSE_TIERS,
  type FakeEngine,
} from "./testing/fakeEngine.js";
import { playablePractice, revisionOfSession, stateOf } from "./testing/scenarios.js";
import type { EngineManagementStance } from "./engineClient.js";

let harness: Harness;

beforeEach(async () => {
  harness = await startHarness();
});

afterEach(async () => {
  await harness.close();
});

function engine(): FakeEngine {
  return fakeOf(harness);
}

/** A class in a practice round, with one fund, at the named tier. */
async function atTier(courseMode: string) {
  return playablePractice(harness, { members: [["Dana"]], courseMode });
}

async function submit(
  fixture: { students: { browser: any; fundId: string }[]; sessionId: string },
  body: Record<string, unknown>,
) {
  const student = fixture.students[0]!;
  return student.browser.post(`/v1/sessions/${fixture.sessionId}/rounds/decision`, {
    fundId: student.fundId,
    ...body,
  });
}

async function closeRound(fixture: {
  professor: any;
  sessionId: string;
}): Promise<{ status: number; body: any }> {
  return fixture.professor.post(
    `/v1/sessions/${fixture.sessionId}/rounds/close`,
    {},
    { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
  );
}

const passOnEveryDeal = (deals: { property_id: string }[]) =>
  deals.map((d) => ({ propertyId: d.property_id, action: "PASS" as const }));

describe("the course tier is server truth", () => {
  it("records the tier the engine reported and publishes it on the round", async () => {
    const fixture = await atTier("310");
    const view = await stateOf(fixture.students[0]!.browser, fixture.sessionId);
    expect(view.session.courseMode).toBe("310");
    expect(view.round.management).toMatchObject({
      enabled: true,
      hasStanceChoice: true,
      courseMode: "310",
      stances: FAKE_COURSE_TIERS["310"]!.stances,
    });
  });

  it("publishes a tier with no stance choice for 220, and none at all for 605", async () => {
    const simplified = await atTier("220");
    const view220 = await stateOf(simplified.students[0]!.browser, simplified.sessionId);
    expect(view220.round.management.enabled).toBe(true);
    expect(view220.round.management.hasStanceChoice).toBe(false);

    await harness.close();
    harness = await startHarness();
    const plain = await atTier("605");
    const view605 = await stateOf(plain.students[0]!.browser, plain.sessionId);
    expect(view605.round.management.enabled).toBe(false);
    expect(view605.round.management.hasStanceChoice).toBe(false);
  });

  it("an unknown tier is refused at creation rather than defaulted", async () => {
    const professor = harness.browser("professor");
    const res = await professor.post("/v1/sessions", {
      name: "Bad tier",
      professorPasscode: "frenzel",
      courseMode: "605x",
    });
    // The fake engine accepts any tier string; the *real* engine refuses an unknown
    // one, which is asserted in the Python suite. What this service must never do is
    // invent a tier, so the tier that reaches the engine is the one that was named.
    expect(res.status).toBe(201);
    const sent = engine().calls.find((c) => c.method === "createGameState");
    expect(sent).toBeUndefined(); // creation does not create a game; start does
  });
});

describe("submitting a stance", () => {
  it("carries the fund's stances to the engine with the bids for the same round", async () => {
    const fixture = await atTier("310");
    const view = await stateOf(fixture.students[0]!.browser, fixture.sessionId);
    const deals = view.round.public.deals as { property_id: string }[];

    const res = await submit(fixture, {
      items: passOnEveryDeal(deals),
      stances: [
        { propertyId: "P1", stance: "INVEST & PROTECT" },
        { propertyId: "P2", stance: "RUN LEAN" },
      ],
    });
    expect(res.status).toBe(200);

    await closeRound(fixture);
    const resolved = engine().calls.find((c) => c.method === "resolveRound")!.args as {
      managementStances: EngineManagementStance[];
      decisions: unknown[];
    };
    expect(resolved.managementStances).toHaveLength(2);
    expect(resolved.managementStances).toContainEqual({
      team_id: fixture.students[0]!.fundId,
      property_id: "P1",
      stance: "INVEST & PROTECT",
    });
    // The bids are still there: a stance rides the decision, it does not replace it.
    expect(resolved.decisions).toHaveLength(deals.length);
  });

  it("accepts a decision with no stances at all", async () => {
    const fixture = await atTier("310");
    const view = await stateOf(fixture.students[0]!.browser, fixture.sessionId);
    const res = await submit(fixture, {
      items: passOnEveryDeal(view.round.public.deals),
    });
    expect(res.status).toBe(200);
    expect(res.body.decision.stances).toEqual([]);
  });

  it("returns what was submitted, so a refresh shows the same choices", async () => {
    const fixture = await atTier("310");
    const view = await stateOf(fixture.students[0]!.browser, fixture.sessionId);
    await submit(fixture, {
      items: passOnEveryDeal(view.round.public.deals),
      stances: [{ propertyId: "P1", stance: "RUN LEAN" }],
    });

    const after = await stateOf(fixture.students[0]!.browser, fixture.sessionId);
    expect(after.round.myDecision.stances).toEqual([
      { propertyId: "P1", stance: "RUN LEAN" },
    ]);
  });

  it("replaces rather than accumulates when a fund changes its mind", async () => {
    const fixture = await atTier("310");
    const view = await stateOf(fixture.students[0]!.browser, fixture.sessionId);
    const items = passOnEveryDeal(view.round.public.deals);
    await submit(fixture, { items, stances: [{ propertyId: "P1", stance: "RUN LEAN" }] });
    const second = await submit(fixture, {
      items,
      stances: [{ propertyId: "P1", stance: "INVEST & PROTECT" }],
    });
    expect(second.status).toBe(200);

    await closeRound(fixture);
    const resolved = engine().calls.find((c) => c.method === "resolveRound")!.args as {
      managementStances: EngineManagementStance[];
    };
    expect(resolved.managementStances).toEqual([
      {
        team_id: fixture.students[0]!.fundId,
        property_id: "P1",
        stance: "INVEST & PROTECT",
      },
    ]);
  });
});

describe("a stance the session cannot use", () => {
  it("is refused on the 605 course tier, naming the tier", async () => {
    const fixture = await atTier("605");
    const view = await stateOf(fixture.students[0]!.browser, fixture.sessionId);
    const res = await submit(fixture, {
      items: passOnEveryDeal(view.round.public.deals),
      stances: [{ propertyId: "P1", stance: "RUN LEAN" }],
    });
    expect(res.status).toBe(400);
    expect(res.body.detail).toMatch(/605 course tier/);
    expect(res.body.detail).toMatch(/no management decision/);
  });

  it("is refused on 220, where the operating year runs but there is no choice", async () => {
    const fixture = await atTier("220");
    const view = await stateOf(fixture.students[0]!.browser, fixture.sessionId);
    const res = await submit(fixture, {
      items: passOnEveryDeal(view.round.public.deals),
      stances: [{ propertyId: "P1", stance: "INVEST & PROTECT" }],
    });
    expect(res.status).toBe(400);
    expect(res.body.detail).toMatch(/220 course tier/);
  });

  it("is refused when the stance is not one the engine named", async () => {
    const fixture = await atTier("310");
    const view = await stateOf(fixture.students[0]!.browser, fixture.sessionId);
    const res = await submit(fixture, {
      items: passOnEveryDeal(view.round.public.deals),
      stances: [{ propertyId: "P1", stance: "YOLO" }],
    });
    expect(res.status).toBe(400);
    expect(res.body.detail).toMatch(/YOLO.*not a management stance/s);
  });

  it("is refused when one building is decided twice", async () => {
    const fixture = await atTier("310");
    const view = await stateOf(fixture.students[0]!.browser, fixture.sessionId);
    const res = await submit(fixture, {
      items: passOnEveryDeal(view.round.public.deals),
      stances: [
        { propertyId: "P1", stance: "RUN LEAN" },
        { propertyId: "P1", stance: "STANDARD" },
      ],
    });
    expect(res.status).toBe(400);
    expect(res.body.detail).toMatch(/twice/);
  });

  it("never crashes a round: a refusal by the engine is reported, not thrown", async () => {
    const fixture = await atTier("310");
    const view = await stateOf(fixture.students[0]!.browser, fixture.sessionId);
    // The engine's own rule decision — here it refuses a building the fund does not
    // own, which is exactly the case the service deliberately does not pre-empt.
    engine().rejectStancesFor = () => "Property NOT-MINE is not in this fund's portfolio";

    await submit(fixture, {
      items: passOnEveryDeal(view.round.public.deals),
      stances: [{ propertyId: "NOT-MINE", stance: "RUN LEAN" }],
    });
    const closed = await closeRound(fixture);
    expect(closed.status).toBe(200);

    const after = await stateOf(fixture.students[0]!.browser, fixture.sessionId);
    expect(after.round.rejectedStances).toEqual([
      {
        fundId: fixture.students[0]!.fundId,
        propertyId: "NOT-MINE",
        reason: "Property NOT-MINE is not in this fund's portfolio",
      },
    ]);
  });
});

describe("what the professor can see", () => {
  it("counts each fund's postures, and never an amount", async () => {
    const fixture = await playablePractice(harness, {
      members: [["Dana"], ["Ravi"]],
      fundNames: ["Value Fund", "Growth Fund"],
      courseMode: "310",
    });
    const dana = fixture.students[0]!;
    const view = await stateOf(dana.browser, fixture.sessionId);
    await dana.browser.post(`/v1/sessions/${fixture.sessionId}/rounds/decision`, {
      fundId: dana.fundId,
      items: passOnEveryDeal(view.round.public.deals),
      stances: [
        { propertyId: "P1", stance: "RUN LEAN" },
        { propertyId: "P2", stance: "RUN LEAN" },
        { propertyId: "P3", stance: "INVEST & PROTECT" },
      ],
    });

    const professorView = await stateOf(fixture.professor, fixture.sessionId);
    const danaRow = professorView.grid.find((r: any) => r.fundName === "Value Fund");
    const raviRow = professorView.grid.find((r: any) => r.fundName === "Growth Fund");
    expect(danaRow.stancesSet).toBe(3);
    expect(danaRow.stanceTally).toEqual({ "RUN LEAN": 2, "INVEST & PROTECT": 1 });
    expect(raviRow.submitted).toBe(false);
    expect(raviRow.stancesSet).toBe(0);
    // The grid is projected for the room: it must not carry a stance *amount*.
    expect(JSON.stringify(professorView.grid)).not.toMatch(/maintenance|upkeep|cost/i);
  });
});
