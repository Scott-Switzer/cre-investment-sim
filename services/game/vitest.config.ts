import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "tests/**/*.test.ts"],
    // The milestone and restart suites stand up a real Python engine over HTTP, so
    // they are slower than a pure unit test by an order of magnitude.
    testTimeout: 120_000,
    hookTimeout: 120_000,
    // Serial: several suites share one engine port and the emulator.
    fileParallelism: false,
  },
});
