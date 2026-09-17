/**
 * Full-classroom Playwright E2E: professor + 2 students through the complete
 * lifecycle — Practice, Rounds 1–4, final standings, and the debrief.
 *
 * KEY DESIGN:
 * - Session created via API (sets professor cookie in response)
 * - Students join through UI (set student cookies)
 * - Phase waiting uses DOM elements, NOT page.evaluate + fetch (cookies not sent)
 * - Deal count is dynamic: practice=1, scored rounds=5
 * - Students navigate directly to expected paths to avoid stale Landing redirects
 */

import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";

import type { Page, Browser } from "@playwright/test";
import { expect, test } from "@playwright/test";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "../../../..");
const ARTIFACTS = resolve(HERE, "../artifacts/full-classroom");
const STATE_PROF = resolve(HERE, ".state-prof.json");
const STATE_A = resolve(HERE, ".state-studentA.json");
const STATE_B = resolve(HERE, ".state-studentB.json");
const JOIN_CODE_PATH = resolve(HERE, ".join-code.json");
const FIXTURE_CSV = resolve(REPO, "tests/fixtures/student_submission_realistic.csv");

const PASSCODE = "frenzel";
const CLASS_NAME = `TestSession_${Date.now()}`;
const FUND_A = "Irvine Capital";
const FUND_B = "Newport Partners";
const STUDENT_A = "Dana Whitfield";
const STUDENT_B = "Ravi Mehta";
let SESSION_ID: string;

// ── Helpers ────────────────────────────────────────────────────────────────────

/**
 * Wait for a phase-specific DOM element to appear.
 * This is more reliable than page.evaluate + fetch because it doesn't depend
 * on cookie delivery (HttpOnly cookies may not be sent by fetch in Playwright).
 */
async function waitForPhaseDom(page: Page, testid: string, timeout = 60_000): Promise<void> {
  await expect(page.getByTestId(testid)).toBeVisible({ timeout });
}

async function waitForAuthoritativePhase(page: Page, phase: string, timeout = 60_000): Promise<void> {
  await expect.poll(async () => {
    return page.evaluate(async (sessionId) => {
      const response = await fetch(`/v1/sessions/${sessionId}/state`, { credentials: "include" });
      const body = await response.json();
      return `${body.session?.phase}:${body.round?.resolvedAt ?? ""}`;
    }, SESSION_ID);
  }, { timeout }).toMatch(new RegExp(`^${phase}:`));
}

async function waitForSubmittedFunds(page: Page, expected: number, timeout = 60_000): Promise<void> {
  await expect.poll(async () => {
    return page.evaluate(async (sessionId) => {
      const response = await fetch(`/v1/sessions/${sessionId}/state`, { credentials: "include" });
      const body = await response.json();
      return body.round?.submittedFunds ?? 0;
    }, SESSION_ID);
  }, { timeout }).toBeGreaterThanOrEqual(expected);
}

/**
 * Create a page with saved cookies. Navigates to the given path directly
 * (bypasses Landing redirects which use stale cached state).
 */
async function freshPage(
  browser: Browser,
  statePath: string,
  initialPath = "/",
): Promise<{ page: Page; ctx: import("@playwright/test").BrowserContext }> {
  const ctx = await browser.newContext();
  const state = JSON.parse(readFileSync(statePath, "utf-8"));
  await ctx.addCookies(state.cookies);
  const page = await ctx.newPage();
  await page.goto(initialPath);
  await page.waitForLoadState("networkidle");
  return { page, ctx };
}

// ── Tests ──────────────────────────────────────────────────────────────────────

test.describe("full classroom lifecycle", () => {
  test.beforeAll(async ({ request }) => {
    const health = await request.get("/v1/health");
    expect(health.ok()).toBeTruthy();
    const body = await health.json();
    expect(body.store).toBe("firestore");
  });
  // ═══════════════════════════════════════════════════════
  //  PHASE 1 — SESSION CREATION
  // ═══════════════════════════════════════════════════════

  test("01 — professor creates session and signs in", async ({ browser }) => {
    mkdirSync(ARTIFACTS, { recursive: true });
    const ctx = await browser.newContext();
    const res = await ctx.request.post("/v1/sessions", {
      data: { name: CLASS_NAME, professorPasscode: PASSCODE, professorName: "Professor Frenzel", fundNames: [] },
    });
    expect(res.status()).toBe(201);
    const body = await res.json();
    expect(body.session.phase).toBe("lobby");
    SESSION_ID = body.sessionId;
    writeFileSync(JOIN_CODE_PATH, JSON.stringify({ joinCode: body.joinCode }));
    await ctx.storageState({ path: STATE_PROF });
    await ctx.close();
  });

  // ═══════════════════════════════════════════════════════
  //  PHASE 2 — STUDENT JOIN & FUND CREATION
  // ═══════════════════════════════════════════════════════

  test("02 — student A joins and creates a fund", async ({ browser }) => {
    const joinCode = JSON.parse(readFileSync(JOIN_CODE_PATH, "utf-8")).joinCode;
    const ctx = await browser.newContext();
    const p = await ctx.newPage();
    await p.goto("/join");
    await p.getByLabel("Your name").fill(STUDENT_A);
    await p.getByLabel("Class code").fill(joinCode);
    await p.getByRole("button", { name: "Continue" }).click();
    await p.getByTestId("mode-create").click();
    await p.getByLabel("Fund name").fill(FUND_A);
    await p.getByTestId("fund-submit").click();
    await expect(p.getByTestId("lobby-fund-table")).toBeVisible({ timeout: 30_000 });
    await p.context().storageState({ path: STATE_A });
    await p.context().close();
  });

  test("03 — student B creates her own fund", async ({ browser }) => {
    const joinCode = JSON.parse(readFileSync(JOIN_CODE_PATH, "utf-8")).joinCode;
    const ctx = await browser.newContext();
    const p = await ctx.newPage();
    await p.goto("/join");
    await p.getByLabel("Your name").fill(STUDENT_B);
    await p.getByLabel("Class code").fill(joinCode);
    await p.getByRole("button", { name: "Continue" }).click();
    await p.getByTestId("mode-create").click();
    await p.getByLabel("Fund name").fill(FUND_B);
    await p.getByTestId("fund-submit").click();
    await expect(p.getByTestId("lobby-fund-table")).toBeVisible({ timeout: 30_000 });
    await p.context().storageState({ path: STATE_B });
    await p.context().close();
  });

  // ═══════════════════════════════════════════════════════
  //  PHASE 3 — LOBBY & MODEL CHECK-IN
  // ═══════════════════════════════════════════════════════

  test("04 — lobby shows 2 funds, check-in ready", async ({ browser }) => {
    // Verify lobby state via page.evaluate (professor has role cookie)
    const prof = await freshPage(browser, STATE_PROF, "/professor");
    const funds = await prof.page.evaluate(async (sid) => {
      try {
        const res = await fetch(`/v1/sessions/${sid}/state`);
        if (!res.ok) return -1;
        const state = await res.json();
        return state.funds?.length ?? 0;
      } catch {
        return -1;
      }
    }, SESSION_ID);
    expect(funds).toBe(2);
    await prof.ctx.close();
  });

  test("05 — professor opens check-in; both funds upload and lock", async ({ browser }) => {
    // Professor: open check-in
    const prof = await freshPage(browser, STATE_PROF, "/professor");
    await prof.page.goto("/professor");
    await expect(prof.page.getByTestId("join-code")).toBeVisible({ timeout: 15_000 });
    await prof.page.reload({ waitUntil: "networkidle" });

    // Wait for button to be enabled, then click
    await expect(prof.page.getByTestId("open-practice-checkin")).toBeEnabled({ timeout: 30_000 });
    await prof.page.getByTestId("open-practice-checkin").click();

    // Wait for phase-specific DOM elements instead of page.evaluate + fetch
    await waitForPhaseDom(prof.page, "kpi-models", 60_000);
    await expect(prof.page.getByTestId("kpi-students")).toContainText("2");

    // Student A: upload & lock model via /model
    const pa = await freshPage(browser, STATE_A, "/model");
    await pa.page.goto("/model");
    await expect(pa.page.getByTestId("upload-model")).toBeVisible({ timeout: 30_000 });
    await pa.page.setInputFiles("input[type=file]", FIXTURE_CSV);
    await expect(pa.page.getByTestId("matched-count")).toBeVisible({ timeout: 30_000 });
    await pa.page.getByTestId("lock-model").click();
    await expect(pa.page.getByTestId("model-locked-banner")).toBeVisible({ timeout: 30_000 });

    // Student B: upload & lock model
    const pb = await freshPage(browser, STATE_B, "/model");
    await pb.page.goto("/model");
    await expect(pb.page.getByTestId("upload-model")).toBeVisible({ timeout: 30_000 });
    await pb.page.setInputFiles("input[type=file]", FIXTURE_CSV);
    await expect(pb.page.getByTestId("matched-count")).toBeVisible({ timeout: 30_000 });
    await pb.page.getByTestId("lock-model").click();
    await expect(pb.page.getByTestId("model-locked-banner")).toBeVisible({ timeout: 30_000 });

    // Professor: close check-in and open practice
    await prof.page.getByTestId("open-practice").click();
    await waitForPhaseDom(prof.page, "kpi-practice", 60_000);
    await expect(prof.page.getByTestId("kpi-practice")).toBeVisible({ timeout: 30_000 });

    await prof.ctx.close();
    await pa.ctx.close();
    await pb.ctx.close();
  });

  // ═══════════════════════════════════════════════════════
  //  PHASE 4 — PRACTICE
  // ═══════════════════════════════════════════════════════

  test("06 — professor opens practice; A bids; B passes", async ({ browser }) => {
    // Navigate directly to /game/practice to bypass stale Landing redirects
    const pa = await freshPage(browser, STATE_A, "/game/practice");
    await pa.page.goto("/game/practice");
    await expect(pa.page.getByTestId("deal-board")).toBeVisible({ timeout: 30_000 });

    const pb = await freshPage(browser, STATE_B, "/game/practice");
    await pb.page.goto("/game/practice");
    await expect(pb.page.getByTestId("deal-board")).toBeVisible({ timeout: 30_000 });

    // Practice has 1 deal (not 5 like scored rounds)
    const cardsA = pa.page.locator("[data-testid^='deal-card-']");
    const dealCount = await cardsA.count();
    console.log(`[Test 06] Practice deals: ${dealCount}`);

    // Student A: bid on deal 0, pass on rest
    for (let i = 0; i < dealCount; i++) {
      const cardId = await cardsA.nth(i).getAttribute("data-testid") || "";
      const pid = cardId.replace(/^deal-card-/, "");
      if (i === 0) {
        await pa.page.getByTestId(`bid-${pid}`).click();
      } else {
        await pa.page.getByTestId(`pass-${pid}`).click();
      }
    }
    // Student B: pass on all deals
    const cardsB = pb.page.locator("[data-testid^='deal-card-']");
    const dealCountB = await cardsB.count();
    for (let i = 0; i < dealCountB; i++) {
      const cardId = await cardsB.nth(i).getAttribute("data-testid") || "";
      const pid = cardId.replace(/^deal-card-/, "");
      await pb.page.getByTestId(`pass-${pid}`).click();
    }

    // Submit via ReviewModal (each student submits on their own page)
    await pa.page.getByTestId("review-submit").click();
    await expect(pa.page.getByTestId("lock-decisions")).toBeVisible({ timeout: 15_000 });
    await pa.page.getByTestId("lock-decisions").click();

    await pb.page.getByTestId("review-submit").click();
    await expect(pb.page.getByTestId("lock-decisions")).toBeVisible({ timeout: 15_000 });
    await pb.page.getByTestId("lock-decisions").click();

    // Professor: close practice
    const prof = await freshPage(browser, STATE_PROF, "/professor");
    await prof.page.goto("/professor");
    const practiceStateRequestsA: string[] = [];
    const practiceEventsA: string[] = [];
    pa.page.on("request", (request) => {
      if (request.url().includes(`/v1/sessions/${SESSION_ID}/state`)) practiceStateRequestsA.push(request.url());
    });
    pa.page.on("response", (response) => {
      if (response.url().includes(`/v1/sessions/${SESSION_ID}/events`)) practiceEventsA.push(String(response.status()));
    });
    await waitForSubmittedFunds(prof.page, 2);
    await expect(prof.page.getByTestId("close-practice")).toBeVisible({ timeout: 30_000 });
    await prof.page.getByTestId("close-practice").click();
    await expect(prof.page.getByTestId("kpi-practice")).toContainText("2", { timeout: 60_000 });
    await waitForAuthoritativePhase(pa.page, "practice_results");

    // Students: view results
    await pa.page.goto("/game/results");
    await pb.page.goto("/game/results");
    const authoritative = await pa.page.evaluate(async (sessionId) => {
      const response = await fetch(`/v1/sessions/${sessionId}/state`, { credentials: "include" });
      const body = await response.json();
      return {
        route: window.location.pathname,
        ui: document.body.innerText.slice(0, 400),
        status: response.status,
        phase: body.session?.phase,
        currentRound: body.session?.currentRound,
        revision: body.session?.revision,
        round: body.round?.round,
        closedAt: body.round?.closedAt,
        resolvedAt: body.round?.resolvedAt,
        myDecision: body.round?.myDecision,
      };
    }, SESSION_ID);
    console.log(`[Test 06] practice convergence ${JSON.stringify({ authoritative, stateRequests: practiceStateRequestsA.length, events: practiceEventsA.length })}`);
    await expect(pa.page.getByTestId("practice-not-booked")).toBeVisible({ timeout: 30_000 });

    await prof.ctx.close();
    await pa.ctx.close();
    await pb.ctx.close();
  });

  // ═══════════════════════════════════════════════════════
  //  PHASE 5 — ROUNDS 1–4
  // ═══════════════════════════════════════════════════════

  test("07 — rounds 1–4 complete with portfolio persistence", async ({ browser }) => {
    async function playRound(roundNum: number) {
      // Professor: open next round
      const prof = await freshPage(browser, STATE_PROF, "/professor");
      await prof.page.goto("/professor");
      await expect(prof.page.getByTestId("open-next-round")).toBeVisible({ timeout: 30_000 });
      await prof.page.getByTestId("open-next-round").click();
      await expect(prof.page.getByTestId("close-practice")).toBeEnabled({ timeout: 60_000 });

      // Students: navigate directly to /game/practice
      const pa = await freshPage(browser, STATE_A, "/game/practice");
      const stateRequestsA: string[] = [];
      const sseResponsesA: string[] = [];
      pa.page.on("request", (request) => {
        if (request.url().includes(`/v1/sessions/${SESSION_ID}/state`)) stateRequestsA.push(request.url());
      });
      pa.page.on("response", (response) => {
        if (response.url().includes(`/v1/sessions/${SESSION_ID}/events`)) sseResponsesA.push(response.status().toString());
      });
      await pa.page.goto("/game/practice");
      await expect(pa.page.getByTestId("deal-board")).toBeVisible({ timeout: 30_000 });

      async function captureStudentState(label: string) {
        const captured = await pa.page.evaluate(async (sessionId) => {
          const response = await fetch(`/v1/sessions/${sessionId}/state`, { credentials: "include" });
          const body = await response.json();
          return { status: response.status, body };
        }, SESSION_ID);
        const ui = await pa.page.locator("body").innerText();
        console.log(`[Round ${roundNum}] ${label} route=${pa.page.url()}`);
        console.log(`[Round ${roundNum}] ${label} UI=${ui.match(/Round [^\n]+|deals reviewed|decisions locked|open for decisions/g)?.join(" | ") ?? ""}`);
        console.log(`[Round ${roundNum}] ${label} STATE=${JSON.stringify({
          status: captured.status,
          phase: captured.body.session?.phase,
          currentRound: captured.body.session?.currentRound,
          revision: captured.body.session?.revision,
          round: captured.body.round && {
            round: captured.body.round.round,
            roundLabel: captured.body.round.roundLabel,
            openedAt: captured.body.round.openedAt,
            closedAt: captured.body.round.closedAt,
            resolvedAt: captured.body.round.resolvedAt,
            isOpenForSubmissions: captured.body.round.isOpenForSubmissions,
            myDecision: captured.body.round.myDecision,
            deals: captured.body.round.public?.deals?.map((deal: { property_id: string }) => deal.property_id),
          },
        })}`);
        console.log(`[Round ${roundNum}] ${label} stateRequests=${stateRequestsA.length} sseResponses=${sseResponsesA.length}`);
        return captured;
      }
      await captureStudentState("BEFORE_RELOAD");
      await pa.page.reload({ waitUntil: "networkidle" });
      await captureStudentState("AFTER_RELOAD");

      const pb = await freshPage(browser, STATE_B, "/game/practice");
      await pb.page.goto("/game/practice");
      await expect(pb.page.getByTestId("deal-board")).toBeVisible({ timeout: 30_000 });

      // Submit decisions on all deals (dynamic count)
      const cardsA = pa.page.locator("[data-testid^='deal-card-']");
      const countA = await cardsA.count();
      console.log(`[Round ${roundNum}] Deals: ${countA}`);

      for (let i = 0; i < countA; i++) {
        const cardId = await cardsA.nth(i).getAttribute("data-testid") || "";
        const pid = cardId.replace(/^deal-card-/, "");
        if (i === 0) {
          await pa.page.getByTestId(`bid-${pid}`).click();
        } else {
          await pb.page.getByTestId(`pass-${pid}`).click();
        }
      }

      // Submit via ReviewModal
      await pa.page.getByTestId("review-submit").click();
      await expect(pa.page.getByTestId("lock-decisions")).toBeVisible({ timeout: 15_000 });
      await pa.page.getByTestId("lock-decisions").click();

      await pb.page.getByTestId("review-submit").click();
      await expect(pb.page.getByTestId("lock-decisions")).toBeVisible({ timeout: 15_000 });
      await pb.page.getByTestId("lock-decisions").click();

      // Professor: close round
      await prof.page.goto("/professor");
      await waitForSubmittedFunds(prof.page, 2);
      await expect(prof.page.getByTestId("close-practice")).toBeVisible({ timeout: 30_000 });
      await prof.page.getByTestId("close-practice").click();
      await waitForAuthoritativePhase(pa.page, "round_results");

      // Students: view results
      await pa.page.goto("/game/results");
      await pb.page.goto("/game/results");
      await expect(pa.page.getByTestId("nav-bridge")).toBeVisible({ timeout: 30_000 });
      await expect(pa.page.getByTestId("game-leaderboard")).toBeVisible({ timeout: 30_000 });

      await prof.ctx.close();
      await pa.ctx.close();
      await pb.ctx.close();
    }

    for (let i = 1; i <= 4; i++) {
      await playRound(i);
    }
  });

  // ═══════════════════════════════════════════════════════
  //  PHASE 6 — FINAL STANDINGS & DEBRIEF
  // ═══════════════════════════════════════════════════════

  test("08 — leaderboard shows standings after round 4", async ({ browser }) => {
    const pa = await freshPage(browser, STATE_A, "/game/results");
    await pa.page.goto("/game/results");
    await expect(pa.page.getByTestId("game-leaderboard")).toBeVisible({ timeout: 30_000 });
    await pa.ctx.close();
  });

  test("09 — professor finalizes; finale shows standings, analytics, debrief", async ({ browser }) => {
    const prof = await freshPage(browser, STATE_PROF, "/professor");
    await prof.page.goto("/professor");
    await expect(prof.page.getByTestId("finalize-game")).toBeVisible({ timeout: 30_000 });
    await prof.page.getByTestId("finalize-game").click();

    // Student A: navigate to finale
    const pa = await freshPage(browser, STATE_A, "/game/finale");
    await pa.page.goto("/game/finale");
    await expect(pa.page.getByTestId("finale-standings")).toBeVisible({ timeout: 30_000 });
    await expect(pa.page.getByTestId("finale-analytics")).toBeVisible({ timeout: 30_000 });
    await expect(pa.page.getByTestId("game-winner")).toBeVisible({ timeout: 30_000 });
    await expect(pa.page.getByTestId("finale-answers")).toBeVisible({ timeout: 30_000 });

    await prof.ctx.close();
    await pa.ctx.close();
  });

  // ═══════════════════════════════════════════════════════
  //  PHASE 7 — EXPORT
  // ═══════════════════════════════════════════════════════

  test("10 — professor exports session ZIP with clean CSVs", async ({ browser }) => {
    const prof = await freshPage(browser, STATE_PROF, "/professor");
    await prof.page.goto("/professor");
    await expect(prof.page.getByTestId("export-session")).toBeVisible({ timeout: 30_000 });

    const [download] = await Promise.all([
      prof.page.waitForEvent("download"),
      prof.page.getByTestId("export-session").click(),
    ]);
    const path = await download.path();
    expect(path).toBeTruthy();
    const zipContent = readFileSync(path!);
    expect(zipContent.length).toBeGreaterThan(1000);
    await prof.ctx.close();
  });

  // ═══════════════════════════════════════════════════════
  //  PHASE 8 — BIGSCREEN VIEW
  // ═══════════════════════════════════════════════════════

  test("11 — bigscreen shows read-only game view", async ({ browser }) => {
    const pa = await freshPage(browser, STATE_PROF, "/bigscreen");
    await pa.page.goto("/bigscreen");
    await expect(pa.page.getByTestId("bigscreen")).toBeVisible({ timeout: 30_000 });
    await pa.ctx.close();
  });

  // ═══════════════════════════════════════════════════════
  //  PHASE 9 — DEMO MODE
  // ═══════════════════════════════════════════════════════

  test("12 — demo mode creates session and starts practice", async ({ browser }) => {
    const ctx = await browser.newContext();
    const p = await ctx.newPage();
    await p.goto("/");
    await p.getByTestId("try-demo").click();
    await expect(p.getByTestId("practice-not-booked")).toBeVisible({ timeout: 30_000 });
    await ctx.close();
  });
});
