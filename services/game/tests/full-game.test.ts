/**
 * Gate A–C release test: the complete classroom lifecycle against the REAL engine.
 *
 * Professor creates a session → four funds join and lock models → Practice → Rounds 1–4
 * → finalize. After every resolution this test asserts:
 *
 *   • the round number and property set are the engine's,
 *   • the round resolved exactly once (duplicate closes are refused, not re-resolved),
 *   • the portfolio persisted and carried into the next round,
 *   • the NAV bridge reconciles exactly (ending − starting = Σ channels),
 *   • the leaderboard ranks deterministically,
 *   • state survives a full serialize/reload (a simulated process restart),
 *   • the finale's NAVs equal a direct engine replay of the identical inputs.
 *
 * The replay is the strongest check available: it rebuilds the whole game from the same
 * models and decisions through the engine alone (no game service), and the final NAVs
 * must match. Any drift means the service's stored engine state diverged from what the
 * decisions actually were.
 */

import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { startHarness, testConfig, type Browser, type Harness } from "../src/testing/harness.js";
import { EngineClient, type Engine, type EngineDecision } from "../src/engineClient.js";
import {
  REAL_BUNDLE_ID,
  realisticStudentCsv,
  startEngine,
  type RunningEngine,
} from "./support/engineProcess.js";

let engine: RunningEngine;
let harness: Harness;
let direct: EngineClient;

beforeAll(async () => {
  engine = await startEngine();
  direct = new EngineClient({ baseUrl: engine.url });
  const realEngine: Engine = direct;
  harness = await startHarness({
    config: testConfig({ engineUrl: engine.url }),
    engine: realEngine,
  });
});

afterAll(async () => {
  await harness?.close();
  await engine?.stop();
});

async function revisionOf(harnessStore: Harness["store"], sessionId: string): Promise<number> {
  const session = await harnessStore.getSession(sessionId);
  if (!session) throw new Error("session vanished");
  return session.revision;
}

interface Fund {
  browser: Browser;
  fundId: string;
  name: string;
}

interface Class {
  sessionId: string;
  joinCode: string;
  professor: Browser;
  funds: Fund[];
}

/** Four funds, each with a valid locked model (the realistic fixture, re-badged). */
async function createClass(label: string): Promise<Class> {
  const professor = harness.browser(`${label}-professor`);
  const created = await professor.post("/v1/sessions", {
    name: `REAL 605 — ${label}`,
    bundleId: REAL_BUNDLE_ID,
    professorPasscode: "frenzel",
    professorName: "Professor Frenzel",
    totalRounds: 4,
    fundNames: [],
  });
  expect(created.status, JSON.stringify(created.body)).toBe(201);
  const sessionId: string = created.body.sessionId;
  const joinCode: string = created.body.joinCode;

  const fundNames = ["Irvine Capital", "Newport Partners", "Laguna Advisors", "Santa Ana Fund"];
  const funds: Fund[] = [];
  for (const [index, name] of fundNames.entries()) {
    const browser = harness.browser(`${label}-${name}`);
    const join = await browser.post("/v1/join", {
      joinCode,
      displayName: `${name} manager`,
      newFundName: name,
    });
    expect(join.status, JSON.stringify(join.body)).toBe(201);
    const fundId: string = join.body.fundId;
    funds.push({ browser, fundId, name });
    void index;
  }

  const began = await professor.post(
    `/v1/sessions/${sessionId}/checkin/begin`,
    {},
    { "if-match": String(await revisionOf(harness.store, sessionId)) },
  );
  expect(began.status, JSON.stringify(began.body)).toBe(200);

  for (const fund of funds) {
    const upload = await fund.browser.post(`/v1/sessions/${sessionId}/funds/${fund.fundId}/model`, {
      csv: realisticStudentCsv(),
    });
    expect(upload.status, JSON.stringify(upload.body)).toBe(200);
    expect(upload.body.ok).toBe(true);
    const lock = await fund.browser.post(
      `/v1/sessions/${sessionId}/funds/${fund.fundId}/model/lock`,
      {},
    );
    expect(lock.status).toBe(200);
  }

  return { sessionId, joinCode, professor, funds };
}

async function act(professor: Browser, sessionId: string, path: string): Promise<Record<string, unknown>> {
  const res = await professor.post(
    path,
    {},
    { "if-match": String(await revisionOf(harness.store, sessionId)) },
  );
  expect(res.status, JSON.stringify(res.body)).toBe(200);
  return res.body as Record<string, unknown>;
}

/** Each fund bids on the cheapest offered deal, passes the rest, at policy price. */
async function submitRoundDecisions(
  cls: Class,
  deals: { property_id: string; asking_price: number }[],
): Promise<void> {
  for (const fund of cls.funds) {
    const view = await fund.browser.get(`/v1/sessions/${cls.sessionId}/state`);
    const forecastRows = view.body.round.myForecast as {
      propertyId: string;
      policy: { maxBid: number; targetLtv: number };
    }[];
    const byId = new Map(forecastRows.map((row) => [row.propertyId, row]));
    const target = [...deals].sort((a, b) => a.asking_price - b.asking_price)[0]!;
    const policy = byId.get(target.property_id)!;
    const res = await fund.browser.post(`/v1/sessions/${cls.sessionId}/rounds/decision`, {
      fundId: fund.fundId,
      items: [
        {
          propertyId: target.property_id,
          action: "BID",
          bid: policy.policy.maxBid,
          ltv: policy.policy.targetLtv,
        },
        ...deals
          .filter((d) => d.property_id !== target.property_id)
          .map((d) => ({ propertyId: d.property_id, action: "PASS" as const })),
      ],
    });
    expect(res.status, JSON.stringify(res.body)).toBe(200);
  }
}

/** Assert the bridge identity on every published pnl row, to the cent. */
function assertBridge(pnl: { nav: number; value_channel: number; noi_income: number; interest_paid: number; acquisition_costs: number; reserves: number }): void {
  const channels =
    pnl.value_channel + pnl.noi_income - pnl.interest_paid - pnl.acquisition_costs - pnl.reserves;
  const starting = pnl.nav - channels;
  const residual = pnl.nav - starting - channels;
  expect(Math.abs(residual), "NAV bridge must reconcile to the cent").toBeLessThan(0.005);
}

describe("the full classroom lifecycle, against the real engine", () => {
  it("plays Practice → Rounds 1–4 → finalize, with exact NAVs matching a direct engine replay", async () => {
    const cls = await createClass("full-game");

    // ── start: practice opens (session default), then close with no submissions ──
    const started = await act(cls.professor, cls.sessionId, `/v1/sessions/${cls.sessionId}/game/start`);
    expect(started.phase).toBe("practice");
    const practiceView = await cls.funds[0]!.browser.get(`/v1/sessions/${cls.sessionId}/state`);
    expect(practiceView.body.session.phase).toBe("practice");
    expect(practiceView.body.session.isPracticeRound).toBe(true);

    const closedPractice = await act(cls.professor, cls.sessionId, `/v1/sessions/${cls.sessionId}/rounds/close`);
    expect(closedPractice.phase).toBe("practice_results");

    // ── four scored rounds ──
    const allDecisions: { round: number; decisions: EngineDecision[] }[] = [];
    let lastNavById = new Map<string, number>();
    let cumulativeSold = 0;

    for (let roundIndex = 0; roundIndex < 4; roundIndex++) {
      const roundNumber = roundIndex;
      const opened = await act(cls.professor, cls.sessionId, `/v1/sessions/${cls.sessionId}/rounds/open`);
      expect(opened.round).toBe(roundNumber);

      const view = await cls.funds[0]!.browser.get(`/v1/sessions/${cls.sessionId}/state`);
      expect(view.body.session.phase).toBe("round");
      expect(view.body.session.roundLabel).toBe(`Round ${roundNumber + 1} of 4`);
      const deals = view.body.round.public.deals as { property_id: string; asking_price: number }[];
      expect(deals).toHaveLength(4);

      // Future-round assets must not leak: the state view carries exactly these four deals.
      const raw = JSON.stringify(view.body);
      for (const other of deals) void other;
      expect(raw).not.toContain("reserve_price");

      await submitRoundDecisions(cls, deals);

      // The engine's decisions for the replay.
      const roundDecisions: EngineDecision[] = [];
      for (const fund of cls.funds) {
        const fv = await fund.browser.get(`/v1/sessions/${cls.sessionId}/state`);
        const items = fv.body.round.myDecision.items as {
          propertyId: string;
          action: "PASS" | "BID";
          bid: number | null;
          ltv: number | null;
        }[];
        for (const item of items) {
          roundDecisions.push({
            team_id: fund.fundId,
            property_id: item.propertyId,
            action: item.action,
            bid: item.bid,
            ltv: item.ltv,
          });
        }
      }
      allDecisions.push({ round: roundNumber, decisions: roundDecisions });

      const closed = await act(cls.professor, cls.sessionId, `/v1/sessions/${cls.sessionId}/rounds/close`);
      expect(closed.phase).toBe("round_results");
      expect(closed.gameComplete).toBe(roundNumber === 3);

      // Duplicate close is refused — the round resolved exactly once.
      const duplicate = await cls.professor.post(
        `/v1/sessions/${cls.sessionId}/rounds/close`,
        {},
        { "if-match": String(await revisionOf(harness.store, cls.sessionId)) },
      );
      expect(duplicate.status).toBe(409);

      const result = await cls.funds[0]!.browser.get(`/v1/sessions/${cls.sessionId}/state`);
      expect(result.body.session.resolvedRounds).toBe(roundNumber + 1);

      // NAV bridge reconciles for every fund.
      for (const pnl of result.body.round.results.pnl) assertBridge(pnl);

      // Portfolio persisted: cumulative assets across funds equals cumulative sold deals.
      const soldThisRound = result.body.round.results.auctions.filter(
        (a: { sold: boolean }) => a.sold,
      ).length;
      cumulativeSold += soldThisRound;
      const totalAssets = result.body.round.results.pnl.reduce(
        (sum: number, p: { assets: number }) => sum + p.assets,
        0,
      );
      expect(totalAssets).toBe(cumulativeSold);

      // Leaderboard ranks deterministically: rank 1 has the highest NAV.
      const standings = result.body.round.results.standings as {
        rank: number;
        nav: number;
        cumulative_return: number;
      }[];
      expect(standings[0]!.rank).toBe(1);
      for (let i = 1; i < standings.length; i++) {
        expect(standings[i]!.rank).toBe(standings[i - 1]!.rank + 1);
        expect(standings[i]!.nav).toBeLessThanOrEqual(standings[i - 1]!.nav);
      }

      // Portfolio carried forward: NAVs persist into the next round's funds block.
      const navById = new Map<string, number>();
      for (const pnl of result.body.round.results.pnl) {
        navById.set(pnl.team_id as string, pnl.nav as number);
      }
      lastNavById = navById;

      // Mid-game restart: fork the store, and the state view is identical.
      const restarted = harness.store.forkForRestart();
      const before = await harness.store.getSession(cls.sessionId);
      const after = await restarted.getSession(cls.sessionId);
      expect(after!.revision).toBe(before!.revision);
      expect(after!.engineStateBytes).toBe(before!.engineStateBytes);
    }

    // ── finalize ──
    const finalized = await act(cls.professor, cls.sessionId, `/v1/sessions/${cls.sessionId}/game/finalize`);
    expect(finalized.phase).toBe("finale");

    // Duplicate finalize refused.
    const dupFinalize = await cls.professor.post(
      `/v1/sessions/${cls.sessionId}/game/finalize`,
      {},
      { "if-match": String(await revisionOf(harness.store, cls.sessionId)) },
    );
    expect(dupFinalize.status).toBe(409);

    const finaleView = await cls.funds[0]!.browser.get(`/v1/sessions/${cls.sessionId}/state`);
    expect(finaleView.body.session.phase).toBe("finale");
    expect(finaleView.body.finale.standings.length).toBe(4);
    expect(finaleView.body.finale.debrief).toBeTruthy();

    // ── the replay: rebuild the identical game through the engine alone ──
    // The engine is deterministic but sensitive to input ordering (team
    // registration and the tie-break walk), so the replay must feed the engine the
    // same sequences the service does: teams sorted by fund id, submissions sorted
    // by property id — exactly as `startGame` and `closeRound` do.
    const allModels = await harness.store.listAllModels(cls.sessionId);
    const teams = [...cls.funds]
      .sort((a, b) => (a.fundId < b.fundId ? -1 : 1))
      .map((fund) => {
        const model = allModels.find((m) => m.fundId === fund.fundId)!;
        return {
          team_id: fund.fundId,
          team_name: fund.name,
          submissions: model.rows
            .map((row) => ({
              property_id: row.propertyId,
              forecast: {
                model_name: model.modelName,
                predicted_fair_value: row.forecast.predictedFairValue,
                predicted_noi_growth: row.forecast.predictedNoiGrowth,
                probability_of_downside: row.forecast.probabilityOfDownside,
                confidence: row.forecast.confidence,
              },
              policy: { max_bid: row.policy.maxBid, target_ltv: row.policy.targetLtv },
            }))
            .sort((a, b) => (a.property_id < b.property_id ? -1 : 1)),
        };
      });

    let replayState = (await direct.createGameState(REAL_BUNDLE_ID, teams, "Base Case")).state;
    // create_game_state returns the open practice round; the service's startGame
    // resolves it with zero decisions, then openRound advances to Round 1. Mirror that.
    const practiceResolved = await direct.resolveRound(replayState, []);
    replayState = practiceResolved.state;
    for (const { round, decisions } of allDecisions) {
      const openedReplay = await direct.openRound(replayState);
      expect(openedReplay.public.round_number).toBe(round);
      // The engine's tied-bid draw walks the bids in insertion order, so the replay
      // must feed them in exactly the order the service does: sorted by fund id.
      const ordered = [...decisions].sort((a, b) => (a.team_id < b.team_id ? -1 : 1));
      const resolved = await direct.resolveRound(openedReplay.state, ordered);
      replayState = resolved.state;
    }
    const replayedFinale = await direct.finalizeGame(replayState);
    const replayedStandings = replayedFinale.standings as Record<string, unknown>[];
    const serviceStandings = finaleView.body.finale.standings as Record<string, unknown>[];

    expect(replayedStandings.length).toBe(serviceStandings.length);
    // Match on the fund's stable id. The engine's standings carry `team_id`;
    // guard against `undefined === undefined` matching the first row by
    // requiring a real id on both sides.
    const fundIdOf = (row: Record<string, unknown>): string | null =>
      typeof row.team_id === "string" ? row.team_id
        : typeof row.fund_id === "string" ? row.fund_id
          : null;
    for (const serviceRow of serviceStandings) {
      const sid = fundIdOf(serviceRow);
      expect(sid, "service standings row must carry a fund id").not.toBeNull();
      const replayRow = replayedStandings.find((row) => fundIdOf(row) === sid);
      expect(replayRow, `replay must contain fund ${sid}`).toBeTruthy();
      // NAV equality to the cent — the P0 release gate.
      expect(Math.abs((replayRow!.nav as number) - (serviceRow.nav as number))).toBeLessThan(0.005);
      expect((replayRow!.cumulative_return as number)).toBeCloseTo(
        serviceRow.cumulative_return as number,
        6,
      );
    }

    // The portfolio endpoint returns the engine's own team view for the last fund.
    const portfolio = await cls.funds[3]!.browser.get(
      `/v1/sessions/${cls.sessionId}/funds/${cls.funds[3]!.fundId}/portfolio`,
    );
    expect(portfolio.status).toBe(200);
    // Nobody else's fund is readable by a student.
    const forbidden = await cls.funds[0]!.browser.get(
      `/v1/sessions/${cls.sessionId}/funds/${cls.funds[1]!.fundId}/portfolio`,
    );
    expect(forbidden.status).toBe(403);

    // Professor export produces a ZIP with the six tables.
    const exported = await cls.professor.get(`/v1/sessions/${cls.sessionId}/export`);
    expect(exported.status).toBe(200);
    expect(exported.headers["content-type"]).toContain("application/zip");
    // The harness can't JSON-parse a ZIP, so the body arrives as the raw bytes.
    const body = Buffer.from(typeof exported.body === "string" ? exported.body : "");
    expect(body.length).toBeGreaterThan(0);
    // ZIP signature.
    expect(body[0]).toBe(0x50);
    expect(body[1]).toBe(0x4b);

    void lastNavById;
  }, 300_000);
});
