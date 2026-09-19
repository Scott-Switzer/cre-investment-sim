/**
 * The round lifecycle.
 *
 * The engine owns the auction; what this service owns is the *sequence* — that a round
 * cannot open before the last one resolved, that a decision covers every property
 * including the passes, that results do not exist before the reveal, and that four
 * rounds can be played end to end without the phase machine drifting.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { fakeOf, startHarness, type Harness } from "./testing/harness.js";
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

async function state(browser: { get: (u: string) => Promise<{ body: any }> }, sessionId: string) {
  return (await browser.get(`/v1/sessions/${sessionId}/state`)).body;
}

function decisionsFor(deals: { property_id: string }[], action: "PASS" | "BID" = "PASS") {
  return deals.map((d) =>
    action === "PASS"
      ? { propertyId: d.property_id, action: "PASS" as const }
      : {
          propertyId: d.property_id,
          action: "BID" as const,
          bid: 9,
          ltv: 0.5,
        },
  );
}

describe("starting the game", () => {
  it("refuses to start while a fund has not locked a model, and names it", async () => {
    // Starting with an empty model would let a fund play without a forecast, and the
    // engine would treat it as having no view at all rather than telling anyone.
    const fixture = await createClass(harness, { fundNames: ["Value Fund", "Growth Fund"] });
    await joinClass(harness, {
      joinCode: fixture.joinCode,
      displayName: "Dana",
      newFundName: "Value Fund",
    });
    const ravi = await joinClass(harness, {
      joinCode: fixture.joinCode,
      displayName: "Ravi",
      newFundName: "Growth Fund",
    });
    await fixture.professor.post(
      `/v1/sessions/${fixture.sessionId}/checkin/begin`,
      {},
      { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
    );
    await ravi.browser.post(
      `/v1/sessions/${fixture.sessionId}/funds/${ravi.fundId}/model`,
      buildCsv(),
    );
    await ravi.browser.post(`/v1/sessions/${fixture.sessionId}/funds/${ravi.fundId}/model/lock`, {});

    const res = await fixture.professor.post(
      `/v1/sessions/${fixture.sessionId}/game/start`,
      {},
      { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
    );
    expect(res.status).toBe(409);
    expect(res.body.detail).toMatch(/waiting on 1 fund\(s\) to lock a model: Value Fund/);
  });

  it("refuses to start a session with no funds at all", async () => {
    const fixture = await createClass(harness, { fundNames: [] });
    await fixture.professor.post(
      `/v1/sessions/${fixture.sessionId}/checkin/begin`,
      {},
      { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
    );
    const res = await fixture.professor.post(
      `/v1/sessions/${fixture.sessionId}/game/start`,
      {},
      { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
    );
    expect(res.status).toBe(409);
    expect(res.body.detail).toMatch(/no funds/);
  });

  it("opens practice, not Round 1, and sends each fund's own model to the engine", async () => {
    const fixture = await playablePractice(harness, { members: [["Dana"]] });
    expect(fakeOf(harness).count("createGameState")).toBe(1);

    const sent = fakeOf(harness).calls.find((c) => c.method === "createGameState")!
      .args as { teams: { team_id: string; submissions: unknown[] }[] };
    expect(sent.teams).toHaveLength(1);
    expect(sent.teams[0]!.submissions).toHaveLength(4);

    const view = await state(fixture.students[0]!.browser, fixture.sessionId);
    expect(view.session.phase).toBe("practice");
    expect(view.session.currentRound).toBe(-1);
    expect(view.session.isPracticeRound).toBe(true);
    expect(view.session.roundLabel).toBe("Practice");
  });

  it("is refused a second time by the state machine, not by a convention", async () => {
    const fixture = await playablePractice(harness, { members: [["Dana"]] });
    const res = await fixture.professor.post(
      `/v1/sessions/${fixture.sessionId}/game/start`,
      {},
      { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
    );
    expect(res.status).toBe(409);
    expect(res.body.error).toBe("illegal_phase");
  });

  it("refuses to open a round before the current one is resolved", async () => {
    const fixture = await playablePractice(harness, { members: [["Dana"]] });
    const res = await fixture.professor.post(
      `/v1/sessions/${fixture.sessionId}/rounds/open`,
      {},
      { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
    );
    expect(res.status).toBe(409);
    expect(res.body.error).toBe("illegal_phase");
  });
});

describe("submitting a decision", () => {
  it("requires an explicit choice for every offered property, passes included", async () => {
    // "I chose not to bid" is the decision this exercise is about, so it is not
    // allowed to be the silent default.
    const fixture = await playablePractice(harness, { members: [["Dana"]] });
    const student = fixture.students[0]!;
    const view = await state(student.browser, fixture.sessionId);
    const deals = view.round.public.deals as { property_id: string }[];
    expect(deals.length).toBeGreaterThan(0);

    const partial = await student.browser.post(
      `/v1/sessions/${fixture.sessionId}/rounds/decision`,
      { fundId: student.fundId, items: [] },
    );
    expect(partial.status).toBe(400);
    expect(partial.body.detail).toMatch(/decide on every property offered/);
    expect(partial.body.details.missing).toEqual(deals.map((d) => d.property_id));
  });

  it("refuses a property that is not on the table this round", async () => {
    const fixture = await playablePractice(harness, { members: [["Dana"]] });
    const student = fixture.students[0]!;
    const view = await state(student.browser, fixture.sessionId);
    const deals = view.round.public.deals as { property_id: string }[];
    const items = [
      ...decisionsFor(deals),
      { propertyId: "P4", action: "BID", bid: 5, ltv: 0.5 },
    ].filter((item) => !deals.some((d) => d.property_id === item.propertyId));

    const res = await student.browser.post(
      `/v1/sessions/${fixture.sessionId}/rounds/decision`,
      { fundId: student.fundId, items },
    );
    expect(res.status).toBe(400);
    expect(res.body.detail).toMatch(/not offered in this round/);
  });

  it("refuses the same property decided twice", async () => {
    const fixture = await playablePractice(harness, { members: [["Dana"]] });
    const student = fixture.students[0]!;
    const view = await state(student.browser, fixture.sessionId);
    const deals = view.round.public.deals as { property_id: string }[];
    const first = decisionsFor(deals);
    const res = await student.browser.post(
      `/v1/sessions/${fixture.sessionId}/rounds/decision`,
      { fundId: student.fundId, items: [...first, first[0]] },
    );
    expect(res.status).toBe(400);
    expect(res.body.detail).toMatch(/decided twice/);
  });

  it("refuses leverage above the published ceiling on the deal", async () => {
    // Checked against a *published* field, not a re-derived rule: the deal DTO carries
    // max_ltv, so this is reading a limit the engine already sent.
    const fixture = await playablePractice(harness, { members: [["Dana"]] });
    const student = fixture.students[0]!;
    const view = await state(student.browser, fixture.sessionId);
    const deal = (view.round.public.deals as { property_id: string; max_ltv: number }[])[0]!;
    const res = await student.browser.post(
      `/v1/sessions/${fixture.sessionId}/rounds/decision`,
      {
        fundId: student.fundId,
        items: [
          { propertyId: deal.property_id, action: "BID", bid: 8, ltv: deal.max_ltv + 0.1 },
        ],
      },
    );
    expect(res.status).toBe(400);
    expect(res.body.detail).toMatch(/ceiling of/);
  });

  it("refuses a bid with no price", async () => {
    const fixture = await playablePractice(harness, { members: [["Dana"]] });
    const student = fixture.students[0]!;
    const view = await state(student.browser, fixture.sessionId);
    const deal = (view.round.public.deals as { property_id: string }[])[0]!;
    const res = await student.browser.post(
      `/v1/sessions/${fixture.sessionId}/rounds/decision`,
      { fundId: student.fundId, items: [{ propertyId: deal.property_id, action: "BID", ltv: 0.5 }] },
    );
    expect(res.status).toBe(400);
    expect(res.body.detail).toMatch(/must be a positive price/);
  });

  it("lets a fund revise its decision while the market is open", async () => {
    const fixture = await playablePractice(harness, { members: [["Dana"]] });
    const student = fixture.students[0]!;
    const view = await state(student.browser, fixture.sessionId);
    const deals = view.round.public.deals as { property_id: string }[];

    await student.browser.post(`/v1/sessions/${fixture.sessionId}/rounds/decision`, {
      fundId: student.fundId,
      items: decisionsFor(deals, "BID"),
    });
    let after = await state(student.browser, fixture.sessionId);
    expect(after.round.myDecision.items[0].action).toBe("BID");

    await student.browser.post(`/v1/sessions/${fixture.sessionId}/rounds/decision`, {
      fundId: student.fundId,
      items: decisionsFor(deals, "PASS"),
    });
    after = await state(student.browser, fixture.sessionId);
    expect(after.round.myDecision.items[0].action).toBe("PASS");
    expect(after.round.myDecision.items[0].bid).toBeNull();
    // Revision, not accumulation: one decision per fund per round.
    expect(after.round.submittedFunds).toBe(1);
  });

  it("refuses decisions from a student in a different fund", async () => {
    const fixture = await createClass(harness, { fundNames: ["Value Fund", "Growth Fund"] });
    const dana = await joinClass(harness, {
      joinCode: fixture.joinCode,
      displayName: "Dana",
      newFundName: "Value Fund",
    });
    const ravi = await joinClass(harness, {
      joinCode: fixture.joinCode,
      displayName: "Ravi",
      newFundName: "Growth Fund",
    });
    await fixture.professor.post(
      `/v1/sessions/${fixture.sessionId}/checkin/begin`,
      {},
      { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
    );
    for (const fundId of [dana.fundId, ravi.fundId]) {
      const browser = fundId === dana.fundId ? dana.browser : ravi.browser;
      await browser.post(
        `/v1/sessions/${fixture.sessionId}/funds/${fundId}/model`,
        buildCsv(),
      );
      await browser.post(`/v1/sessions/${fixture.sessionId}/funds/${fundId}/model/lock`, {});
    }
    await fixture.professor.post(
      `/v1/sessions/${fixture.sessionId}/game/start`,
      {},
      { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
    );

    const view = await state(dana.browser, fixture.sessionId);
    const deals = view.round.public.deals as { property_id: string }[];
    const res = await dana.browser.post(`/v1/sessions/${fixture.sessionId}/rounds/decision`, {
      fundId: ravi.fundId,
      items: decisionsFor(deals),
    });
    expect(res.status).toBe(403);
    expect(res.body.detail).toMatch(/not a member of fund/);
  });
});

describe("results and the reveal", () => {
  it("publishes nothing about outcomes until the round resolves", async () => {
    const fixture = await playablePractice(harness, { members: [["Dana"]] });
    const student = fixture.students[0]!;
    const before = await state(student.browser, fixture.sessionId);
    expect(before.round.resolvedAt).toBeNull();
    expect(before.round.results).toBeNull();
    expect(JSON.stringify(before)).not.toContain("reserve_price");
    expect(JSON.stringify(before)).not.toContain("realized_value");
  });

  it("publishes the reveal, the standings and who won once it resolves", async () => {
    const fixture = await playablePractice(harness, { members: [["Dana"]] });
    const student = fixture.students[0]!;
    const view = await state(student.browser, fixture.sessionId);
    const deal = (view.round.public.deals as { property_id: string; asking_price: number }[])[0]!;

    await student.browser.post(`/v1/sessions/${fixture.sessionId}/rounds/decision`, {
      fundId: student.fundId,
      items: [
        {
          propertyId: deal.property_id,
          action: "BID",
          bid: deal.asking_price,
          ltv: 0.5,
        },
      ],
    });

    const closed = await fixture.professor.post(
      `/v1/sessions/${fixture.sessionId}/rounds/close`,
      {},
      { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
    );
    expect(closed.status).toBe(200);
    expect(closed.body.phase).toBe("practice_results");

    const after = await state(student.browser, fixture.sessionId);
    expect(after.round.resolvedAt).toBeTruthy();
    expect(after.round.results.auctions[0].sold).toBe(true);
    expect(after.round.results.auctions[0].winning_team_id).toBe(student.fundId);
    // Legitimately public now — this is the reveal, and the whole point of the auction.
    expect(after.round.results.auctions[0].reserve_price).toBeGreaterThan(0);
    expect(after.round.results.standings[0].rank).toBe(1);
  });

  it("surfaces the engine's own refusal rather than guessing at legality here", async () => {
    // The engine refuses a bid the fund cannot fund. This service deliberately does not
    // pre-empt that rule, so the refusal has to reach the student legibly.
    const fixture = await playablePractice(harness, { members: [["Dana"]] });
    const student = fixture.students[0]!;
    const view = await state(student.browser, fixture.sessionId);
    const deal = (view.round.public.deals as { property_id: string }[])[0]!;

    await student.browser.post(`/v1/sessions/${fixture.sessionId}/rounds/decision`, {
      fundId: student.fundId,
      items: [{ propertyId: deal.property_id, action: "BID", bid: 900, ltv: 0.5 }],
    });
    const closed = await fixture.professor.post(
      `/v1/sessions/${fixture.sessionId}/rounds/close`,
      {},
      { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
    );
    expect(closed.status).toBe(200);
    expect(closed.body.rejected).toHaveLength(1);
    expect(closed.body.rejected[0].reason).toMatch(/insufficient equity/);

    const after = await state(student.browser, fixture.sessionId);
    expect(after.round.rejected[0].fundId).toBe(student.fundId);
  });

  it("resolves a round with no bids at all, and says nothing sold", async () => {
    const fixture = await playablePractice(harness, { members: [["Dana"]] });
    const closed = await fixture.professor.post(
      `/v1/sessions/${fixture.sessionId}/rounds/close`,
      {},
      { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
    );
    expect(closed.status).toBe(200);
    expect(closed.body.results.auctions.every((a: { sold: boolean }) => !a.sold)).toBe(true);
    expect(closed.body.submittedFunds).toBe(0);
  });
});

describe("four scored rounds", () => {
  it("opens Round 1 with fresh, writable decision state after practice", async () => {
    const fixture = await playablePractice(harness, { members: [["Dana"]] });
    const student = fixture.students[0]!;
    const practice = await state(student.browser, fixture.sessionId);
    const practiceDeals = practice.round.public.deals as { property_id: string }[];

    expect(
      (await student.browser.post(`/v1/sessions/${fixture.sessionId}/rounds/decision`, {
        fundId: student.fundId,
        items: decisionsFor(practiceDeals),
      })).status,
    ).toBe(200);
    expect(
      (await fixture.professor.post(
        `/v1/sessions/${fixture.sessionId}/rounds/close`,
        {},
        { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
      )).status,
    ).toBe(200);
    expect(
      (await fixture.professor.post(
        `/v1/sessions/${fixture.sessionId}/rounds/open`,
        {},
        { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
      )).status,
    ).toBe(200);

    const roundOne = await state(student.browser, fixture.sessionId);
    expect(roundOne.session.currentRound).toBe(0);
    expect(roundOne.session.phase).toBe("round");
    expect(roundOne.round.round).toBe(0);
    expect(roundOne.round.myDecision).toBeNull();
    expect(roundOne.round.isOpenForSubmissions).toBe(true);
    expect(roundOne.round.public.deals).not.toEqual(practiceDeals);
  });

  it("plays practice and four rounds to completion without the phase drifting", async () => {
    const fixture = await playablePractice(harness, { members: [["Dana"]] });
    const student = fixture.students[0]!;
    const professor = fixture.professor;

    const roundsSeen: number[] = [];
    const phasesSeen: string[] = [];

    for (let step = 0; step < 5; step += 1) {
      const view = await state(student.browser, fixture.sessionId);
      roundsSeen.push(view.session.currentRound);
      phasesSeen.push(view.session.phase);

      // Every fund decides on every offered property, always passing on this run so the
      // assertion is only about the machine, not about the auction.
      const deals = view.round.public.deals as { property_id: string }[];
      const submitted = await student.browser.post(
        `/v1/sessions/${fixture.sessionId}/rounds/decision`,
        { fundId: student.fundId, items: decisionsFor(deals) },
      );
      expect(submitted.status).toBe(200);

      const closed = await professor.post(
        `/v1/sessions/${fixture.sessionId}/rounds/close`,
        {},
        { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
      );
      expect(closed.status).toBe(200);

      const afterClose = await state(student.browser, fixture.sessionId);
      if (afterClose.session.gameComplete) break;
      const opened = await professor.post(
        `/v1/sessions/${fixture.sessionId}/rounds/open`,
        {},
        { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
      );
      expect(opened.status).toBe(200);
    }

    // Practice, then rounds 0..3, then complete.
    expect(roundsSeen).toEqual([-1, 0, 1, 2, 3]);
    expect(phasesSeen).toEqual(["practice", "round", "round", "round", "round"]);

    const final = await state(student.browser, fixture.sessionId);
    expect(final.session.resolvedRounds).toBe(4);
    expect(final.session.gameComplete).toBe(true);
    expect(final.session.phase).toBe("round_results");
    expect(final.session.nextStep).toMatch(/final debrief/);

    // And one more open is refused rather than looping back to round zero.
    const extra = await professor.post(
      `/v1/sessions/${fixture.sessionId}/rounds/open`,
      {},
      { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
    );
    expect(extra.status).toBeGreaterThanOrEqual(400);
  });

  it("counts practice separately from the scored rounds", async () => {
    const fixture = await playablePractice(harness, { members: [["Dana"]] });
    await fixture.professor.post(
      `/v1/sessions/${fixture.sessionId}/rounds/close`,
      {},
      { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
    );
    const view = await state(fixture.students[0]!.browser, fixture.sessionId);
    expect(view.session.resolvedRounds).toBe(0);
    expect(view.session.gameComplete).toBe(false);
  });
});

describe("the professor's grid", () => {
  it("shows who submitted and who exceeded their own policy, but never the amounts", async () => {
    // A professor's screen is routinely projected for the room. Amounts in the payload
    // would make that projection a leak, so they are simply not there.
    const fixture = await playablePractice(harness, { members: [["Dana", "Ravi"]] });
    const student = fixture.students[0]!;
    const view = await state(student.browser, fixture.sessionId);
    const deal = (view.round.public.deals as { property_id: string; max_ltv: number }[])[0]!;

    // Bid above the fund's own ceiling so the override tally has something to count.
    await student.browser.post(`/v1/sessions/${fixture.sessionId}/rounds/decision`, {
      fundId: student.fundId,
      items: [{ propertyId: deal.property_id, action: "BID", bid: 99, ltv: deal.max_ltv }],
    });

    const professorView = await state(fixture.professor, fixture.sessionId);
    expect(professorView.grid).toHaveLength(1);
    const row = professorView.grid[0];
    expect(row.submitted).toBe(true);
    expect(row.bids).toBe(1);
    expect(row.bidsAboveOwnCeiling).toBe(1);
    // The management summary is two counts and a tally of postures, never an amount,
    // so the grid stays safe to project. It is asserted here in full so a field added
    // to this row has to be considered on purpose.
    expect(row.stancesSet).toBe(0);
    expect(row.stanceTally).toEqual({});
    expect(Object.keys(row).sort()).toEqual([
      "bids",
      "bidsAboveOwnCeiling",
      "fundId",
      "fundName",
      "ltvAboveOwnTarget",
      "passes",
      "stanceTally",
      "stancesSet",
      "submitted",
      "submittedAt",
    ]);
    // Never the amount itself: check the numeric/status fields, not the raw JSON —
    // a timestamp or fundId hash can legitimately contain "99".
    for (const field of ["submittedAt", "bids", "passes", "bidsAboveOwnCeiling", "ltvAboveOwnTarget"]) {
      const value = (row as unknown as Record<string, unknown>)[field];
      if (value !== null && value !== undefined) {
        expect(String(value)).not.toBe("99");
      }
    }
    expect(JSON.stringify(professorView.grid)).not.toContain("winning_bid");
    expect(JSON.stringify(professorView.grid)).not.toContain("reserve_price");
  });

  it("is absent for a student, who sees only their own decision", async () => {
    const fixture = await playablePractice(harness, {
      fundNames: ["Value Fund", "Growth Fund"],
      members: [["Dana"], ["Ravi"]],
    });
    const dana = fixture.students[0]!;
    const ravi = fixture.students[1]!;
    const view = await state(dana.browser, fixture.sessionId);
    const deal = (view.round.public.deals as { property_id: string }[])[0]!;

    await ravi.browser.post(`/v1/sessions/${fixture.sessionId}/rounds/decision`, {
      fundId: ravi.fundId,
      items: [{ propertyId: deal.property_id, action: "BID", bid: 42, ltv: 0.5 }],
    });

    const danaView = await state(dana.browser, fixture.sessionId);
    expect(danaView.grid).toBeNull();
    // The count is shared, because "17 of 18 have submitted" is a room-wide fact.
    expect(danaView.round.submittedFunds).toBe(1);
    // The rival submitted; Dana did not. Dana's own decision must therefore still be
    // absent, which is the isolation property — a shared "somebody submitted" count
    // must never leak into "Dana submitted".
    expect(danaView.round.myDecision).toBeNull();
    // And no decision *collection* is exposed under any name.
    expect(Object.keys(danaView.round)).not.toContain("decisions");
    expect(danaView.round.results).toBeNull();
  });
});
