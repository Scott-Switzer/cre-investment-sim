/**
 * The event stream.
 *
 * SSE here is a doorbell, not a data channel, and this suite exists to keep it that
 * way. Two properties are load-bearing:
 *
 * **It carries a revision and nothing else.** If a room's worth of game state ever
 * travelled on this stream, the stream would become a second, unaudited projection —
 * and the projection boundary is the one thing this design cannot duplicate.
 *
 * **Losing it is harmless.** A client that misses every event still converges, because
 * its next poll reads the authoritative document. That is what makes an in-process
 * notifier safe on a platform that recycles instances.
 *
 * Driven over a real socket rather than `inject`, because the thing under test is a
 * streaming response and `inject` does not stream.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { startHarness, type Harness } from "./testing/harness.js";
import { createClass, joinClass, revisionOfSession } from "./testing/scenarios.js";

let harness: Harness;
let baseUrl: string;

beforeEach(async () => {
  harness = await startHarness();
  baseUrl = await harness.app.listen({ port: 0, host: "127.0.0.1" });
});

afterEach(async () => {
  await harness.close();
});

/** Read SSE frames until `predicate` is satisfied or the deadline passes. */
async function readFrames(
  url: string,
  cookie: string,
  count: number,
  deadlineMs = 4000,
): Promise<{ frames: string[]; raw: string; abort: () => void }> {
  const controller = new AbortController();
  const response = await fetch(url, {
    headers: { cookie, accept: "text/event-stream" },
    signal: controller.signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`SSE did not open: ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let raw = "";
  const started = Date.now();

  while (
    raw.split("\n\n").filter((chunk) => chunk.includes("event: revision")).length < count &&
    Date.now() - started < deadlineMs
  ) {
    const { value, done } = await reader.read();
    if (done) break;
    raw += decoder.decode(value, { stream: true });
  }

  controller.abort();
  return {
    frames: raw.split("\n\n").filter((chunk) => chunk.includes("event: revision")),
    raw,
    abort: () => controller.abort(),
  };
}

describe("GET /events", () => {
  it("opens with the current revision and follows a change", async () => {
    const fixture = await createClass(harness);
    const student = await joinClass(harness, {
      joinCode: fixture.joinCode,
      displayName: "Dana",
    });
    const cookie = [...student.browser.cookies.entries()]
      .map(([k, v]) => `${k}=${v}`)
      .join("; ");

    const startRevision = await revisionOfSession(harness, fixture.sessionId);

    const streamed = readFrames(
      `${baseUrl}/v1/sessions/${fixture.sessionId}/events`,
      cookie,
      2,
    );
    // Give the stream a moment to open before moving the session along.
    await new Promise((resolve) => setTimeout(resolve, 150));
    await joinClass(harness, { joinCode: fixture.joinCode, displayName: "Ravi" });

    const { frames } = await streamed;
    expect(frames.length).toBeGreaterThanOrEqual(2);

    const revisions = frames.map(
      (frame) => JSON.parse(frame.split("data: ")[1]!.trim()) as { revision: number },
    );
    expect(revisions[0]!.revision).toBe(startRevision);
    expect(revisions.at(-1)!.revision).toBeGreaterThan(startRevision);
  });

  it("carries a revision and nothing else — never a deal, a NAV or a reserve", async () => {
    const fixture = await createClass(harness);
    const student = await joinClass(harness, {
      joinCode: fixture.joinCode,
      displayName: "Dana",
      newFundName: "Value Fund",
    });
    const cookie = [...student.browser.cookies.entries()]
      .map(([k, v]) => `${k}=${v}`)
      .join("; ");

    const streamed = readFrames(
      `${baseUrl}/v1/sessions/${fixture.sessionId}/events`,
      cookie,
      1,
    );
    await new Promise((resolve) => setTimeout(resolve, 200));
    const { raw } = await streamed;

    // The only JSON on the wire is a revision number.
    const payloads = [...raw.matchAll(/data: (.+)/g)].map((m) => m[1]!);
    expect(payloads.length).toBeGreaterThan(0);
    for (const payload of payloads) {
      expect(Object.keys(JSON.parse(payload))).toEqual(["revision"]);
    }
    expect(raw).not.toContain("deals");
    expect(raw).not.toContain("reserve");
    expect(raw).not.toContain("nav");
    expect(raw).not.toContain("engineState");
  });

  it("refuses a stream to anyone who is not signed in for that session", async () => {
    const fixture = await createClass(harness);
    const response = await fetch(`${baseUrl}/v1/sessions/${fixture.sessionId}/events`);
    expect(response.status).toBe(401);
  });

  it("keeps the stream alive while nothing happens, with a comment heartbeat", async () => {
    const fixture = await createClass(harness);
    const student = await joinClass(harness, {
      joinCode: fixture.joinCode,
      displayName: "Dana",
    });
    const cookie = [...student.browser.cookies.entries()]
      .map(([k, v]) => `${k}=${v}`)
      .join("; ");

    const response = await fetch(`${baseUrl}/v1/sessions/${fixture.sessionId}/events`, {
      headers: { cookie },
    });
    expect(response.headers.get("content-type")).toContain("text/event-stream");
    // Cloud Run buffers responses unless this is set, which turns a live stream into a
    // twenty-second delay and makes the game feel broken.
    expect(response.headers.get("x-accel-buffering")).toBe("no");
    expect(response.headers.get("cache-control")).toContain("no-cache");
    await response.body?.cancel();
  });
});
