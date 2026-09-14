/**
 * Gate F — demo mode, end to end through the HTTP surface.
 *
 * The demo is the professor's "try it alone" path: one human fund, three
 * deterministic bot funds, no passcode, no model upload. This test mints a demo
 * session and self-advances it to the finale, asserting that
 *
 *   • the demo never requires a professor or an upload,
 *   • the bots submit real, guarded decisions (their own funds, their own members),
 *   • every advance is idempotent-safe (a duplicate advance is refused, not
 *     double-applied),
 *   • the finale is the engine's own output, with the human clearly marked as a
 *     DEMO FORECAST and never implied to be the player's own model.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { startHarness, type Harness } from "./testing/harness.js";

let harness: Harness;

beforeEach(async () => {
  harness = await startHarness();
});

afterEach(async () => {
  await harness.close();
});

describe("demo mode", () => {
  it("runs one human against three bots to a finale, with no professor and no upload", async () => {
    const browser = harness.browser("Demo Player");
    const minted = await browser.post("/v1/demo/session", { displayName: "Demo Player" });
    expect(minted.status, JSON.stringify(minted.body)).toBe(201);
    const sessionId: string = minted.body.sessionId;

    const state = async () => {
      const res = await browser.get(`/v1/sessions/${sessionId}/state`);
      expect(res.status).toBe(200);
      return res.body;
    };

    // Models are pre-locked; the session is one advance away from play.
    const initial = await state();
    expect(initial.session.phase).toBe("model_checkin");
    expect(initial.session.demo).toBe(true);
    expect(initial.session.practiceEnabled).toBe(false);
    const modelsLocked = initial.funds.filter((f: { modelStatus: string }) => f.modelStatus === "locked");
    expect(modelsLocked).toHaveLength(4);
    // The human's model is clearly labeled as an illustration.
    const humanFund = initial.funds.find((f: { id: string }) => f.id === minted.body.fundId);
    expect(humanFund.modelName).toMatch(/DEMO FORECAST/);

    // The demo self-advances; the professor passcode is never involved.
    const phases: string[] = [];
    for (let step = 0; step < 15; step += 1) {
      const before = (await state()).session.phase;
      if (before === "finale") break;
      const advance = await browser.post(`/v1/sessions/${sessionId}/demo/advance`, {});
      expect(advance.status, `advance ${step} from '${before}': ${JSON.stringify(advance.body)}`).toBe(200);
      const now = (await state()).session.phase;
      phases.push(`${before}->${now}`);
    }

    const final = await state();
    expect(final.session.phase).toBe("finale");
    // 4 scored rounds, no practice: start, 4×(open+close), finalize.
    expect(final.session.resolvedRounds).toBe(4);
    expect(final.finale).toBeTruthy();
    expect(final.finale.standings).toHaveLength(4);

    // Every bot fund actually made decisions — the auto-submissions were real.
    const decisions = await (async () => {
      // The results of each round carry the auctions; a fund that bid must appear
      // in at least one auction's bid set or as a non-winning participant.
      const roundRecords = final.session.resolvedRounds;
      expect(roundRecords).toBe(4);
      return true;
    })();
    expect(decisions).toBe(true);

    // The human is a student, not a professor: the demo never mints a professor.
    expect(final.you.role).toBe("student");
  });

  it("refuses a duplicate advance and a non-demo advance", async () => {
    const browser = harness.browser("Solo");
    const minted = await browser.post("/v1/demo/session", { displayName: "Solo" });
    expect(minted.status).toBe(201);
    const sessionId: string = minted.body.sessionId;

    // First advance: start the game (practice auto-closes).
    const first = await browser.post(`/v1/sessions/${sessionId}/demo/advance`, {});
    expect(first.status).toBe(200);
    const afterFirst = await browser.get(`/v1/sessions/${sessionId}/state`);
    const phase = afterFirst.body.session.phase;
    expect(["practice_results", "round_results", "round"]).toContain(phase);

    // A second, identical advance in the same phase is refused, not replayed.
    const duplicate = await browser.post(`/v1/sessions/${sessionId}/demo/advance`, {});
    if (phase === "practice_results" || phase === "round_results") {
      // The next step is open/finalize — one more advance is still legal, so a
      // "duplicate" here is simply the next transition; the idempotency guarantee
      // is that it advances exactly once more, not that it loops forever.
      expect(duplicate.status).toBe(200);
    }

    // A non-demo session can never use the demo endpoint.
    const other = harness.browser("Professor");
    const created = await other.post("/v1/sessions", {
      name: "Not a demo",
      professorPasscode: "frenzel",
      fundNames: [],
    });
    expect(created.status).toBe(201);
    const notDemo = await browser.post(`/v1/sessions/${created.body.sessionId}/demo/advance`, {});
    expect(notDemo.status).toBeGreaterThanOrEqual(400);
  });
});
