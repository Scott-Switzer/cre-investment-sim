/**
 * The real Python engine, as a separate process.
 *
 * The correctness suite runs against a fake so it can be fast. This starts the actual
 * engine so the milestone can be honest: the same container the classroom will talk to,
 * over the same HTTP surface, with the same 284-test adjudicator behind it.
 *
 * Started once per test file and reused, because booting uvicorn takes about a second
 * and the tests that use it are about sequences, not about startup.
 */

import { spawn, type ChildProcess } from "node:child_process";
import { readFileSync } from "node:fs";
import { createServer } from "node:net";
import { resolve } from "node:path";

const REPO_ROOT = resolve(process.cwd(), "../..");

export interface RunningEngine {
  url: string;
  stop: () => Promise<void>;
}

async function freePort(): Promise<number> {
  return new Promise((resolvePort, reject) => {
    const server = createServer();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (typeof address === "string" || address === null) {
        reject(new Error("could not determine a free port"));
        return;
      }
      const { port } = address;
      server.close(() => resolvePort(port));
    });
  });
}

async function waitForHealth(url: string, deadlineMs = 60_000): Promise<void> {
  const started = Date.now();
  let lastError = "no attempt made";
  while (Date.now() - started < deadlineMs) {
    try {
      const response = await fetch(`${url}/v1/health`, { signal: AbortSignal.timeout(2000) });
      if (response.ok) return;
      lastError = `HTTP ${response.status}`;
    } catch (err) {
      lastError = err instanceof Error ? err.message : String(err);
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`the engine did not become healthy within ${deadlineMs}ms: ${lastError}`);
}

export async function startEngine(): Promise<RunningEngine> {
  const port = await freePort();
  const url = `http://127.0.0.1:${port}`;
  const child: ChildProcess = spawn(
    "uv",
    ["run", "python", "scripts/serve_engine.py"],
    {
      cwd: REPO_ROOT,
      env: { ...process.env, PORT: String(port), HOST: "127.0.0.1", LOG_LEVEL: "warning" },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );

  let output = "";
  child.stdout?.on("data", (chunk) => {
    output += String(chunk);
  });
  child.stderr?.on("data", (chunk) => {
    output += String(chunk);
  });

  try {
    await waitForHealth(url);
  } catch (err) {
    child.kill("SIGKILL");
    throw new Error(
      `${err instanceof Error ? err.message : String(err)}\n--- engine output ---\n${output}`,
    );
  }

  return {
    url,
    stop: async () => {
      if (child.exitCode !== null) return;
      child.kill("SIGTERM");
      await new Promise((r) => setTimeout(r, 200));
      if (child.exitCode === null) child.kill("SIGKILL");
    },
  };
}

/** The published student packet fixture: 120 rows for the shipped pool. */
export const REALISTIC_STUDENT_FIXTURE = resolve(
  REPO_ROOT,
  "tests/fixtures/student_submission_realistic.csv",
);

export function realisticStudentCsv(): string {
  return readFileSync(REALISTIC_STUDENT_FIXTURE, "utf8");
}

export const REAL_BUNDLE_ID = "real605-fall26-v1";
