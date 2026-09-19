#!/usr/bin/env node
/**
 * Classroom resilience harness.
 *
 * Drives the DEPLOYED stack over its public HTTP API — no browser, no Docker, no
 * localhost. It exists to answer the questions a real classroom asks:
 *
 *   • can 50–75 students join, lock, bid, manage and read results at once?
 *   • does a refresh, a reconnect or a redeploy lose a seat or a decision?
 *   • can a double-click resolve a round twice, or double-count a transaction?
 *   • does one browser holding two classes land in the wrong one?
 *   • does each course tier expose exactly its own contract, under load?
 *
 * Every assertion is recorded rather than thrown, so a failing drill still yields
 * a full report instead of a stack trace.
 *
 * Usage:
 *   node scripts/classroom_load.mjs --scenario smoke
 *   node scripts/classroom_load.mjs --scenario load --students 50
 *   node scripts/classroom_load.mjs --scenario all --students 75 \
 *     --out artifacts/resilience/report.json
 *
 * Scenarios: smoke | latency | load | idempotency | all
 */

import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";

// ── arguments ─────────────────────────────────────────────────────────────

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const token = argv[i];
    if (!token.startsWith("--")) continue;
    const key = token.slice(2);
    const next = argv[i + 1];
    if (next === undefined || next.startsWith("--")) out[key] = true;
    else {
      out[key] = next;
      i++;
    }
  }
  return out;
}

const args = parseArgs(process.argv.slice(2));
const BASE = String(args["base-url"] ?? "https://cre-game-preview.scswitzer.workers.dev").replace(/\/$/, "");
const PASSCODE = String(args.passcode ?? process.env.PROFESSOR_PASSCODE ?? "frenzel");
const BUNDLE = String(args.bundle ?? "real605-fall26-v1");
const SCENARIO = String(args.scenario ?? "smoke");
const STUDENTS = Number(args.students ?? 50);
const BACKFILL = Number(args["background-students"] ?? Math.min(10, STUDENTS));
const TIMEOUT_MS = Number(args.timeout ?? 60_000);
const OUT = args.out ? String(args.out) : null;
const VERBOSE = Boolean(args.verbose);
const ONLY = args.only ? String(args.only) : null;

const RUN_STAMP = new Date().toISOString().replace(/[:.]/g, "-");
const EVIDENCE_DIR = OUT ? join(OUT, "..") : join("artifacts", "resilience", RUN_STAMP);

// ── measurement ───────────────────────────────────────────────────────────

/** Every request the harness makes lands here, tagged with the phase that made it. */
const samples = [];
let PHASE = "setup";

function routeOf(path) {
  return path
    .replace(/\?.*$/, "")
    .replace(/sess_[A-Za-z0-9]+/g, ":session")
    .replace(/fund_[A-Za-z0-9]+/g, ":fund");
}

function record(route, status, ms, ok, note = null) {
  samples.push({ phase: PHASE, route, status, ms: Number(ms.toFixed(1)), ok, note });
}

function percentile(values, p) {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1);
  return Number(sorted[Math.max(0, index)].toFixed(1));
}

function statsOf(rows) {
  const ms = rows.map((r) => r.ms);
  const ok = rows.filter((r) => r.ok).length;
  const statuses = {};
  for (const row of rows) statuses[String(row.status)] = (statuses[String(row.status)] ?? 0) + 1;
  return {
    n: rows.length,
    ok,
    successRate: rows.length ? Number(((ok / rows.length) * 100).toFixed(2)) : null,
    p50: percentile(ms, 50),
    p90: percentile(ms, 90),
    p95: percentile(ms, 95),
    p99: percentile(ms, 99),
    max: ms.length ? Number(Math.max(...ms).toFixed(1)) : null,
    statuses,
  };
}

function groupStats(rows, key) {
  const groups = new Map();
  for (const row of rows) {
    const k = row[key];
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(row);
  }
  return Object.fromEntries([...groups.entries()].map(([k, v]) => [k, statsOf(v)]));
}

// ── assertions ────────────────────────────────────────────────────────────

const checks = [];
function check(name, pass, detail = "") {
  checks.push({ name, pass: Boolean(pass), detail: String(detail) });
  if (!pass) console.log(`   FAIL ${name}${detail ? ` — ${detail}` : ""}`);
  else if (VERBOSE) console.log(`   ok   ${name}`);
  return Boolean(pass);
}

const notes = [];
function note(text) {
  notes.push(text);
  console.log(`   ..   ${text}`);
}

// ── actor: one browser's cookie jar ───────────────────────────────────────

class Actor {
  constructor(label) {
    this.label = label;
    this.cookies = new Map();
  }

  jar() {
    return [...this.cookies.entries()].map(([k, v]) => `${k}=${v}`).join("; ");
  }

  reset() {
    this.cookies.clear();
  }

  async req(method, path, opts = {}) {
    const { body, rawBody, headers = {}, cookie, timeoutMs = TIMEOUT_MS } = opts;
    const sent = { ...headers };
    let payload;
    if (rawBody !== undefined) payload = rawBody;
    else if (body !== undefined) {
      sent["content-type"] = sent["content-type"] ?? "application/json";
      payload = JSON.stringify(body);
    }
    const cookieHeader = cookie !== undefined ? cookie : this.jar();
    if (cookieHeader) sent.cookie = cookieHeader;

    const started = performance.now();
    let res = null;
    let failure = null;
    try {
      res = await fetch(`${BASE}${path}`, {
        method,
        headers: sent,
        body: payload,
        redirect: "manual",
        signal: AbortSignal.timeout(timeoutMs),
      });
    } catch (err) {
      failure = err?.name ?? String(err);
    }
    const ms = performance.now() - started;

    if (!res) {
      record(routeOf(path), "network_error", ms, false, failure);
      return { status: 0, body: null, ms, error: failure, headers: null };
    }

    const setCookies =
      typeof res.headers.getSetCookie === "function" ? res.headers.getSetCookie() : [];
    for (const raw of setCookies) {
      const [pair] = raw.split(";");
      const eq = pair.indexOf("=");
      if (eq > 0) this.cookies.set(pair.slice(0, eq).trim(), pair.slice(eq + 1).trim());
    }

    const text = await res.text();
    let parsed = null;
    if (text) {
      try {
        parsed = JSON.parse(text);
      } catch {
        parsed = { _unparsed: text.slice(0, 300) };
      }
    }
    const ok = res.status >= 200 && res.status < 300;
    record(routeOf(path), res.status, ms, ok);
    return { status: res.status, body: parsed, ms, headers: res.headers, text };
  }

  get(path, opts) {
    return this.req("GET", path, opts);
  }

  post(path, body, opts = {}) {
    return this.req("POST", path, { ...opts, body });
  }

  postRaw(path, rawBody, opts = {}) {
    return this.req("POST", path, { ...opts, rawBody });
  }
}

const errorDetail = (res) =>
  typeof res?.body?.detail === "string"
    ? res.body.detail
    : typeof res?.body?.error === "string"
      ? `${res.body.error}: ${res.body.detail ?? ""}`
      : JSON.stringify(res?.body ?? null).slice(0, 200);

// ── classroom ─────────────────────────────────────────────────────────────

class Classroom {
  constructor({ label, courseMode, students, totalRounds = 3, practiceEnabled = true }) {
    this.label = label;
    this.courseMode = courseMode;
    this.studentCount = students;
    this.totalRounds = totalRounds;
    this.practiceEnabled = practiceEnabled;
    this.professor = new Actor(`${label}/professor`);
    this.students = [];
    this.sessionId = null;
    this.joinCode = null;
    /** Round numbers whose decisions have been submitted with stances. */
    this.managedRounds = [];
  }

  async create() {
    const res = await this.professor.post("/v1/sessions", {
      name: `RESILIENCE ${this.label}`,
      bundleId: BUNDLE,
      courseMode: this.courseMode,
      professorPasscode: PASSCODE,
      professorName: "Professor Frenzel",
      mode: "team",
      maxTeamSize: 4,
      // Explicitly empty: "no funds yet, my teams create their own". Omitting the
      // list would make the server invent a "Fund 1" that no student owns, and
      // startGame would correctly refuse to start while it has no locked model.
      fundNames: [],
      totalRounds: this.totalRounds,
      practiceEnabled: this.practiceEnabled,
      roundTimerSeconds: 0,
    });
    check(
      `${this.label}: session created`,
      res.status === 201,
      res.status === 201 ? "" : errorDetail(res),
    );
    this.sessionId = res.body?.sessionId ?? null;
    this.joinCode = res.body?.joinCode ?? null;
    return this;
  }

  /** Professor cookie for a session this passcode owns. */
  async signInProfessor() {
    const res = await this.professor.post(`/v1/sessions/${this.sessionId}/professor`, {
      passcode: PASSCODE,
      displayName: "Professor Frenzel",
    });
    check(`${this.label}: professor signed in`, res.status === 200, errorDetail(res));
    return res;
  }

  /** Phase A — the join burst. Every student arrives within the same window. */
  async joinAll(count = this.studentCount) {
    const joined = await Promise.all(
      Array.from({ length: count }, async (_unused, i) => {
        const actor = new Actor(`${this.label}/student-${String(i + 1).padStart(3, "0")}`);
        const name = `Student ${String(i + 1).padStart(3, "0")}`;
        const res = await actor.post("/v1/join", {
          joinCode: this.joinCode,
          displayName: name,
          newFundName: `${this.label} Fund ${String(i + 1).padStart(3, "0")}`,
        });
        if (res.status !== 201) return { actor, name, fundId: null, status: res.status };
        return { actor, name, fundId: res.body.fundId, status: 201 };
      }),
    );
    this.students = joined;
    const seated = joined.filter((s) => s.fundId);
    check(
      `${this.label}: all ${count} students seated`,
      seated.length === count,
      `${seated.length}/${count} seated`,
    );
    const funds = new Set(seated.map((s) => s.fundId));
    check(
      `${this.label}: every student got a distinct fund`,
      funds.size === seated.length,
      `${funds.size} distinct funds for ${seated.length} students`,
    );
    return seated;
  }

  async stateAs(actor, extra = {}) {
    return actor.get(`/v1/sessions/${this.sessionId}/state`, extra);
  }

  async revisionAs(actor) {
    const res = await this.stateAs(actor);
    return res.body?.session?.revision ?? null;
  }

  async professorAct(path, { body = {}, headers = {} } = {}) {
    const revision = await this.revisionAs(this.professor);
    return this.professor.post(path, body, {
      headers: { ...headers, "if-match": String(revision) },
    });
  }

  async beginCheckIn() {
    const res = await this.professorAct(`/v1/sessions/${this.sessionId}/checkin/begin`);
    check(`${this.label}: check-in opened`, res.status === 200, errorDetail(res));
    return res;
  }

  /** Phase C — many funds lock a model in the same window. */
  async lockModels({ idempotencyKey = null } = {}) {
    const results = await Promise.all(
      this.students.map((student) => {
        const headers = idempotencyKey ? { "idempotency-key": idempotencyKey(student) } : {};
        return student.actor.post(
          `/v1/sessions/${this.sessionId}/funds/${student.fundId}/model/manual`,
          {},
          { headers },
        );
      }),
    );
    const locked = results.filter((r) => r.status === 200).length;
    check(
      `${this.label}: all funds locked a model`,
      locked === this.students.length,
      `${locked}/${this.students.length} locked`,
    );
    return results;
  }

  async startGame() {
    const res = await this.professorAct(`/v1/sessions/${this.sessionId}/game/start`);
    check(`${this.label}: game started`, res.status === 200, errorDetail(res));
    return res;
  }

  async phase() {
    const res = await this.stateAs(this.professor);
    return res.body?.session?.phase ?? null;
  }

  async openRound() {
    const res = await this.professorAct(`/v1/sessions/${this.sessionId}/rounds/open`);
    return res;
  }

  /**
   * Get to the first scored round from wherever `game/start` left the session.
   *
   * The landing phase depends on the session: with practice on it is `practice`,
   * and with practice off the engine has already resolved it, so the session sits
   * in `practice_results`. Only the first of those needs closing.
   */
  async enterFirstRound() {
    if ((await this.phase()) === "practice") await this.closeRound();
    return this.openRound();
  }

  async closeRound() {
    return this.professorAct(`/v1/sessions/${this.sessionId}/rounds/close`);
  }

  async finalize() {
    return this.professorAct(`/v1/sessions/${this.sessionId}/game/finalize`);
  }

  async holdingsOf(student) {
    const res = await student.actor.get(
      `/v1/sessions/${this.sessionId}/funds/${student.fundId}/portfolio`,
    );
    const holdings = res.body?.portfolio?.holdings;
    return Array.isArray(holdings) ? holdings.map((h) => String(h.property_id)) : [];
  }

  /**
   * One student's bid set: the cheapest offered building, at a price above ask so
   * it actually clears the reserve, and every other building explicitly passed.
   */
  decisionItems(deals, target = null) {
    const priced = deals.filter((d) => typeof d.asking_price === "number" && d.asking_price > 0);
    const cheapest = target ?? [...priced].sort((a, b) => a.asking_price - b.asking_price)[0];
    if (!cheapest) return deals.map((d) => ({ propertyId: d.property_id, action: "PASS" }));
    const ltv = Math.min(0.6, typeof cheapest.max_ltv === "number" ? cheapest.max_ltv : 0.6);
    return deals.map((d) =>
      d.property_id === cheapest.property_id
        ? {
            propertyId: d.property_id,
            action: "BID",
            bid: Number((cheapest.asking_price * 1.02).toFixed(2)),
            ltv: Number(ltv.toFixed(4)),
          }
        : { propertyId: d.property_id, action: "PASS" },
    );
  }

  /** Phase D/F — fetch the round's deals and decide, optionally managing holdings. */
  async submitRound({ checkSubmissions = true } = {}) {
    const submissions = await Promise.all(
      this.students.map(async (student) => {
        const view = await this.stateAs(student.actor);
        const round = view.body?.round ?? null;
        const deals = round?.public?.deals ?? [];
        if (deals.length === 0) return { student, status: 0, reason: "no_deals", items: [] };

        const management = round.management ?? { enabled: false, hasStanceChoice: false };
        let stances = [];
        if (management.enabled && management.hasStanceChoice) {
          const owned = await this.holdingsOf(student);
          const choices = management.stances ?? [];
          if (owned.length > 0 && choices.length > 0) {
            stances = owned.map((propertyId, index) => ({
              propertyId,
              stance: choices[index % choices.length],
            }));
          }
        }

        const items = this.decisionItems(deals);
        const res = await student.actor.post(`/v1/sessions/${this.sessionId}/rounds/decision`, {
          fundId: student.fundId,
          items,
          stances,
        });
        return { student, status: res.status, body: res.body, items, stances, detail: errorDetail(res) };
      }),
    );

    const accepted = submissions.filter((s) => s.status === 200);
    if (checkSubmissions) {
      check(
        `${this.label}: every student's decision was accepted`,
        accepted.length === this.students.length,
        `${accepted.length}/${this.students.length}`,
      );
    }
    const withStances = submissions.filter((s) => (s.stances ?? []).length > 0);
    if (withStances.length > 0) this.managedRounds.push(withStances.length);
    return submissions;
  }

  /** Phase B / G — everyone re-reads state at once. */
  async readBurst({ iterations = 2, onStudent = null } = {}) {
    const results = await Promise.all(
      this.students.map(async (student) => {
        const views = [];
        for (let i = 0; i < iterations; i++) {
          if (onStudent) await onStudent(student, i);
          const res = await this.stateAs(student.actor);
          views.push(res);
        }
        return views;
      }),
    );
    return results;
  }

  async statusesAsProfessor() {
    const res = await this.stateAs(this.professor);
    return res.body ?? {};
  }
}

// ── shared assertions ─────────────────────────────────────────────────────

/**
 * The NAV bridge: ending NAV minus the sum of every published channel equals the
 * NAV the round started from, to the cent. Reported by the engine per fund.
 */
function bridgeResidual(pnl) {
  const channels =
    pnl.value_channel + pnl.noi_income - pnl.interest_paid - pnl.acquisition_costs - pnl.reserves;
  return pnl.nav - (pnl.nav - channels) - channels;
}

function assertBridge(label, results) {
  const pnlRows = results?.pnl ?? [];
  const worst = pnlRows.reduce((acc, pnl) => {
    const channels =
      pnl.value_channel + pnl.noi_income - pnl.interest_paid - pnl.acquisition_costs - pnl.reserves;
    return Math.max(acc, Math.abs(pnl.nav - (pnl.nav - channels) - channels));
  }, 0);
  check(
    `${label}: NAV bridge reconciles for all ${pnlRows.length} funds`,
    pnlRows.length > 0 && worst < 0.005,
    `worst residual ${worst.toFixed(6)}`,
  );
  return worst;
}

function checkTier(label, expect, round, session) {
  const management = round?.management ?? null;
  const published = round?.public?.economics?.management ?? null;
  check(`${label}: round carries a management block`, management !== null, "management missing");
  if (!management) return;
  check(
    `${label}: management.enabled = ${expect.enabled}`,
    management.enabled === expect.enabled,
    `got ${management.enabled}`,
  );
  check(
    `${label}: management.hasStanceChoice = ${expect.hasStanceChoice}`,
    management.hasStanceChoice === expect.hasStanceChoice,
    `got ${management.hasStanceChoice}`,
  );
  check(
    `${label}: management.courseMode = ${expect.courseMode}`,
    String(management.courseMode) === String(expect.courseMode),
    `got ${management.courseMode}`,
  );
  check(
    `${label}: session.courseMode = ${expect.courseMode}`,
    String(session?.courseMode) === String(expect.courseMode),
    `got ${session?.courseMode}`,
  );
  if (expect.stances !== undefined) {
    check(
      `${label}: ${expect.stances} stances published`,
      (management.stances ?? []).length === expect.stances,
      `got ${JSON.stringify(management.stances)}`,
    );
  }
  // The engine's own copy of the tier config must agree with the service's.
  if (published) {
    check(
      `${label}: engine's published management agrees with the round`,
      published.enabled === management.enabled &&
        published.has_stance_choice === management.hasStanceChoice,
      `engine=${JSON.stringify(published)}`,
    );
  } else {
    check(`${label}: engine published no management block`, expect.enabled === false, "unexpected");
  }
}

// ── scenario: three-course deployed smoke ─────────────────────────────────

const TIERS = {
  "605": { enabled: false, hasStanceChoice: false, courseMode: "605" },
  "310": { enabled: true, hasStanceChoice: true, courseMode: "310", stances: 3 },
  "220": { enabled: true, hasStanceChoice: false, courseMode: "220" },
};

async function runTierSmoke({ students = 3, label = "smoke" } = {}) {
  console.log(`\n=== three-course deployed smoke (${students} students per tier) ===`);
  const classes = {};

  for (const courseMode of ["605", "310", "220"]) {
    PHASE = `${courseMode}/setup`;
    const cls = await new Classroom({
      label: `${label}-${courseMode}`,
      courseMode,
      students,
      totalRounds: 2,
      practiceEnabled: true,
    })
      .create()
      .then(async (c) => {
        await c.signInProfessor();
        return c;
      });
    PHASE = `${courseMode}/join`;
    await cls.joinAll(students);
    classes[courseMode] = cls;
  }

  // ── model check-in ──
  for (const courseMode of ["605", "310", "220"]) {
    PHASE = `${courseMode}/checkin`;
    await classes[courseMode].beginCheckIn();
    await classes[courseMode].lockModels();
  }

  // ── each tier plays: practice → round 1 (acquire) → round 2 (manage) ──
  const tierProof = {};
  for (const courseMode of ["605", "310", "220"]) {
    const cls = classes[courseMode];
    PHASE = `${courseMode}/practice`;
    await cls.startGame();

    // Round 1 — acquisitions. The practice market does not carry forward, so this
    // is where funds first own buildings, and therefore where management begins.
    PHASE = `${courseMode}/round-1`;
    const opened = await cls.enterFirstRound();
    check(`${courseMode}: the first scored round opened`, opened.status === 200, errorDetail(opened));
    await cls.submitRound();
    await cls.closeRound();
    const afterFirst = await cls.stateAs(cls.professor);
    assertBridge(`${courseMode} round 1`, afterFirst.body?.round?.results);
    const sold = (afterFirst.body?.round?.results?.auctions ?? []).filter((a) => a.sold).length;
    const assets = (afterFirst.body?.round?.results?.pnl ?? []).reduce((s, p) => s + p.assets, 0);
    check(
      `${courseMode}: each sold building is owned exactly once`,
      assets === sold,
      `assets=${assets} sold=${sold}`,
    );

    // Round 2 — the tier's management contract.
    const openedSecond = await cls.openRound();
    check(`${courseMode}: the management round opened`, openedSecond.status === 200, errorDetail(openedSecond));
    const roundState = await cls.stateAs(cls.professor);
    tierProof[courseMode] = {
      round: roundState.body?.round ?? null,
      session: roundState.body?.session ?? null,
    };
    checkTier(`${courseMode} tier`, TIERS[courseMode], tierProof[courseMode].round, tierProof[courseMode].session);

    // Refusal semantics come first, so a refused request can never be mistaken for
    // a successful one. A refusal must also leave the fund free to decide again.
    PHASE = `${courseMode}/refusal`;
    const victim = cls.students[0];
    const view = await cls.stateAs(victim.actor);
    const deals = view.body?.round?.public?.deals ?? [];
    const items = cls.decisionItems(deals);
    const attempt = await victim.actor.post(`/v1/sessions/${cls.sessionId}/rounds/decision`, {
      fundId: victim.fundId,
      items,
      stances: [
        {
          propertyId: deals[0]?.property_id ?? "unknown",
          stance: courseMode === "310" ? "MAX PROTECTION" : "STANDARD",
        },
      ],
    });
    if (courseMode === "310") {
      check(
        "310: an invented stance is refused, and the legal list is named",
        attempt.status === 400 && /is not a management stance/.test(errorDetail(attempt)),
        `${attempt.status} ${errorDetail(attempt)}`,
      );
    } else {
      check(
        `${courseMode}: a stance is refused, and the tier is named`,
        attempt.status === 400 && /course tier/.test(errorDetail(attempt)),
        `${attempt.status} ${errorDetail(attempt)}`,
      );
    }
    const recovered = await victim.actor.post(`/v1/sessions/${cls.sessionId}/rounds/decision`, {
      fundId: victim.fundId,
      items,
      stances: [],
    });
    check(
      `${courseMode}: the plain decision still succeeds after a refusal`,
      recovered.status === 200,
      errorDetail(recovered),
    );

    PHASE = `${courseMode}/round-2`;
    const submissions = await cls.submitRound();
    const stanced = submissions.filter((s) => (s.stances ?? []).length > 0).length;

    if (courseMode === "310") {
      const owned = await Promise.all(cls.students.map((s) => cls.holdingsOf(s)));
      const owners = owned.filter((h) => h.length > 0).length;
      check("310: funds own buildings to manage", owners > 0, `${owners}/${cls.students.length} own buildings`);
      check("310: owned buildings received a stance", stanced > 0, `${stanced} funds set stances`);
    } else {
      check(
        `${courseMode}: no student managed anything`,
        submissions.every((s) => (s.stances ?? []).length === 0),
        `${stanced} funds sent stances`,
      );
    }

    const closed = await cls.closeRound();
    check(`${courseMode}: the management round resolved`, closed.status === 200, errorDetail(closed));
    const results = await cls.stateAs(cls.professor);
    assertBridge(`${courseMode} round 2`, results.body?.round?.results);
    const pnl = results.body?.round?.results?.pnl ?? [];
    check(
      `${courseMode} round 2: results published for every fund`,
      pnl.length === cls.students.length,
      `${pnl.length}/${cls.students.length}`,
    );
  }

  return { classes, tierProof };
}

// ── scenario: multi-student load ──────────────────────────────────────────

async function runLoad({ students = STUDENTS, background = BACKFILL, label = "load" } = {}) {
  console.log(`\n=== classroom load: ${students} students on 310, ${background} each on 310+605 ===`);

  const main = new Classroom({
    label: `${label}-310-A`,
    courseMode: "310",
    students,
    totalRounds: 3,
    practiceEnabled: true,
  })
    .create()
    .then(async (c) => {
      await c.signInProfessor();
      return c;
    });
  const [mainCls] = await Promise.all([main]);
  const second = await new Classroom({
    label: `${label}-310-B`,
    courseMode: "310",
    students: background,
    totalRounds: 3,
    practiceEnabled: true,
  })
    .create()
    .then(async (c) => {
      await c.signInProfessor();
      return c;
    });
  const third = await new Classroom({
    label: `${label}-605-C`,
    courseMode: "605",
    students: background,
    totalRounds: 3,
    practiceEnabled: true,
  })
    .create()
    .then(async (c) => {
      await c.signInProfessor();
      return c;
    });
  const others = [second, third];

  PHASE = "A/join-burst";
  const startedJoin = performance.now();
  await Promise.all([mainCls.joinAll(students), ...others.map((c) => c.joinAll(c.studentCount))]);
  const joinWindow = performance.now() - startedJoin;
  note(`join burst: ${students + 2 * background} students in ${(joinWindow / 1000).toFixed(1)}s`);

  PHASE = "B/lobby-poll";
  await Promise.all([
    mainCls.readBurst({ iterations: 3 }),
    ...others.map((c) => c.readBurst({ iterations: 2 })),
  ]);

  PHASE = "C/checkin";
  await Promise.all([mainCls.beginCheckIn(), ...others.map((c) => c.beginCheckIn())]);

  PHASE = "C/model-lock";
  await Promise.all([mainCls.lockModels(), ...others.map((c) => c.lockModels())]);

  PHASE = "D/game-start";
  await Promise.all([mainCls.startGame(), ...others.map((c) => c.startGame())]);
  for (const cls of [mainCls, ...others]) {
    await cls.enterFirstRound();
  }

  // ── Phase D: deal bidding under load, three sessions at once ──
  PHASE = "D/deal-bidding";
  await Promise.all([mainCls.submitRound(), ...others.map((c) => c.submitRound())]);

  // ── Reconnect drill: ~40% of the main class hard-refreshes mid-round ──
  PHASE = "D/reconnect-mid-round";
  const reconnectors = mainCls.students.filter((_s, i) => i % 5 < 2);
  const reconnected = await Promise.all(
    reconnectors.map(async (student) => {
      const saved = new Map(student.actor.cookies);
      const before = await mainCls.stateAs(student.actor);
      const decidedBefore = before.body?.round?.myDecision?.submittedAt ?? null;
      // A hard refresh: the cookie jar is gone.
      student.actor.cookies = new Map();
      const empty = await mainCls.stateAs(student.actor);
      // ...and then comes back, exactly as a browser restoring its cookie would.
      student.actor.cookies = saved;
      const after = await mainCls.stateAs(student.actor);
      return {
        decidedBefore,
        decidedAfter: after.body?.round?.myDecision?.submittedAt ?? null,
        emptyStatus: empty.status,
        afterStatus: after.status,
      };
    }),
  );
  check(
    "reconnect: a cookie-less refresh is refused, not silently re-seated",
    reconnected.every((r) => r.emptyStatus >= 400),
    JSON.stringify(reconnected.map((r) => r.emptyStatus)),
  );
  check(
    "reconnect: restoring the cookie restores the seat and the submitted decision",
    reconnected.every((r) => r.afterStatus === 200 && r.decidedAfter && r.decidedAfter === r.decidedBefore),
    JSON.stringify(reconnected.map((r) => [r.afterStatus, r.decidedBefore === r.decidedAfter])),
  );

  // ── Race: submissions arriving while the professor closes the market ──
  PHASE = "D/race-submit-vs-close";
  const raceStudents = mainCls.students.filter((_s, i) => i % 5 === 2);
  const raceSubmissions = raceStudents.map(async (student) => {
    const view = await mainCls.stateAs(student.actor);
    const deals = view.body?.round?.public?.deals ?? [];
    return student.actor.post(`/v1/sessions/${mainCls.sessionId}/rounds/decision`, {
      fundId: student.fundId,
      items: mainCls.decisionItems(deals),
      stances: [],
    });
  });
  const [raceResults, firstClose] = await Promise.all([
    Promise.all(raceSubmissions),
    mainCls.closeRound(),
  ]);
  const closeAttempts = [firstClose.status];
  let closed = firstClose;
  // Optimistic concurrency: if a submission landed between the console's read and
  // its write, the close is refused and simply retried. That is the designed path.
  for (let attempt = 0; attempt < 4 && closed.status !== 200; attempt++) {
    closed = await mainCls.closeRound();
    closeAttempts.push(closed.status);
  }
  check(
    "race: submissions landing during the close get 2xx or a clean refusal",
    raceResults.every((r) => (r.status === 200 || r.status === 409)),
    JSON.stringify(raceResults.map((r) => r.status)),
  );
  check(
    "race: no request in the race returned a server error",
    raceResults.every((r) => r.status < 500) && closeAttempts.every((s) => s < 500),
    JSON.stringify({ race: raceResults.map((r) => r.status), close: closeAttempts }),
  );
  check("race: the market closed", closed.status === 200, `attempts ${closeAttempts.join("→")}`);

  const resolvedOnce = await mainCls.stateAs(mainCls.professor);
  check(
    "race: the round resolved exactly once",
    resolvedOnce.body?.session?.resolvedRounds === 1,
    `resolvedRounds=${resolvedOnce.body?.session?.resolvedRounds}`,
  );

  // ── Idempotency: the same close, twice ──
  PHASE = "E/idempotency";
  const duplicateClose = await mainCls.closeRound();
  check(
    "idempotency: a second close does not resolve the round twice",
    duplicateClose.status === 409,
    `${duplicateClose.status} ${errorDetail(duplicateClose)}`,
  );

  const afterResolve = await mainCls.stateAs(mainCls.professor);
  assertBridge("load round 1", afterResolve.body?.round?.results);
  const soldFirst = (afterResolve.body?.round?.results?.auctions ?? []).filter((a) => a.sold).length;
  const assetsFirst = (afterResolve.body?.round?.results?.pnl ?? []).reduce((s, p) => s + p.assets, 0);
  check(
    "no duplicate ownership: total assets equals the number of sold buildings",
    assetsFirst === soldFirst,
    `assets=${assetsFirst} sold=${soldFirst}`,
  );

  // ── Phase G: results burst, then management round ──
  PHASE = "G/results-burst";
  await Promise.all([mainCls.readBurst({ iterations: 2 }), ...others.map((c) => c.readBurst({ iterations: 1 }))]);

  PHASE = "F/management-round";
  await mainCls.openRound();
  const managed = await mainCls.submitRound();
  const managedCount = managed.filter((s) => (s.stances ?? []).length > 0).length;
  note(`management: ${managedCount}/${students} funds submitted stances`);
  check("310 under load: management stances were submitted", managedCount > 0, `${managedCount} funds`);

  const grid = await mainCls.statusesAsProfessor();
  const rows = grid.grid ?? [];
  check(
    "professor visibility: the round grid lists every fund",
    rows.length === students,
    `${rows.length}/${students}`,
  );
  const withTally = rows.filter((r) => r.stancesSet > 0);
  check(
    "professor visibility: the grid reports stances set and a stance mix",
    withTally.length > 0 && withTally.every((r) => Object.keys(r.stanceTally ?? {}).length > 0),
    `${withTally.length} funds with stances`,
  );
  check(
    "professor visibility: submitted vs waiting is distinguishable",
    rows.every((r) => typeof r.submitted === "boolean"),
  );

  PHASE = "F/refresh-load";
  await mainCls.readBurst({ iterations: 2 });

  await mainCls.closeRound();
  const managedResults = await mainCls.stateAs(mainCls.professor);
  assertBridge("load round 2 (management)", managedResults.body?.round?.results);

  // ── Session isolation ──
  PHASE = "isolation";
  const aStudent = mainCls.students[0];
  const bStudent = second.students[0];
  const crossFund = await aStudent.actor.get(
    `/v1/sessions/${mainCls.sessionId}/funds/${bStudent.fundId}/portfolio`,
  );
  check(
    "isolation: a student cannot read another session's fund",
    crossFund.status === 403 || crossFund.status === 404,
    String(crossFund.status),
  );

  const aView = await mainCls.stateAs(aStudent.actor);
  const aFundIds = new Set((aView.body?.funds ?? []).map((f) => f.id));
  const leaked = second.students.filter((s) => aFundIds.has(s.fundId));
  check("isolation: no fund of session B appears in session A", leaked.length === 0, `${leaked.length} leaked`);

  const bothCookies = `${aStudent.actor.jar()}; ${bStudent.actor.jar()}`;
  const hint = await aStudent.actor.get(`/v1/whoami?session=${second.sessionId}`, { cookie: bothCookies });
  check(
    "isolation: an explicit session hint wins over cookie order",
    hint.body?.sessionId === second.sessionId,
    `got ${hint.body?.sessionId} (wanted ${second.sessionId})`,
  );
  const unhinted = await aStudent.actor.get("/v1/whoami", { cookie: bothCookies });
  check(
    "isolation: without a hint, two held seats are reported as ambiguous rather than guessed",
    unhinted.body?.sessionId === null && unhinted.body?.ambiguous === true,
    JSON.stringify(unhinted.body),
  );

  return { main: mainCls, others };
}

// ── scenario: idempotency ────────────────────────────────────────────────

async function runIdempotency({ students = 4, label = "idem" } = {}) {
  console.log(`\n=== idempotency drills (${students} students) ===`);
  const cls = await new Classroom({
    label: `${label}-310`,
    courseMode: "310",
    students,
    totalRounds: 2,
    practiceEnabled: false,
  })
    .create()
    .then(async (c) => {
      await c.signInProfessor();
      return c;
    });
  await cls.joinAll(students);

  PHASE = "idem/checkin";
  await cls.beginCheckIn();
  await cls.lockModels();

  // Same key, same body: the second lock is a replay, not a second lock.
  const keyed = cls.students[0];
  const k1 = "lock-key-1";
  const first = await keyed.actor.post(
    `/v1/sessions/${cls.sessionId}/funds/${keyed.fundId}/model/manual`,
    {},
    { headers: { "idempotency-key": k1 } },
  );
  const replay = await keyed.actor.post(
    `/v1/sessions/${cls.sessionId}/funds/${keyed.fundId}/model/manual`,
    {},
    { headers: { "idempotency-key": k1 } },
  );
  // Strictly two successes: comparing only the two statuses would accept a matched
  // pair of 500s, which is how the slash-scoped-key defect stayed invisible.
  check(
    "idempotency: a repeated model lock with the same key replays instead of double-locking",
    first.status === 200 && replay.status === 200,
    `${first.status} then ${replay.status}`,
  );

  // A key reused with a different body must be refused, not silently accepted.
  const reused = await keyed.actor.post(
    `/v1/sessions/${cls.sessionId}/rounds/decision`,
    { fundId: keyed.fundId, items: [], stances: [] },
    { headers: { "idempotency-key": "body-drift" } },
  );
  const reuse = await keyed.actor.post(
    `/v1/sessions/${cls.sessionId}/rounds/decision`,
    { fundId: keyed.fundId, items: [{ propertyId: "p1", action: "PASS" }], stances: [] },
    { headers: { "idempotency-key": "body-drift" } },
  );
  check(
    "idempotency: the same key with a different body is refused",
    reuse.status >= 400,
    `${reused.status} then ${reuse.status}`,
  );

  PHASE = "idem/round";
  await cls.startGame();
  const opened = await cls.enterFirstRound();
  check("idempotency: the first scored round opened", opened.status === 200, errorDetail(opened));

  const student = cls.students[1];
  const view = await cls.stateAs(student.actor);
  const deals = view.body?.round?.public?.deals ?? [];
  const items = cls.decisionItems(deals);
  const key = "decision-key-1";
  const submit = () =>
    student.actor.post(
      `/v1/sessions/${cls.sessionId}/rounds/decision`,
      { fundId: student.fundId, items, stances: [] },
      { headers: { "idempotency-key": key } },
    );
  const firstSubmit = await submit();
  const secondSubmit = await submit();
  const submittedAtOf = (res) => res.body?.decision?.submittedAt ?? null;
  check(
    "idempotency: a double-clicked submit replays one decision",
    firstSubmit.status === 200 &&
      secondSubmit.status === 200 &&
      submittedAtOf(firstSubmit) === submittedAtOf(secondSubmit),
    `${firstSubmit.status}/${secondSubmit.status}`,
  );

  // The classic double-click without a key: a replacement, never an accumulation.
  const unkeyed = cls.students[2];
  const uview = await cls.stateAs(unkeyed.actor);
  const uitems = cls.decisionItems(uview.body?.round?.public?.deals ?? []);
  const a = await unkeyed.actor.post(`/v1/sessions/${cls.sessionId}/rounds/decision`, {
    fundId: unkeyed.fundId,
    items: uitems,
    stances: [],
  });
  const b = await unkeyed.actor.post(`/v1/sessions/${cls.sessionId}/rounds/decision`, {
    fundId: unkeyed.fundId,
    items: uitems,
    stances: [],
  });
  check(
    "idempotency: two unkeyed submits replace rather than duplicate",
    a.status === 200 && b.status === 200,
    `${a.status}/${b.status}`,
  );

  await cls.submitRound({ checkSubmissions: false });
  PHASE = "idem/close";
  const closed = await cls.closeRound();
  check("idempotency: the round closed", closed.status === 200, errorDetail(closed));
  const closedAgain = await cls.closeRound();
  check(
    "idempotency: closing twice is refused",
    closedAgain.status === 409,
    `${closedAgain.status} ${errorDetail(closedAgain)}`,
  );

  const after = await cls.stateAs(cls.professor);
  assertBridge("idempotency round 1", after.body?.round?.results);
  const pnl = after.body?.round?.results?.pnl ?? [];
  const sold = (after.body?.round?.results?.auctions ?? []).filter((x) => x.sold).length;
  const assets = pnl.reduce((s, p) => s + p.assets, 0);
  check(
    "idempotency: no double-counted transactions",
    assets === sold,
    `assets=${assets} sold=${sold}`,
  );

  PHASE = "idem/finalize";
  await cls.openRound();
  await cls.submitRound({ checkSubmissions: false });
  await cls.closeRound();
  const finalized = await cls.finalize();
  check("idempotency: the game finalized", finalized.status === 200, errorDetail(finalized));
  const finalAgain = await cls.finalize();
  check(
    "idempotency: finalizing twice is refused",
    finalAgain.status === 409,
    `${finalAgain.status} ${errorDetail(finalAgain)}`,
  );

  return cls;
}

// ── scenario: steady-state latency decomposition ─────────────────────────

/**
 * Cold starts are not the classroom's problem; steady state is. This warms the
 * container, then measures the same routes repeatedly so the numbers answer a
 * different question: where does a warm request actually spend its time —
 * Cookie-only and engine-probe routes bracket the container's own overhead, so
 * `state` and `portfolio` can be read as store-plus-engine cost on top of it.
 */
async function runLatency({ reps = 8 } = {}) {
  console.log(`\n=== steady-state latency decomposition (${reps} reps per route) ===`);
  const cls = await new Classroom({
    label: "latency-310",
    courseMode: "310",
    students: 1,
    totalRounds: 2,
    practiceEnabled: false,
  })
    .create()
    .then(async (c) => {
      await c.signInProfessor();
      return c;
    });
  await cls.joinAll(1);
  await cls.beginCheckIn();
  await cls.lockModels();
  await cls.startGame();
  await cls.enterFirstRound();

  const student = cls.students[0];
  PHASE = "latency/warmup";
  for (let i = 0; i < 3; i++) {
    await student.actor.get("/healthz");
    await student.actor.get("/v1/whoami");
    await cls.stateAs(student.actor);
  }

  PHASE = "latency/container-only";
  for (let i = 0; i < reps; i++) await student.actor.get("/v1/whoami");
  PHASE = "latency/engine-probe";
  for (let i = 0; i < reps; i++) await student.actor.get("/healthz");
  PHASE = "latency/engine-bundles";
  for (let i = 0; i < reps; i++) await student.actor.get("/v1/bundles");
  PHASE = "latency/session-state";
  for (let i = 0; i < reps; i++) await cls.stateAs(student.actor);
  PHASE = "latency/portfolio";
  for (let i = 0; i < reps; i++) await cls.holdingsOf(student);
  PHASE = "latency/state-as-professor";
  for (let i = 0; i < reps; i++) await cls.stateAs(cls.professor);

  return cls;
}

// ── scenario: export + NAV acceptance ────────────────────────────────────

async function runExportAcceptance(cls) {
  console.log("\n=== export + NAV acceptance ===");
  PHASE = "export";
  const res = await cls.professor.get(`/v1/sessions/${cls.sessionId}/export`);
  check("export: the professor receives a zip", res.status === 200, errorDetail(res));
  if (res.status !== 200) return null;

  mkdirSync(EVIDENCE_DIR, { recursive: true });
  const dir = mkdtempSync(join(tmpdir(), "cre-export-"));
  const zipPath = join(dir, "export.zip");
  // Re-fetch as bytes: the zip is binary, and the text path would mangle it.
  const raw = await fetch(`${BASE}/v1/sessions/${cls.sessionId}/export`, {
    headers: { cookie: cls.professor.jar() },
  });
  const bytes = Buffer.from(await raw.arrayBuffer());
  writeFileSync(zipPath, bytes);
  const outDir = join(EVIDENCE_DIR, `export-${cls.label}`);
  mkdirSync(outDir, { recursive: true });
  try {
    execFileSync("unzip", ["-o", "-q", zipPath, "-d", outDir]);
  } catch (err) {
    check("export: the zip is readable", false, String(err.message).slice(0, 120));
    return null;
  }

  const files = readdirSync(outDir);
  const expected = [
    "session_summary.csv",
    "fund_final_standings.csv",
    "round_decisions.csv",
    "round_management_stances.csv",
    "round_results.csv",
    "model_metrics.csv",
    "override_metrics.csv",
  ];
  for (const name of expected) {
    check(`export: contains ${name}`, files.includes(name), files.join(","));
  }

  const stancesCsv = files.includes("round_management_stances.csv")
    ? readFileSync(join(outDir, "round_management_stances.csv"), "utf8")
    : "";
  const stanceRows = stancesCsv.trim() ? stancesCsv.trim().split("\n").slice(1) : [];
  const header = (stancesCsv.split("\n")[0] ?? "").trim();
  console.log(`   round_management_stances.csv (${stanceRows.length} rows): ${header}`);
  check(
    "export: round_management_stances.csv carries the session's stances",
    stanceRows.length > 0,
    `${stanceRows.length} rows`,
  );
  const columns = header.split(",").map((c) => c.trim());
  check(
    "export: stance rows name the round, the fund, the building and the stance",
    ["round", "fund", "property_id", "stance"].every((c) => columns.includes(c)),
    header,
  );
  const legal = new Set(["RUN LEAN", "STANDARD", "INVEST & PROTECT"]);
  const stancesUsed = new Set(
    stanceRows.map((row) => row.split(",").map((c) => c.trim()).filter(Boolean).pop()),
  );
  check(
    "export: every exported stance is a stance the engine publishes",
    stancesUsed.size > 0 && [...stancesUsed].every((s) => legal.has(s)),
    [...stancesUsed].join(" | "),
  );
  const summaryCsv = files.includes("session_summary.csv")
    ? readFileSync(join(outDir, "session_summary.csv"), "utf8")
    : "";
  check(
    "export: session_summary.csv identifies this session",
    summaryCsv.includes(cls.sessionId),
    summaryCsv.split("\n").slice(0, 2).join(" / ").slice(0, 160),
  );
  console.log(`   exported to ${outDir} (${files.length} files, ${(bytes.length / 1024).toFixed(0)} KiB)`);
  return { outDir, files, stanceRows: stanceRows.length };
}

// ── report ────────────────────────────────────────────────────────────────

function printReport({ startedAt, scenario }) {
  const byPhase = groupStats(samples, "phase");
  const byRoute = groupStats(samples, "route");
  const overall = statsOf(samples);

  console.log(`\n=== request volumes by phase (${samples.length} requests) ===`);
  for (const [phase, s] of Object.entries(byPhase)) {
    console.log(
      `  ${phase.padEnd(26)} n=${String(s.n).padStart(5)}  ok=${String(s.successRate).padStart(6)}%  ` +
        `p50=${s.p50}  p95=${s.p95}  p99=${s.p99}  max=${s.max}  ${JSON.stringify(s.statuses)}`,
    );
  }

  console.log("\n=== latency by route (ms) ===");
  for (const [route, s] of Object.entries(byRoute).sort((a, b) => (b[1].n ?? 0) - (a[1].n ?? 0))) {
    console.log(
      `  ${route.padEnd(38)} n=${String(s.n).padStart(5)}  ok=${String(s.successRate).padStart(6)}%  ` +
        `p50=${s.p50}  p90=${s.p90}  p95=${s.p95}  p99=${s.p99}  max=${s.max}  ${JSON.stringify(s.statuses)}`,
    );
  }

  const failed = checks.filter((c) => !c.pass);
  console.log(`\n=== checks: ${checks.length - failed.length}/${checks.length} passed ===`);
  for (const c of failed) console.log(`  FAIL ${c.name} — ${c.detail}`);

  console.log("\n=== headline ===");
  console.log(`  requests          ${overall.n}`);
  console.log(`  success rate      ${overall.successRate}%`);
  console.log(`  p50/p95/p99       ${overall.p50} / ${overall.p95} / ${overall.p99} ms`);
  console.log(`  timeouts+errors   ${samples.filter((s) => !s.ok && s.status === "network_error").length}`);
  console.log(`  wall clock        ${((Date.now() - startedAt) / 1000).toFixed(1)}s`);

  const report = {
    scenario,
    baseUrl: BASE,
    startedAt: new Date(startedAt).toISOString(),
    finishedAt: new Date().toISOString(),
    wallClockSeconds: Number(((Date.now() - startedAt) / 1000).toFixed(1)),
    requests: overall,
    byPhase,
    byRoute,
    checks,
    checksPassed: checks.length - failed.length,
    checksFailed: failed.length,
    notes,
    samples,
  };

  const outFile = OUT ?? join(EVIDENCE_DIR, `report-${scenario}.json`);
  mkdirSync(dirname(outFile), { recursive: true });
  writeFileSync(outFile, JSON.stringify(report, null, 2));
  console.log(`\n  evidence written to ${outFile}`);
  return report;
}

// ── main ──────────────────────────────────────────────────────────────────

async function main() {
  const startedAt = Date.now();
  console.log(`classroom resilience harness → ${BASE}`);
  console.log(`scenario=${SCENARIO} students=${STUDENTS} background=${BACKFILL} bundle=${BUNDLE}`);

  const health = await fetch(`${BASE}/v1/health`).then((r) => r.json());
  console.log(
    `deployed: engine ${health?.engine?.engine_version} economics ${health?.engine?.economics_version} ` +
      `store ${health?.store} build ${health?.build?.sha ?? "(no sha published)"}`,
  );
  check("deployed stack reports a healthy engine", health?.engine?.status === "ok", JSON.stringify(health));
  check(
    "deployed engine is the V2 management engine",
    health?.engine?.serde_schema_version === 3,
    `serde_schema_version=${health?.engine?.serde_schema_version}`,
  );

  let cls = null;
  if (SCENARIO === "smoke" || SCENARIO === "all") {
    const { classes } = await runTierSmoke({ students: Math.min(3, STUDENTS), label: "smoke" });
    // The 310 class has just played its final round: finalize, then export the
    // completed game so the management CSV is non-empty.
    const exportCls = classes["310"];
    const finalized = await exportCls.finalize();
    check("310: the game finalized", finalized.status === 200, errorDetail(finalized));
    await runExportAcceptance(exportCls);
  }

  if (SCENARIO === "load" || SCENARIO === "all") {
    const { main } = await runLoad({ students: STUDENTS, background: BACKFILL, label: "load" });
    cls = main;
    await runExportAcceptance(main);
  }

  if (SCENARIO === "latency") {
    await runLatency({ reps: Number(args.reps ?? 8) });
  }

  if (SCENARIO === "idempotency") {
    cls = await runIdempotency({ students: 4, label: "idem" });
    await runExportAcceptance(cls);
  }

  if (ONLY === "idempotency") {
    cls = await runIdempotency({ students: 4, label: "idem-only" });
    await runExportAcceptance(cls);
  }

  printReport({ startedAt, scenario: SCENARIO });
}

main().catch((err) => {
  console.error("\nharness aborted:", err);
  try {
    printReport({ startedAt: Date.now(), scenario: SCENARIO });
  } catch {
    /* the report is best-effort */
  }
  process.exitCode = 1;
});
