/**
 * Scenarios the suites share.
 *
 * Written as the actions a person would take, in order, because the tests that
 * matter in this phase are about *sequences* — join, upload, lock, submit, close —
 * and a helper called `setupLockedGame()` would hide the sequence being tested.
 */

import type { Harness, Browser } from "./harness.js";
import { joinCodeOf } from "./harness.js";
import { FAKE_POOL } from "./fakeEngine.js";
import type { PoolProperty } from "../engineClient.js";

export const CSV_HEADER =
  "team_id,property_id,model_name,predicted_fair_value,predicted_noi_growth," +
  "probability_of_downside,max_bid,target_ltv,predicted_noi,confidence,notes";

export interface CsvOptions {
  modelName?: string;
  /** Fair value as a multiple of asking price. */
  fairValueOf?: (property: PoolProperty) => number;
  /** Max bid as a multiple of asking price. */
  maxBidOf?: (property: PoolProperty) => number;
  /** Defaults to 0.6 capped by each property's own ceiling, i.e. a *valid* file. */
  ltv?: number | ((property: PoolProperty) => number);
  teamId?: string;
  pool?: PoolProperty[];
  noiGrowth?: number;
  downside?: number;
}

/** A valid prediction CSV for the fake pool, unless an option makes it invalid. */
export function buildCsv(options: CsvOptions = {}): string {
  const pool = options.pool ?? FAKE_POOL;
  const lines = [CSV_HEADER];
  for (const property of pool) {
    const fairValue = options.fairValueOf?.(property) ?? (property.asking_price ?? 0) * 1.05;
    const maxBid = options.maxBidOf?.(property) ?? (property.asking_price ?? 0) * 0.98;
    // The default is capped by the property's own ceiling, because the point of the
    // default is a *valid* file and the ceiling is per property, not per file. An
    // explicit value is used as given — explicit means explicit, so a test can ask
    // for an over-ceiling LTV on purpose.
    const ltv =
      options.ltv === undefined
        ? Math.min(0.6, property.max_ltv ?? 0.6)
        : typeof options.ltv === "function"
          ? options.ltv(property)
          : options.ltv;
    lines.push(
      [
        options.teamId ?? "Fund 1",
        property.property_id,
        options.modelName ?? "test_model_v1",
        fairValue.toFixed(4),
        (options.noiGrowth ?? 0.025).toFixed(4),
        (options.downside ?? 0.2).toFixed(4),
        maxBid.toFixed(4),
        ltv.toFixed(4),
        "",
        "0.8",
        "",
      ].join(","),
    );
  }
  return lines.join("\n") + "\n";
}

export interface SessionFixture {
  sessionId: string;
  joinCode: string;
  professor: Browser;
  revision: number;
}

/** A professor opens a class. Nothing else has happened yet. */
export async function createClass(
  harness: Harness,
  options: {
    name?: string;
    fundNames?: string[];
    totalRounds?: number;
    maxTeamSize?: number;
  } = {},
): Promise<SessionFixture> {
  const professor = harness.browser("professor");
  const res = await professor.post("/v1/sessions", {
    name: options.name ?? "REAL 605 — Test",
    professorPasscode: "frenzel",
    professorName: "Professor Frenzel",
    fundNames: options.fundNames ?? ["Value Fund"],
    totalRounds: options.totalRounds ?? 4,
    ...(options.maxTeamSize === undefined ? {} : { maxTeamSize: options.maxTeamSize }),
  });
  if (res.status !== 201) {
    throw new Error(`could not create a session: ${res.status} ${JSON.stringify(res.body)}`);
  }
  return {
    sessionId: res.body.sessionId,
    joinCode: joinCodeOf(res.body),
    professor,
    revision: 0,
  };
}

export interface StudentFixture {
  browser: Browser;
  fundId: string;
  memberId: string;
}

/** A student joins, by code, into a named or existing fund. */
export async function joinClass(
  harness: Harness,
  options: { joinCode: string; displayName: string; fundId?: string; newFundName?: string },
): Promise<StudentFixture> {
  const browser = harness.browser(options.displayName);
  const res = await browser.post("/v1/join", {
    joinCode: options.joinCode,
    displayName: options.displayName,
    ...(options.fundId ? { fundId: options.fundId } : { newFundName: options.newFundName ?? options.displayName }),
  });
  if (res.status !== 201) {
    throw new Error(`could not join: ${res.status} ${JSON.stringify(res.body)}`);
  }
  const state = await browser.get(`/v1/sessions/${res.body.sessionId}/state`);
  return {
    browser,
    fundId: res.body.fundId,
    memberId: (state.body as { you: { memberId: string } }).you.memberId,
  };
}

export async function revisionOfSession(harness: Harness, sessionId: string): Promise<number> {
  const session = await harness.store.getSession(sessionId);
  if (!session) throw new Error(`unknown session ${sessionId}`);
  return session.revision;
}

export async function stateOf(browser: Browser, sessionId: string): Promise<any> {
  const res = await browser.get(`/v1/sessions/${sessionId}/state`);
  if (res.status !== 200) {
    throw new Error(`state failed: ${res.status} ${JSON.stringify(res.body)}`);
  }
  return res.body;
}

/**
 * Advance a session to where a practice round is open with locked models.
 *
 * `members` is **one list per fund**, because a fund is the unit that uploads a
 * model. Two students on one fund share one forecast, and the model is uploaded and
 * locked once — which is exactly the classroom shape, and the thing an earlier
 * version of this helper got wrong by locking a model per member.
 */
export async function playablePractice(
  harness: Harness,
  options: {
    fundNames?: string[];
    members?: string[][];
    totalRounds?: number;
    csv?: string;
  } = {},
): Promise<SessionFixture & { students: StudentFixture[]; fundIds: string[] }> {
  const fundNames = options.fundNames ?? ["Value Fund"];
  const members = options.members ?? [fundNames.map((_, i) => `Member ${i + 1}`)];
  const fixture = await createClass(harness, {
    fundNames,
    ...(options.totalRounds === undefined ? {} : { totalRounds: options.totalRounds }),
  });

  const students: StudentFixture[] = [];
  const fundIds: string[] = [];
  for (let fundIndex = 0; fundIndex < fundNames.length; fundIndex += 1) {
    const names = members[fundIndex] ?? [];
    let fundId: string | null = null;
    for (const displayName of names) {
      const student = await joinClass(
        harness,
        fundId
          ? { joinCode: fixture.joinCode, displayName, fundId }
          : { joinCode: fixture.joinCode, displayName, newFundName: fundNames[fundIndex]! },
      );
      fundId = student.fundId;
      students.push(student);
    }
    if (!fundId) {
      throw new Error(`fund '${fundNames[fundIndex]}' has no members to upload a model`);
    }
    fundIds.push(fundId);
  }

  const begin = await fixture.professor.post(
    `/v1/sessions/${fixture.sessionId}/checkin/begin`,
    {},
    { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
  );
  if (begin.status !== 200) throw new Error(`begin check-in failed: ${JSON.stringify(begin.body)}`);

  for (const fundId of fundIds) {
    // Submitting member of that fund, so the ownership check is exercised too.
    const member = students.find((s) => s.fundId === fundId)!;
    const upload = await member.browser.post(
      `/v1/sessions/${fixture.sessionId}/funds/${fundId}/model`,
      options.csv ?? buildCsv(),
      { "idempotency-key": `upload-${fundId}` },
    );
    if (upload.status !== 200 || upload.body.ok !== true) {
      throw new Error(`upload failed: ${JSON.stringify(upload.body)}`);
    }
    const lock = await member.browser.post(
      `/v1/sessions/${fixture.sessionId}/funds/${fundId}/model/lock`,
    );
    if (lock.status !== 200) throw new Error(`lock failed: ${JSON.stringify(lock.body)}`);
  }

  const start = await fixture.professor.post(
    `/v1/sessions/${fixture.sessionId}/game/start`,
    {},
    { "if-match": String(await revisionOfSession(harness, fixture.sessionId)) },
  );
  if (start.status !== 200) throw new Error(`start failed: ${JSON.stringify(start.body)}`);

  return { ...fixture, students, fundIds };
}
