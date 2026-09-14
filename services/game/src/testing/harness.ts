/**
 * Test harness.
 *
 * Two things here exist to make the tests meaningful rather than convenient.
 *
 * **`Browser` behaves like a browser, not like a function call.** It keeps one cookie
 * jar per instance and re-sends what the server set, exactly as a real client would.
 * That is what lets a test say "refresh changes nothing" and mean it: a second
 * request from the same jar is a refresh, and a new jar is a different person.
 *
 * **`restart()` builds a genuinely separate server over the same data.** Not a
 * mocked flag: a second Fastify instance, a second context, sharing only the store.
 * The property under test — a cookie minted before the restart still works, and the
 * session is unchanged — is the one that decides whether Cloud Run scaling to zero
 * logs a class out mid-exercise.
 */

import type { FastifyInstance } from "fastify";

import { loadConfig, type ServiceConfig } from "../config.js";
import { createContext, type AppContext } from "../context.js";
import { buildServer } from "../server.js";
import { MemoryStore } from "../store/memory.js";
import { FakeEngine } from "./fakeEngine.js";
import type { Engine } from "../engineClient.js";

export const TEST_PASSCODE = "frenzel";
export const TEST_COOKIE_SECRET = "test-secret-that-is-at-least-32-characters-long";

export function testConfig(overrides: Partial<ServiceConfig> = {}): ServiceConfig {
  return {
    ...loadConfig({
      COOKIE_SECRET: TEST_COOKIE_SECRET,
      PROFESSOR_PASSCODE: TEST_PASSCODE,
      COOKIE_INSECURE: "1",
      ENGINE_URL: "http://engine.invalid",
      PORT: "0",
      HOST: "127.0.0.1",
    } as NodeJS.ProcessEnv),
    cookieName: "cre_test",
    ...overrides,
  };
}

export interface Response {
  status: number;
  body: any;
  headers: Record<string, unknown>;
}

/** One cookie jar, one identity. */
export class Browser {
  readonly cookies = new Map<string, string>();

  constructor(private readonly app: FastifyInstance, readonly label: string) {}

  headerLines(): Record<string, string> {
    if (this.cookies.size === 0) return {};
    return {
      cookie: [...this.cookies.entries()].map(([k, v]) => `${k}=${v}`).join("; "),
    };
  }

  async request(
    method: "GET" | "POST",
    url: string,
    options: { body?: unknown; headers?: Record<string, string> } = {},
  ): Promise<Response> {
    const headers: Record<string, string> = { ...this.headerLines(), ...options.headers };
    const payload = options.body;
    if (payload !== undefined && typeof payload === "string") {
      headers["content-type"] ??= "text/csv";
    } else if (payload !== undefined) {
      headers["content-type"] ??= "application/json";
    }

    const res = await this.app.inject({
      method,
      url,
      headers,
      ...(payload === undefined
        ? {}
        : { payload: typeof payload === "string" ? payload : JSON.stringify(payload) }),
    });

    const rawCookies = res.headers["set-cookie"];
    for (const line of Array.isArray(rawCookies) ? rawCookies : rawCookies ? [rawCookies] : []) {
      const eq = String(line).indexOf("=");
      if (eq < 0) continue;
      const name = String(line).slice(0, eq).trim();
      const value = String(line).slice(eq + 1).split(";")[0]!.trim();
      this.cookies.set(name, value);
    }

    let body: unknown = null;
    const text = res.payload;
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        body = text;
      }
    }
    return { status: res.statusCode, body, headers: res.headers as Record<string, unknown> };
  }

  get(url: string, headers?: Record<string, string>): Promise<Response> {
    return this.request("GET", url, headers ? { headers } : {});
  }

  post(url: string, body?: unknown, headers?: Record<string, string>): Promise<Response> {
    return this.request("POST", url, { body, ...(headers ? { headers } : {}) });
  }
}

export interface Harness {
  app: FastifyInstance;
  store: MemoryStore;
  /** Whatever engine this harness was built with: the fake, or the real one. */
  engine: Engine;
  /** The fake, when the harness is running on one. The milestone passes null. */
  fake: FakeEngine | null;
  config: ServiceConfig;
  context: AppContext;
  browser(label: string): Browser;
  /** A fresh server and context over the same persisted data: a process restart. */
  restart(): Promise<Harness>;
  close(): Promise<void>;
}

/** The fake engine, or a clear error — so a test cannot silently assert nothing. */
export function fakeOf(harness: Harness): FakeEngine {
  if (!harness.fake) {
    throw new Error("this harness is running on the real engine, not the fake");
  }
  return harness.fake;
}

export async function startHarness(options: {
  store?: MemoryStore;
  engine?: Engine;
  config?: ServiceConfig;
} = {}): Promise<Harness> {
  const store = options.store ?? new MemoryStore();
  const engine = options.engine ?? new FakeEngine();
  const config = options.config ?? testConfig();
  await store.ensureReady();
  const context = createContext({ store, engine, config });
  const app = buildServer({ config, context });
  await app.ready();

  const browsers: Browser[] = [];
  const harness: Harness = {
    app,
    store,
    engine,
    fake: engine instanceof FakeEngine ? engine : null,
    config,
    context,
    browser(label: string) {
      const browser = new Browser(app, label);
      browsers.push(browser);
      return browser;
    },
    async restart() {
      // A new Fastify instance, a new context, the same engine — and the same store.
      // Nothing in-process carries over except the persisted documents, which is the
      // point: the restart must be survivable by the *data*, not by a hot module.
      return startHarness({ store, engine, config });
    },
    async close() {
      void browsers;
      await app.close();
    },
  };
  return harness;
}

/** Pull the join code out of a create-session response. */
export function joinCodeOf(body: unknown): string {
  const code = (body as { joinCode?: unknown })?.joinCode;
  if (typeof code !== "string") throw new Error("no joinCode in the response");
  return code;
}

export function revisionOf(body: unknown): number {
  const revision = (body as { session?: { revision?: unknown } })?.session?.revision;
  if (typeof revision !== "number") throw new Error("no revision in the response");
  return revision;
}
