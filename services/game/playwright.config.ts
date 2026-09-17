import { defineConfig, devices } from "@playwright/test";

/**
 * The Phase 2 browser gate.
 *
 * The full local stack is started once by `webServer` entries: Python engine →
 * Firestore emulator → game service (serving the built client). Every test then
 * drives *real browsers* through the real HTTP surface — no direct API shortcuts:
 * the professor creates the session in the professor console, students join through
 * the join screen, and decisions are locked through the review modal.
 */
export default defineConfig({
  testDir: "tests/e2e",
  timeout: 180_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:8080",
    testIdAttribute: "data-testid",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: [
    {
      command: "bash tests/e2e/start-emulator.sh",
      url: "http://127.0.0.1:8085",
      // The emulator is state-cleared by firebase for each managed run; allow
      // Playwright to attach when the emulator wrapper is still draining.
      reuseExistingServer: true,
      timeout: 120_000,
      cwd: ".",
    },
    {
      command: "uv run python scripts/stack_test.py",
      url: "http://127.0.0.1:8080/v1/health",
      cwd: "../..",
      // A stale service can be healthy while serving the wrong store/config.
      reuseExistingServer: false,
      timeout: 240_000,
    },
  ],
});
