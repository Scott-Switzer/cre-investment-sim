/**
 * Model check-in.
 *
 * The lock is the thing under test as much as the validation is. A model that can be
 * replaced after Round 1 is not a frozen forecast, and the entire teaching claim of
 * this exercise rests on the forecast being fixed before outcomes start arriving.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { startHarness, type Harness } from "./testing/harness.js";
import { FAKE_POOL } from "./testing/fakeEngine.js";
import { buildCsv, createClass, joinClass, revisionOfSession } from "./testing/scenarios.js";

let harness: Harness;

beforeEach(async () => {
  harness = await startHarness();
});

afterEach(async () => {
  await harness.close();
});

async function classAtCheckIn(options: { displayName?: string; fundNames?: string[] } = {}) {
  const fixture = await createClass(harness, {
    fundNames: options.fundNames ?? ["Value Fund"],
  });
  const student = await joinClass(harness, {
    joinCode: fixture.joinCode,
    displayName: options.displayName ?? "Dana",
    newFundName: "Value Fund",
  });
  const begin = await fixture.professor.post(
    `/v1/sessions/${fixture.sessionId}/checkin/begin`,
    {},
    { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
  );
  if (begin.status !== 200) throw new Error(JSON.stringify(begin.body));
  return { ...fixture, student, url: `/v1/sessions/${fixture.sessionId}/funds/${student.fundId}/model` };
}

describe("uploading a model", () => {
  it("validates, stores and reports without ever scoring the forecast", async () => {
    const fixture = await classAtCheckIn();
    const res = await fixture.student.browser.post(fixture.url, buildCsv());
    expect(res.status).toBe(200);
    expect(res.body.ok).toBe(true);
    expect(res.body.report.summary.scored).toBe(false);
    expect(res.body.fund.modelStatus).toBe("validated");
    expect(res.body.fund.modelRowCount).toBe(FAKE_POOL.length);
    // The default fixture file asks for 60% but is capped by each property's own
    // ceiling, so the mean is the average of the ceilings that bind.
    expect(res.body.fund.forecastSummary.meanTargetLtv).toBeCloseTo(0.575, 6);
  });

  it("returns a report rather than an error when the file is wrong, so it can be read", async () => {
    const fixture = await classAtCheckIn();
    const res = await fixture.student.browser.post(fixture.url, "nonsense,columns\n1,2\n");
    // 200 with ok:false: the report *is* the product, and burying it in an error body
    // would make the check-in screen parse prose.
    expect(res.status).toBe(200);
    expect(res.body.ok).toBe(false);
    expect(res.body.report.errors.length).toBeGreaterThan(0);
    expect(res.body.fund).toBeNull();
  });

  it("refuses a file for a different dataset, naming it exactly as the engine does", async () => {
    const fixture = await classAtCheckIn();
    const res = await fixture.student.browser.post(
      fixture.url,
      buildCsv({ pool: FAKE_POOL.filter((p) => p.property_id !== "P4") }),
    );
    expect(res.body.ok).toBe(false);
    expect(res.body.report.errors.join(" ")).toMatch(
      /This model was built for a different property dataset/,
    );
  });

  it("refuses an upload before check-in has opened, distinctly from after it has closed", async () => {
    const fixture = await createClass(harness, { fundNames: ["Value Fund"] });
    const student = await joinClass(harness, {
      joinCode: fixture.joinCode,
      displayName: "Dana",
      newFundName: "Value Fund",
    });
    const res = await student.browser.post(
      `/v1/sessions/${fixture.sessionId}/funds/${student.fundId}/model`,
      buildCsv(),
    );
    expect(res.status).toBe(409);
    expect(res.body.detail).toMatch(/has not been opened yet/);
  });

  it("refuses a student uploading for another fund", async () => {
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
    const res = await dana.browser.post(
      `/v1/sessions/${fixture.sessionId}/funds/${ravi.fundId}/model`,
      buildCsv(),
    );
    expect(res.status).toBe(403);
    expect(res.body.detail).toMatch(/only upload a model for your own fund/);
  });

  it("replaces a validated model when the fund has not locked yet", async () => {
    // Uploading, seeing the report, and correcting the file is the intended loop.
    const fixture = await classAtCheckIn();
    const first = await fixture.student.browser.post(fixture.url, buildCsv({ downside: 0.2 }));
    expect(first.body.ok).toBe(true);
    const second = await fixture.student.browser.post(fixture.url, buildCsv({ downside: 0.4 }));
    expect(second.body.ok).toBe(true);
    expect(second.body.fund.forecastSummary.meanDownsideProbability).toBeCloseTo(0.4, 6);
  });
});

describe("locking a model", () => {
  it("locks a validated model exactly once", async () => {
    const fixture = await classAtCheckIn();
    await fixture.student.browser.post(fixture.url, buildCsv());
    const lockUrl = `${fixture.url}/lock`;
    const first = await fixture.student.browser.post(lockUrl, {});
    expect(first.status).toBe(200);
    expect(first.body.fund.modelStatus).toBe("locked");
    expect(first.body.fund.modelLockedAt).toBeTruthy();

    const second = await fixture.student.browser.post(lockUrl, {});
    expect(second.status).toBe(409);
    expect(second.body.detail).toMatch(/already locked/);
  });

  it("refuses to lock before a model has been validated", async () => {
    const fixture = await classAtCheckIn();
    const res = await fixture.student.browser.post(`${fixture.url}/lock`, {});
    expect(res.status).toBe(409);
    expect(res.body.detail).toMatch(/upload your prediction file first/);
  });

  it("refuses to lock after a failed validation", async () => {
    const fixture = await classAtCheckIn();
    await fixture.student.browser.post(fixture.url, "team_id,property_id\nx,y\n");
    const res = await fixture.student.browser.post(`${fixture.url}/lock`, {});
    expect(res.status).toBe(409);
    expect(res.body.detail).toMatch(/upload your prediction file first/);
  });

  it("makes a locked model unreplaceable, which is what freezes the forecast", async () => {
    const fixture = await classAtCheckIn();
    await fixture.student.browser.post(fixture.url, buildCsv({ noiGrowth: 0.02 }));
    await fixture.student.browser.post(`${fixture.url}/lock`, {});

    // The move this exists to prevent: seeing Round 1, then re-uploading a better model.
    const better = await fixture.student.browser.post(fixture.url, buildCsv({ noiGrowth: 0.05 }));
    expect(better.status).toBe(409);
    expect(better.body.detail).toMatch(/locked its model/);

    const state = await fixture.student.browser.get(
      `/v1/sessions/${fixture.sessionId}/state`,
    );
    expect(state.body.yourFund.modelName).toBe("test_model_v1");
  });

  it("lets a teammate lock a model another teammate uploaded", async () => {
    const fixture = await classAtCheckIn();
    const ravi = await joinClass(harness, {
      joinCode: fixture.joinCode,
      displayName: "Ravi",
      fundId: fixture.student.fundId,
    });
    await fixture.student.browser.post(fixture.url, buildCsv());
    const res = await ravi.browser.post(`${fixture.url}/lock`, {});
    expect(res.status).toBe(200);
  });
});

describe("reading a model back", () => {
  it("returns a fund's own forecast to that fund", async () => {
    const fixture = await classAtCheckIn();
    await fixture.student.browser.post(fixture.url, buildCsv());
    const res = await fixture.student.browser.get(fixture.url);
    expect(res.status).toBe(200);
    expect(res.body.model.rows).toHaveLength(FAKE_POOL.length);
    expect(res.body.model.modelName).toBe("test_model_v1");
  });

  it("refuses another fund's forecast to a student", async () => {
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
    await ravi.browser.post(
      `/v1/sessions/${fixture.sessionId}/funds/${ravi.fundId}/model`,
      buildCsv({ modelName: "rival_secret_model" }),
    );

    // The rival's model is the most valuable thing on the table before Round 1.
    const res = await dana.browser.get(
      `/v1/sessions/${fixture.sessionId}/funds/${ravi.fundId}/model`,
    );
    expect(res.status).toBe(403);
    expect(JSON.stringify(res.body)).not.toContain("rival_secret_model");
  });

  it("lets the professor read any fund's forecast, which they grade from", async () => {
    const fixture = await classAtCheckIn();
    await fixture.student.browser.post(fixture.url, buildCsv());
    const res = await fixture.professor.get(fixture.url);
    expect(res.status).toBe(200);
    expect(res.body.model.rows).toHaveLength(FAKE_POOL.length);
  });
});
