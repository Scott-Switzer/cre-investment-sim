/**
 * Identifiers and join codes.
 *
 * Join codes are meant to be read aloud across a room and typed once, so the
 * alphabet excludes the characters people mis-hear and mistype: I/1, O/0, and S/5.
 * A student who writes down "OI8S1O" and cannot join is a five-minute classroom
 * loss, and the fix costs nothing here.
 */

import { randomBytes, randomUUID } from "node:crypto";

/** No I, L, O, S, 0, 1, 5 — the pairs that get transcribed wrong on a whiteboard. */
const JOIN_ALPHABET = "ABCDEFGHJKMNPQRTUVWXYZ2346789";
export const JOIN_CODE_LENGTH = 6;

export function newId(prefix: string): string {
  return `${prefix}_${randomUUID().replace(/-/g, "").slice(0, 20)}`;
}

export function newJoinCode(): string {
  const bytes = randomBytes(JOIN_CODE_LENGTH);
  let out = "";
  for (const byte of bytes) {
    out += JOIN_ALPHABET[byte % JOIN_ALPHABET.length];
  }
  return out;
}

/**
 * Fold a code a student typed into its canonical form.
 *
 * Deliberately forgiving in one direction only: it upper-cases and strips
 * separators, and maps the look-alikes onto the characters the alphabet actually
 * uses. `o1-8s` becomes a real lookup key instead of "not found".
 */
export function canonicalJoinCode(input: string): string {
  return input
    .toUpperCase()
    .replace(/[\s-_.]/g, "")
    .replace(/[IL]/g, "J")
    .replace(/O/g, "Q")
    .replace(/S/g, "Z")
    .replace(/0/g, "Q")
    .replace(/1/g, "J")
    .replace(/5/g, "Z");
}

export function isJoinCodeShaped(input: string): boolean {
  return canonicalJoinCode(input).length === JOIN_CODE_LENGTH;
}

export function newToken(): string {
  return randomBytes(32).toString("base64url");
}

export function nowIso(): string {
  return new Date().toISOString();
}
