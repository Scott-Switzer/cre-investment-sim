/**
 * Runtime configuration, read once and validated at startup.
 *
 * The cookie secret is deliberately *required*, not generated when absent. A
 * per-process random secret would look fine in development and then invalidate
 * every student's session on each Cloud Run cold start — the failure would appear
 * as "the site logged me out mid-class", long after the cause. Refusing to boot is
 * cheaper than diagnosing that.
 */

import { AppError } from "./errors.js";

export interface ServiceConfig {
  readonly port: number;
  readonly host: string;
  /** Base URL of the private Python engine. Server-to-server only. */
  readonly engineUrl: string;
  /** Sent as a bearer token to the engine when it sits behind IAM. Empty locally. */
  readonly engineToken: string;
  readonly cookieSecret: string;
  readonly professorPasscode: string;
  /**
   * Marks cookies Secure. Off for localhost HTTP, on everywhere else. Defaults to
   * true because the failure mode of forgetting it in production (a session cookie
   * readable over plaintext) is worse than the failure mode of forgetting it
   * locally (a login that does not stick, in front of the only person who can fix it).
   */
  readonly cookieSecure: boolean;
  readonly cookieName: string;
  readonly sessionSecret: string;
  readonly sessionTtlSeconds: number;
  readonly allowedOrigins: readonly string[];
  /**
   * Commit this process was built from, or null when nobody said. Baked in at deploy
   * time and reported by the health routes so "is the deployed build the merged one?"
   * is a question a response can answer instead of a story about who deployed when.
   */
  readonly buildSha: string | null;
}

const MIN_SECRET_LENGTH = 32;

function requireSecret(name: string, value: string | undefined, why: string): string {
  if (!value || value.length < MIN_SECRET_LENGTH) {
    throw new AppError(
      "internal",
      `${name} must be set to at least ${MIN_SECRET_LENGTH} characters (${why}). ` +
        `Generate one with: openssl rand -base64 48`,
    );
  }
  return value;
}

/**
 * The first of these that is set. A deploy that forgets to pass the commit reports
 * null — an honest "unknown" beats a stale SHA that would make the build look
 * verifiable when it is not.
 */
function firstNonEmpty(...values: (string | undefined)[]): string | null {
  for (const value of values) {
    const trimmed = value?.trim();
    if (trimmed) return trimmed;
  }
  return null;
}

function csv(value: string | undefined): string[] {
  return (value ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): ServiceConfig {
  const isProduction = env.NODE_ENV === "production";
  return {
    port: Number(env.PORT ?? 8080),
    host: env.HOST ?? "0.0.0.0",
    engineUrl: (env.ENGINE_URL ?? "http://127.0.0.1:8081").replace(/\/+$/, ""),
    engineToken: env.ENGINE_TOKEN ?? "",
    cookieSecret: requireSecret(
      "COOKIE_SECRET",
      env.COOKIE_SECRET,
      "signs the session cookie; a per-process value would log everyone out on restart",
    ),
    professorPasscode: env.PROFESSOR_PASSCODE ?? "frenzel",
    cookieSecure: env.COOKIE_INSECURE === "1" ? false : isProduction || env.COOKIE_SECURE !== "0",
    cookieName: env.COOKIE_NAME ?? "cre_game",
    sessionSecret: env.SESSION_SECRET ?? "",
    sessionTtlSeconds: Number(env.SESSION_TTL_SECONDS ?? 60 * 60 * 12),
    allowedOrigins: csv(env.ALLOWED_ORIGINS),
    buildSha: firstNonEmpty(env.GIT_SHA, env.GITHUB_SHA, env.BUILD_SHA),
  };
}
