/**
 * Signed HttpOnly cookie sessions.
 *
 * No accounts, per the architecture: a student should be able to close the tab,
 * reopen the link, and still be in their seat. That rules out anything held in
 * memory or in `localStorage`, so identity is a signed cookie the server issues and
 * verifies. Clearing cookies loses the seat, which is what the join code plus a
 * professor's seat reassignment is for.
 *
 * The cookie is **per session**, not global: `cre_game_<sessionId>`. A student in
 * one class and a professor helping with another have independent identities, and
 * there is no "which session am I in" ambiguity to get wrong.
 *
 * The payload is signed, not encrypted. It carries no secret — a member id, a fund
 * id, a role — and the signature is what stops a browser naming its own fund.
 */

import { createHmac, timingSafeEqual } from "node:crypto";

export interface Grant {
  sessionId: string;
  memberId: string;
  fundId: string | null;
  role: "student" | "professor";
  displayName: string;
  /** Issued at / expires at, in epoch seconds. */
  iat: number;
  exp: number;
}

const SESSION_ID_PATTERN = /^[A-Za-z0-9_-]{4,64}$/;

function b64url(input: Buffer | string): string {
  return Buffer.from(input).toString("base64url");
}

function sign(payload: string, secret: string): string {
  return createHmac("sha256", secret).update(payload).digest("base64url");
}

export function cookieName(base: string, sessionId: string): string {
  // A session id is server-generated from a fixed alphabet, but it becomes a cookie
  // *name* here, so it is validated rather than trusted: a name containing `;` or
  // `=` would let a crafted id inject a header.
  if (!SESSION_ID_PATTERN.test(sessionId)) {
    throw new Error(`session id '${sessionId}' is not usable as a cookie name component`);
  }
  return `${base}_${sessionId}`;
}

export function issueGrant(grant: Grant, secret: string): string {
  const payload = b64url(JSON.stringify(grant));
  return `${payload}.${sign(payload, secret)}`;
}

export function verifyGrant(token: string | undefined, secret: string): Grant | null {
  if (!token) return null;
  const dot = token.lastIndexOf(".");
  if (dot <= 0) return null;
  const payload = token.slice(0, dot);
  const provided = token.slice(dot + 1);

  const expected = sign(payload, secret);
  const a = Buffer.from(provided);
  const b = Buffer.from(expected);
  // Length check first: timingSafeEqual throws on a length mismatch, and throwing
  // here would turn a malformed cookie into a 500 instead of a 401.
  if (a.length !== b.length || !timingSafeEqual(a, b)) return null;

  let parsed: Grant;
  try {
    parsed = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as Grant;
  } catch {
    return null;
  }
  if (
    typeof parsed.sessionId !== "string" ||
    typeof parsed.memberId !== "string" ||
    (parsed.role !== "student" && parsed.role !== "professor") ||
    typeof parsed.exp !== "number"
  ) {
    return null;
  }
  if (parsed.exp * 1000 <= Date.now()) return null;
  return parsed;
}

export function newGrant(
  fields: Omit<Grant, "iat" | "exp">,
  ttlSeconds: number,
): Grant {
  const iat = Math.floor(Date.now() / 1000);
  return { ...fields, iat, exp: iat + ttlSeconds };
}

export interface CookieSpec {
  name: string;
  value: string;
  options: {
    httpOnly: true;
    sameSite: "lax";
    path: string;
    maxAge: number;
    secure: boolean;
  };
}

export function buildCookie(
  name: string,
  grant: Grant,
  secret: string,
  ttlSeconds: number,
  secure: boolean,
): CookieSpec {
  return {
    name,
    value: issueGrant(grant, secret),
    options: {
      httpOnly: true,
      sameSite: "lax",
      path: "/",
      maxAge: ttlSeconds,
      secure,
    },
  };
}

/**
 * Constant-time passcode check.
 *
 * The passcode is shared across a class and read aloud, so it is not a strong
 * secret. Comparing in constant time costs nothing and removes the one attack that
 * would otherwise work trivially against it.
 */
export function passcodeMatches(provided: string, expected: string): boolean {
  const a = Buffer.from(provided);
  const b = Buffer.from(expected);
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);
}
