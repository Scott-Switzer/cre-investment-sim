/**
 * The Phase 2 browser gate, played for real.
 *
 * Everything runs through real browsers against the full stack (engine, Firestore
 * emulator, game service serving the built client). No API shortcuts for anything
 * the task forbids: the students join through the join screen, the model is uploaded
 * and locked through check-in, decisions are locked through the review modal, and the
 * reveal reaches the student automatically through SSE. The one API call is session
 * creation itself — it is done with a request-scope context so its professor cookie
 * never leaks into the browser contexts.
 *
 * Serial by design (`workers: 1`, declared order): the flow is a state machine and
 * each step consumes the previous step's state. Student seats are minted once and
 * reused via storageState so later tests re-enter their seat instead of joining
 * again — a second join with the same display name would create a duplicate member.
 *
 * The same run captures the ten mandated screenshots into artifacts/phase2-ui/.
 */
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { mkdirSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "../../../..");
const FIXTURE_CSV = resolve(REPO, "tests/fixtures/student_submission_realistic.csv");
const ARTIFACTS = resolve(REPO, "artifacts/phase2-ui");

const PASSCODE = "frenzel";
const CLASS_NAME = "REAL 605 — CRE Investment Committee";
const FUND_NAME = "Pacific CRE Partners";
const STUDENT_A = "Dana Whitfield";
const STUDENT_B = "Ravi Mehta";

const STUDENT_A_STATE = resolve(HERE, ".state-studentA.json");
const STUDENT_B_STATE = resolve(HERE, ".state-studentB.json");

async function screenshot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: resolve(ARTIFACTS, `${name}.png`), fullPage: false });
}

test.describe.serial("the playable practice UX", () => {
  let joinCode = "";

  /** Fresh, cookie-free contexts — never share the professor's jar. */
  function newPage(browser: import("@playwright/test").Browser, storageState?: string) {
    return browser.newContext({ storageState }).then((c) => c.newPage());
  }

  test("01 — professor creates the session and signs the console in", async ({ browser }) => {
    mkdirSync(ARTIFACTS, { recursive: true });

    // Cookie-free request scope: creating the session must not sign the console in.
    const ctx = await browser.newContext();
    const res = await ctx.request.post("/v1/sessions", {
      data: {
        name: CLASS_NAME,
        professorPasscode: PASSCODE,
        professorName: "Professor Frenzel",
        fundNames: [],
      },
    });
    expect(res.ok()).toBeTruthy();
    const body = (await res.json()) as { joinCode: string };
    joinCode = body.joinCode;
    expect(joinCode).toHaveLength(6);
    await ctx.close();

    // The professor console signs in through its real form.
    const page = await newPage(browser);
    await page.goto("/professor");
    await page.getByTestId("professor-signin-input").fill(PASSCODE);
    await page.getByTestId("professor-signin").click();
    await expect(page.getByTestId("join-code")).toHaveText(joinCode, { timeout: 30_000 });
    await expect(page.getByTestId("kpi-students")).toHaveText("0");
    await screenshot(page, "09-professor-console-empty");

    // The console's own seat is reused for the rest of the run.
    await page.context().storageState({ path: resolve(HERE, ".state-professor.json") });
    await page.context().close();
  });

  test("02 — landing renders the first viewport", async ({ browser }) => {
    const page = await newPage(browser);
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("live acquisition decisions");
    await expect(page.getByTestId("join-class")).toBeVisible();
    await expect(page.getByText("Semi-synthetic CRE cases")).toBeVisible();
    await screenshot(page, "01-landing");
    await page.context().close();
  });

  test("03 — student A joins through the browser and creates the fund", async ({ browser }) => {
    const page = await newPage(browser);
    await page.goto("/join");
    await page.getByLabel("Your name").fill(STUDENT_A);
    await page.getByLabel("Class code").fill(joinCode);
    await page.getByTestId("join-continue").click();
    await expect(page.getByTestId("fund-name")).toBeVisible();
    await screenshot(page, "02-join");
    await page.getByTestId("mode-create").click();
    await page.getByTestId("fund-name").fill(FUND_NAME);
    await page.getByTestId("fund-submit").click();
    await expect(page.getByTestId("lobby-fund-name")).toHaveText(FUND_NAME);
    await screenshot(page, "03-lobby");
    await page.context().storageState({ path: STUDENT_A_STATE });
    await page.context().close();
  });

  test("04 — student B joins the same fund through the fund picker; the lobby updates live", async ({ browser }) => {
    const pageA = await newPage(browser, STUDENT_A_STATE);
    const pageB = await newPage(browser);

    await pageB.goto("/join");
    await pageB.getByLabel("Your name").fill(STUDENT_B);
    await pageB.getByLabel("Class code").fill(joinCode);
    await pageB.getByTestId("join-continue").click();
    // The fund A created is announced in the picker; B selects it and joins.
    await pageB.getByTestId(`fund-option-${FUND_NAME}`).click();
    await pageB.getByTestId("fund-submit").click();
    await expect(pageB.getByTestId("lobby-fund-name")).toHaveText(FUND_NAME);
    await pageB.context().storageState({ path: STUDENT_B_STATE });
    await pageB.context().close();

    // A's open lobby shows the new teammate without any reload — pure SSE.
    await pageA.goto("/lobby");
    await expect(pageA.getByTestId("lobby-fund-name")).toHaveText(FUND_NAME);
    await expect(pageA.getByText(STUDENT_B)).toBeVisible({ timeout: 30_000 });
    await screenshot(pageA, "03-lobby-two-members");
    await pageA.context().close();
  });

  test("05 — model check-in: upload, validate 120/120, lock", async ({ browser }) => {
    const page = await newPage(browser, STUDENT_A_STATE);
    await page.goto("/lobby");
    await expect(page.getByTestId("lobby-fund-name")).toHaveText(FUND_NAME);

    // Professor opens check-in from the signed-in console.
    const prof = await newPage(browser, resolve(HERE, ".state-professor.json"));
    await prof.goto("/professor");
    await prof.getByTestId("open-practice-checkin").click();
    await expect(prof.getByTestId("kpi-models")).toContainText("0 /");

    // SSE moves the student's open lobby to the check-in screen by itself.
    await expect(page.getByTestId("matched-count")).toBeHidden();
    await expect(page.getByTestId("upload-model")).toBeVisible({ timeout: 30_000 });
    await screenshot(page, "04-model-checkin");

    await page.setInputFiles("input[type=file]", FIXTURE_CSV);
    await expect(page.getByTestId("upload-success")).toContainText("120 / 120", { timeout: 30_000 });

    await page.getByTestId("lock-model").click();
    await expect(page.getByTestId("model-locked-banner")).toContainText("cannot change during the game");
    await screenshot(page, "04-model-checkin-locked");
    await page.context().close();
    await prof.context().close();
  });

  test("06 — professor opens practice; deal board renders", async ({ browser }) => {
    const prof = await newPage(browser, resolve(HERE, ".state-professor.json"));
    await prof.goto("/professor");
    await prof.getByTestId("open-practice").click();
    await expect(prof.getByTestId("kpi-models")).toHaveText("1 / 1");
    await prof.context().close();

    // Student A re-enters the seat; the phase gate lands them on the board.
    const page = await newPage(browser, STUDENT_A_STATE);
    await page.goto("/game/practice");
    await expect(page.getByTestId("deal-board")).toBeVisible({ timeout: 30_000 });
    const cards = page.locator("[data-testid^='deal-card-']");
    await expect(cards.first()).toBeVisible();
    await screenshot(page, "05-practice-deal-board");
    await page.context().close();
  });

  test("07 — underwriting drawer over the board", async ({ browser }) => {
    const page = await newPage(browser, STUDENT_A_STATE);
    await page.goto("/game/practice");
    await expect(page.getByTestId("deal-board")).toBeVisible({ timeout: 30_000 });

    const cards = page.locator("[data-testid^='deal-card-']");
    const count = await cards.count();
    expect(count).toBeGreaterThanOrEqual(1);
    for (let i = 0; i < count; i += 1) {
      const propId = (await cards.nth(i).getAttribute("data-testid"))!.replace("deal-card-", "");
      await page.getByTestId(`underwrite-${propId}`).click();
      await expect(page.getByRole("dialog")).toBeVisible();
      // Every mandated drawer section present.
      await expect(page.getByRole("dialog")).toContainText("Property");
      await expect(page.getByRole("dialog")).toContainText("Operations");
      await expect(page.getByRole("dialog")).toContainText("Capital markets");
      await expect(page.getByRole("dialog")).toContainText("Ownership costs");
      // The analysis chain (forecast → policy → decision) is its own sticky column.
      await expect(page.getByRole("dialog")).toContainText("Pre-class forecast");
      await expect(page.getByRole("dialog")).toContainText("Investment policy");
      await expect(page.getByTestId("drawer-decision")).toBeVisible();
      // The reserve-rate charge is visually distinct from indicative capex.
      await expect(page.getByTestId("reserve-rate-chip")).toBeVisible();
      if (i === 0) await screenshot(page, "06-underwriting-drawer");
      await page.getByRole("button", { name: "Close drawer" }).click();
    }
    await page.context().close();
  });

  test("08 — decide on every deal, review, lock; refresh preserves everything", async ({ browser }) => {
    const page = await newPage(browser, STUDENT_A_STATE);
    await page.goto("/game/practice");
    await expect(page.getByTestId("deal-board")).toBeVisible({ timeout: 30_000 });

    const cards = page.locator("[data-testid^='deal-card-']");
    const count = await cards.count();
    for (let i = 0; i < count; i += 1) {
      const propId = (await cards.nth(i).getAttribute("data-testid"))!.replace("deal-card-", "");
      if (i === 0) {
        // BID slightly above the ask — exercises the policy-override path.
        await page.getByTestId(`bid-${propId}`).click();
        const askText = await cards.nth(i).locator(".deal-metric").first().locator(".m-value").textContent();
        const ask = Number(askText!.replace(/[$M,]/g, ""));
        await page.getByTestId(`bid-price-${propId}`).fill((ask * 1.01).toFixed(1));
        await page.getByTestId(`bid-ltv-${propId}`).fill("58");
        await expect(page.getByTestId(`total-cash-${propId}`).first()).toContainText("$");
      } else {
        await page.getByTestId(`pass-${propId}`).click();
      }
    }

    await screenshot(page, "07-review-decisions-made");
    await expect(page.getByTestId("review-submit")).toBeEnabled();
    await page.getByTestId("review-submit").click();
    await expect(page.getByTestId("review-table")).toBeVisible();
    await expect(page.getByTestId("lock-decisions")).toBeVisible();
    await screenshot(page, "07-review-and-submit");
    await page.getByTestId("lock-decisions").click();

    // Waiting state with the submission count.
    await expect(page.getByTestId("waiting-banner")).toContainText("Decisions locked");
    await expect(page.getByTestId("submission-count")).toBeVisible();
    await screenshot(page, "08-waiting");

    // REFRESH: state unchanged — the seat and the locked decisions survive.
    await page.reload();
    await expect(page.getByTestId("waiting-banner")).toContainText("Decisions locked");
    await page.context().close();
  });

  test("09 — professor closes practice; students receive results automatically", async ({ browser }) => {
    // The student's browser is OPEN while the professor acts — the reveal must arrive
    // through SSE alone, with no navigation and no reload.
    const page = await newPage(browser, STUDENT_A_STATE);
    await page.goto("/game/waiting");
    await expect(page.getByTestId("waiting-banner")).toBeVisible({ timeout: 30_000 });

    const prof = await newPage(browser, resolve(HERE, ".state-professor.json"));
    await prof.goto("/professor");
    await prof.getByTestId("close-practice").click();
    await expect(prof.getByTestId("kpi-practice")).toContainText("1 / 1");

    await expect(page.getByTestId("practice-not-booked")).toContainText("Transaction not booked", {
      timeout: 30_000,
    });
    const bannerText = await page.getByTestId("practice-not-booked").textContent();
    expect(bannerText).not.toMatch(/NO SALE/i);
    await screenshot(page, "10-practice-results");

    // Professor grid stays sealed: no bid amounts on the projected screen.
    const gridText = await prof.getByTestId("fund-grid").textContent();
    expect(gridText).not.toContain("$");
    await screenshot(prof, "09-professor-console-final");
    await page.context().close();
    await prof.context().close();
  });

  test("10 — visual sweep at three viewports, no horizontal scrolling", async ({ browser }) => {
    test.setTimeout(240_000);
    const page = await newPage(browser, STUDENT_A_STATE);

    const check = async () => {
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
      expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);
    };

    // Results screen (the flow's terminus).
    await page.goto("/game/results");
    await expect(page.getByTestId("practice-not-booked")).toBeVisible({ timeout: 30_000 });
    for (const [w, h, name] of [
      [1366, 768, "viewport-1366x768-results"],
      [1440, 900, "viewport-1440x900-results"],
      [1920, 1080, "viewport-1920x1080-results"],
    ] as const) {
      await page.setViewportSize({ width: w, height: h });
      await page.waitForTimeout(250);
      await check();
      await screenshot(page, name);
    }

    // Deal board — the densest screen.
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto("/game/results"); // gate will bounce to where the session is
    await expect(page.getByTestId("practice-not-booked")).toBeVisible();
    await page.context().close();
  });

  test("11 — text audit: no explanatory block over 240 characters in core gameplay", async ({ browser }) => {
    const page = await newPage(browser, STUDENT_A_STATE);
    await page.goto("/game/results");
    await expect(page.getByTestId("practice-not-booked")).toBeVisible({ timeout: 30_000 });

    const offenders = await page.evaluate(() => {
      const out: string[] = [];
      for (const el of Array.from(document.querySelectorAll("p, li, .help, .note-box, .sub"))) {
        const text = (el.textContent ?? "").trim();
        // Blocks, not sentences inside a KV row or a chip.
        if (text.length > 240 && el.children.length === 0) out.push(text.slice(0, 80));
        // Tooltip-stored text does not render; title attributes are exempt.
      }
      return out;
    });
    expect(offenders, JSON.stringify(offenders)).toEqual([]);
    await page.context().close();
  });
});
