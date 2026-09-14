/**
 * The Phase 1 milestone, played for real.
 *
 * The acceptance statement:
 *
 *   > Frenzel creates a class, two students join the same fund, the fund uploads its
 *   > pre-class model, Practice opens, they submit one acquisition decision, Frenzel
 *   > closes the market, the Python engine resolves it, both students see the result —
 *   > and refreshing either browser at any point changes nothing.
 *
 * Everything here talks to the **real engine over HTTP**, through the same service the
 * browser will. No shortcuts into `GameManager` and no fake results.
 *
 * One piece of the engine's behaviour is asserted rather than assumed, because it
 * changes what the demo means: **the practice round never transacts.** It reveals the
 * seller's reserve and projects what the year would have done, and then awards nothing
 * — `reason: "Practice round — no actual transactions"`. That is the right design (a
 * rehearsal must not move anyone's scoreboard), and it means a milestone that stopped
 * at practice could not show a real acquisition. So the second test plays one scored
 * round through the *same code path* — no new routes, no new state — which is what
 * proves a real transaction lands and real NAV moves.
 */

import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

import { startHarness, testConfig, type Browser, type Harness } from "../src/testing/harness.js";
import { EngineClient, type Engine } from "../src/engineClient.js";
import {
  REAL_BUNDLE_ID,
  REALISTIC_STUDENT_FIXTURE,
  realisticStudentCsv,
  startEngine,
  type RunningEngine,
} from "./support/engineProcess.js";

let engine: RunningEngine;
let harness: Harness;

beforeAll(async () => {
  engine = await startEngine();
  // The real client pointed at the real engine: the milestone must exercise the actual
  // HTTP contract, not a fake that agrees with the service by construction.
  const realEngine: Engine = new EngineClient({ baseUrl: engine.url });
  harness = await startHarness({
    config: testConfig({ engineUrl: engine.url }),
    engine: realEngine,
  });
});

afterAll(async () => {
  await harness?.close();
  await engine?.stop();
});

async function view(browser: Browser, sessionId: string) {
  const res = await browser.get(`/v1/sessions/${sessionId}/state`);
  expect(res.status, JSON.stringify(res.body)).toBe(200);
  return res.body;
}

async function revision(sessionId: string): Promise<number> {
  const session = await harness.store.getSession(sessionId);
  if (!session) throw new Error("session vanished");
  return session.revision;
}

interface Class {
  sessionId: string;
  joinCode: string;
  fundId: string;
  professor: Browser;
  dana: Browser;
  ravi: Browser;
}

/** Steps 2–6 of the milestone: a class, one fund with two students, a locked model. */
async function classWithLockedModel(label: string): Promise<Class> {
  const professor = harness.browser(`${label}-professor`);
  const created = await professor.post("/v1/sessions", {
    name: `REAL 605 — ${label}`,
    bundleId: REAL_BUNDLE_ID,
    professorPasscode: "frenzel",
    professorName: "Professor Frenzel",
    fundNames: ["Irvine Capital"],
  });
  expect(created.status, JSON.stringify(created.body)).toBe(201);
  const sessionId: string = created.body.sessionId;
  const joinCode: string = created.body.joinCode;
  expect(created.body.session.poolCount).toBe(120);

  const dana = harness.browser(`${label}-Dana`);
  const danaJoin = await dana.post("/v1/join", {
    joinCode,
    displayName: "Dana",
    newFundName: "Irvine Capital",
  });
  expect(danaJoin.status, JSON.stringify(danaJoin.body)).toBe(201);
  const fundId: string = danaJoin.body.fundId;

  const ravi = harness.browser(`${label}-Ravi`);
  const raviJoin = await ravi.post("/v1/join", { joinCode, displayName: "Ravi", fundId });
  expect(raviJoin.status).toBe(201);
  expect(raviJoin.body.fundId).toBe(fundId);

  const began = await professor.post(
    `/v1/sessions/${sessionId}/checkin/begin`,
    {},
    { "if-match": String(await revision(sessionId)) },
  );
  expect(began.status, JSON.stringify(began.body)).toBe(200);
  expect(began.body.phase).toBe("model_checkin");

  const modelUrl = `/v1/sessions/${sessionId}/funds/${fundId}/model`;
  // A wrong file is reported, not thrown: the report is the product.
  const bad = await dana.post(modelUrl, "team_id,property_id\nREAL605,Irvine\n");
  expect(bad.body.ok).toBe(false);
  expect(bad.body.report.errors.length).toBeGreaterThan(0);

  const upload = await dana.post(modelUrl, realisticStudentCsv(), {
    "idempotency-key": `${label}-v1`,
  });
  expect(upload.status, JSON.stringify(upload.body)).toBe(200);
  expect(upload.body.ok, JSON.stringify(upload.body.report.errors)).toBe(true);
  expect(upload.body.report.summary.propertiesMatched).toBe(120);
  // Descriptive, never a score.
  expect(upload.body.report.summary.scored).toBe(false);
  expect(upload.body.fund.forecastSummary.meanPredictedUpsideVsAsk).not.toBeNull();

  // Ravi sees only that the fund has validated — never what it says.
  const watched = await view(ravi, sessionId);
  expect(watched.funds[0].modelStatus).toBe("validated");
  expect(JSON.stringify(watched)).not.toContain("predicted_fair_value");

  // The lock is write-once, from either teammate.
  const lock = await ravi.post(`${modelUrl}/lock`, {});
  expect(lock.status).toBe(200);
  expect(lock.body.fund.modelStatus).toBe("locked");
  expect((await dana.post(`${modelUrl}/lock`, {})).status).toBe(409);
  expect((await dana.post(modelUrl, realisticStudentCsv())).status).toBe(409);

  return { sessionId, joinCode, fundId, professor, dana, ravi };
}

async function startPractice(cls: Class) {
  const started = await cls.professor.post(
    `/v1/sessions/${cls.sessionId}/game/start`,
    {},
    { "if-match": String(await revision(cls.sessionId)) },
  );
  expect(started.status, JSON.stringify(started.body)).toBe(200);
  expect(started.body.phase).toBe("practice");
  expect(started.body.round).toBe(-1);
  // The snapshot is real, and it is not small — which is why it is gzipped at rest.
  expect(started.body.engineStateBytes).toBeGreaterThan(50_000);
  return started.body;
}

async function closeRound(cls: Class) {
  const closed = await cls.professor.post(
    `/v1/sessions/${cls.sessionId}/rounds/close`,
    {},
    { "if-match": String(await revision(cls.sessionId)) },
  );
  expect(closed.status, JSON.stringify(closed.body)).toBe(200);
  return closed.body;
}

describe("the classroom vertical slice, against the real engine", () => {
  it("plays through the practice round, and a refresh at any point changes nothing", async () => {
    const health = await harness.browser("health").get("/v1/health");
    expect(health.status).toBe(200);
    expect(health.body.engine.game).toBe("cre-investment-committee");
    expect(health.body.engine.economics_version).toBeTruthy();
    expect(health.body.store).toBe("memory");

    const cls = await classWithLockedModel("practice");
    await startPractice(cls);

    const practice = await view(cls.dana, cls.sessionId);
    expect(practice.session.phase).toBe("practice");
    expect(practice.session.isPracticeRound).toBe(true);
    expect(practice.session.roundLabel).toBe("Practice");
    const deals = practice.round.public.deals as { property_id: string; asking_price: number }[];
    expect(deals).toHaveLength(1);

    // The fund's own forecast is visible to the fund, for the offered deal only.
    expect(practice.round.myForecast).toHaveLength(1);
    expect(practice.round.myForecast[0].propertyId).toBe(deals[0]!.property_id);
    expect(practice.round.myForecast[0].forecast.predictedFairValue).toBeGreaterThan(0);
    expect(practice.round.myForecast[0].policy.maxBid).toBeGreaterThan(0);

    // And the seller's reserve is not on the wire, for either student.
    expect(deals[0]).not.toHaveProperty("reserve_price");
    expect(JSON.stringify(practice)).not.toContain("reserve_price");
    expect(JSON.stringify(await view(cls.ravi, cls.sessionId))).not.toContain("reserve_price");

    // A refresh mid-round is byte-identical.
    expect(await view(cls.dana, cls.sessionId)).toEqual(practice);

    // They submit one acquisition decision, bidding 1.2x the asking price.
    const deal = deals[0]!;
    const bid = Math.round(deal.asking_price * 1.2 * 1e6) / 1e6;
    const submitted = await cls.dana.post(`/v1/sessions/${cls.sessionId}/rounds/decision`, {
      fundId: cls.fundId,
      items: [{ propertyId: deal.property_id, action: "BID", bid, ltv: 0.5 }],
    });
    expect(submitted.status, JSON.stringify(submitted.body)).toBe(200);

    const afterSubmit = await view(cls.ravi, cls.sessionId);
    expect(afterSubmit.round.submittedFunds).toBe(1);
    expect(afterSubmit.round.myDecision.items[0]).toMatchObject({ action: "BID", bid });
    expect(afterSubmit.round.results).toBeNull();
    expect(await view(cls.dana, cls.sessionId)).toEqual(await view(cls.dana, cls.sessionId));

    await closeRound(cls);

    const danaResults = await view(cls.dana, cls.sessionId);
    const raviResults = await view(cls.ravi, cls.sessionId);
    expect(danaResults.session.phase).toBe("practice_results");
    expect(danaResults.round.resolvedAt).toBeTruthy();
    expect(danaResults.session.nextStep).toMatch(/Round 1 next/);

    const auction = danaResults.round.results.auctions[0];
    expect(auction.property_id).toBe(deal.property_id);

    // The practice round's own semantics, asserted rather than assumed.
    expect(auction.sold).toBe(false);
    expect(auction.reason).toMatch(/Practice round/);
    expect(auction.winning_team_id).toBeNull();
    // But the market *is* revealed — the reserve and the year's outcome both appear.
    expect(auction.reserve_price).toBeGreaterThan(0);
    expect(auction.realized_value).toBeGreaterThan(0);
    expect(auction.asking_price).toBe(deal.asking_price);

    // And because nothing transacted, nobody's scoreboard moved.
    const row = danaResults.round.results.pnl.find(
      (p: { team_id: string }) => p.team_id === cls.fundId,
    );
    expect(row.assets).toBe(0);
    expect(row.nav).toBe(100);
    expect(row.acquisition_costs).toBe(0);

    // Both students in the fund see the same thing.
    expect(raviResults.round.results).toEqual(danaResults.round.results);

    // A refresh at the very end changes nothing.
    expect(await view(cls.dana, cls.sessionId)).toEqual(danaResults);
    expect(await view(cls.ravi, cls.sessionId)).toEqual(raviResults);

    // The round is closed, so a late decision is refused rather than silently dropped.
    const late = await cls.ravi.post(`/v1/sessions/${cls.sessionId}/rounds/decision`, {
      fundId: cls.fundId,
      items: [{ propertyId: deal.property_id, action: "PASS" }],
    });
    expect(late.status).toBe(409);
    expect(late.body.detail).toMatch(/market is closed/);
  });

  it("plays one scored round through the same path, and a real acquisition moves NAV", async () => {
    const cls = await classWithLockedModel("scored");
    await startPractice(cls);
    await closeRound(cls);

    const opened = await cls.professor.post(
      `/v1/sessions/${cls.sessionId}/rounds/open`,
      {},
      { "if-match": String(await revision(cls.sessionId)) },
    );
    expect(opened.status, JSON.stringify(opened.body)).toBe(200);
    expect(opened.body.round).toBe(0);

    const round = await view(cls.dana, cls.sessionId);
    expect(round.session.roundLabel).toBe("Round 1 of 4");
    expect(round.session.nextStep).toMatch(/Round 1 of 4 is open/);
    const deals = round.round.public.deals as { property_id: string; asking_price: number }[];
    expect(deals).toHaveLength(4);
    // The forecast now covers all four offered buildings — the full candidate pool is
    // still not sent, because a round is about four of them.
    expect(round.round.myForecast).toHaveLength(4);

    const target = [...deals].sort((a, b) => a.asking_price - b.asking_price)[0]!;
    const bid = Math.round(target.asking_price * 1.2 * 1e6) / 1e6;
    const submitted = await cls.dana.post(`/v1/sessions/${cls.sessionId}/rounds/decision`, {
      fundId: cls.fundId,
      items: [
        { propertyId: target.property_id, action: "BID", bid, ltv: 0.5 },
        ...deals
          .filter((d) => d.property_id !== target.property_id)
          .map((d) => ({ propertyId: d.property_id, action: "PASS" as const })),
      ],
    });
    expect(submitted.status, JSON.stringify(submitted.body)).toBe(200);

    // `closeRound` returns the response body, not the response.
    const closed = await closeRound(cls);
    expect(closed.phase).toBe("round_results");
    expect(closed.gameComplete).toBe(false);
    expect(closed.rejected).toEqual([]);

    const result = await view(cls.dana, cls.sessionId);
    const auction = result.round.results.auctions.find(
      (a: { property_id: string }) => a.property_id === target.property_id,
    );
    expect(auction.sold).toBe(true);
    expect(auction.winning_team_id).toBe(cls.fundId);
    expect(auction.winning_bid).toBe(bid);
    expect(auction.reserve_price).toBeLessThan(bid);

    // The fund now owns a building, and the five channels of the NAV identity moved.
    const row = result.round.results.pnl.find(
      (p: { team_id: string }) => p.team_id === cls.fundId,
    );
    expect(row.assets).toBe(1);
    expect(row.value_channel).not.toBe(0);
    expect(row.noi_income).toBeGreaterThan(0);
    expect(row.interest_paid).toBeGreaterThan(0);
    expect(row.acquisition_costs).toBeGreaterThan(0);
    expect(row.reserves).toBeGreaterThan(0);
    expect(row.nav).not.toBe(100);
    expect(row.gross_ltv).toBeGreaterThan(0);

    // The teaching point, visible in one number: bidding 20% over asking destroys value
    // on the day it is bought, because the price paid is already above the asset's worth.
    expect(row.value_channel).toBeLessThan(0);

    // The team view carries the fund's own book and nothing about the rival's.
    const team = await cls.dana.get(
      `/v1/sessions/${cls.sessionId}/funds/${cls.fundId}/model`,
    );
    expect(team.status).toBe(200);
    expect(team.body.model.rows).toHaveLength(120);

    // Refresh again: identical.
    expect(await view(cls.dana, cls.sessionId)).toEqual(result);

    // And the professor's grid counts the submission without exposing the amount.
    const grid = (await view(cls.professor, cls.sessionId)).grid;
    expect(grid[0].submitted).toBe(true);
    expect(grid[0].bids).toBe(1);
    expect(JSON.stringify(grid)).not.toContain(String(Math.round(bid)));
  });

  it("accepts the shipped student fixture against the real pool, and the engine agrees on the ids", async () => {
    // The gate that matters: the Node validator and the engine must agree on the same
    // file, or a fund passes check-in and is refused at "start game".
    const client = new EngineClient({ baseUrl: engine.url });
    const pool = await client.bundlePool(REAL_BUNDLE_ID);
    expect(pool.pool_count).toBe(120);
    expect(pool.candidate_pool_hash).toMatch(/^[0-9a-f]{64}$/);

    const csv = readFileSync(REALISTIC_STUDENT_FIXTURE, "utf8");
    const ids = csv
      .trim()
      .split("\n")
      .slice(1)
      .map((line) => line.split(",")[1]!);
    expect(ids).toHaveLength(120);
    expect(new Set(ids).size).toBe(120);
    expect(new Set(pool.properties.map((p) => p.property_id))).toEqual(new Set(ids));

    // The pool route exposes no reserve and no future outcome, even unnamed.
    expect(JSON.stringify(pool.properties)).not.toContain("reserve_price");
    expect(JSON.stringify(pool.properties)).not.toContain("realized_value");
  });
});
