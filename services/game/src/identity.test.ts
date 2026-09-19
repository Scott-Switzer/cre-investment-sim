/**
 * Which class is this browser in?
 *
 * A browser can hold more than one seat. Cookies are per session, so a student in two
 * sections, or a professor running two, holds two equally real grants — and there is
 * no fact of the matter about which one `/v1/whoami` should name on its own. The
 * original implementation took the first cookie the browser sent, which in cookie
 * order is the *oldest*: join a second class and the client would mount the first.
 *
 * That failure is invisible to the person it happens to. They are not told they are in
 * the wrong class; they see a familiar screen with the wrong round in it. So these
 * tests pin down the two properties that make it impossible:
 *
 *   1. An explicit `?session=<id>` is answered exactly — that seat, or a refusal.
 *   2. Without an explicit id, an ambiguous browser is told it is ambiguous.
 *
 * The refusal half matters as much as the answer. A shared or stale link names a
 * session its holder may not have a seat in, and the one response that must never
 * come back is somebody else's.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { startHarness, type Browser, type Harness } from "./testing/harness.js";
import { createClass } from "./testing/scenarios.js";

let harness: Harness;

beforeEach(async () => {
  harness = await startHarness();
});

afterEach(async () => {
  await harness.close();
});

interface Seat {
  sessionId: string;
  name: string;
}

async function joinOne(browser: Browser, seat: Seat, fundName: string): Promise<void> {
  const fixture = await createClass(harness, { name: seat.name });
  seat.sessionId = fixture.sessionId;
  const res = await browser.post("/v1/join", {
    joinCode: fixture.joinCode,
    displayName: "Dana",
    newFundName: fundName,
  });
  expect(res.status).toBe(201);
}

/**
 * One browser, two classes, oldest cookie first — the cookie order a real client sends,
 * because they all share `/` and RFC 6265 sorts those by creation time.
 */
async function twoSeats(): Promise<{ browser: Browser; first: Seat; second: Seat }> {
  const first: Seat = { sessionId: "", name: "Morning section" };
  const second: Seat = { sessionId: "", name: "Afternoon section" };
  const browser = harness.browser("Dana");
  await joinOne(browser, first, "Morning Fund");
  await joinOne(browser, second, "Afternoon Fund");
  return { browser, first, second };
}

describe("whoami", () => {
  it("names the only seat when the browser holds exactly one", async () => {
    const browser = harness.browser("Dana");
    const seat: Seat = { sessionId: "", name: "Only" };
    await joinOne(browser, seat, "Only Fund");

    const res = await browser.get("/v1/whoami");
    expect(res.status).toBe(200);
    expect(res.body.sessionId).toBe(seat.sessionId);
    expect(res.body.ambiguous).toBe(false);
    expect(res.body.sessions).toHaveLength(1);
    expect(res.body.sessions[0].role).toBe("student");
  });

  it("has no seat to name for a browser that never joined", async () => {
    const res = await harness.browser("stranger").get("/v1/whoami");
    expect(res.status).toBe(200);
    expect(res.body.sessionId).toBeNull();
    expect(res.body.sessions).toEqual([]);
    expect(res.body.ambiguous).toBe(false);
  });

  it("reports two held seats as ambiguous instead of choosing one", async () => {
    const { browser, first, second } = await twoSeats();

    const res = await browser.get("/v1/whoami");
    expect(res.body.sessionId).toBeNull();
    expect(res.body.ambiguous).toBe(true);
    const held = (res.body.sessions as { sessionId: string }[]).map((s) => s.sessionId);
    expect(held).toContain(first.sessionId);
    expect(held).toContain(second.sessionId);
  });

  it("answers for the session that was asked for, not the first one held", async () => {
    const { browser, first, second } = await twoSeats();

    // The regression: the second seat is the newer cookie, so a first-valid-cookie
    // implementation answers with `first` here and the student lands in the wrong class.
    const res = await browser.get(`/v1/whoami?session=${second.sessionId}`);
    expect(res.body.sessionId).toBe(second.sessionId);
    expect(res.body.memberId).toBeTruthy();
    expect(res.body.sessionId).not.toBe(first.sessionId);

    const firstRes = await browser.get(`/v1/whoami?session=${first.sessionId}`);
    expect(firstRes.body.sessionId).toBe(first.sessionId);
  });

  it("refuses a session the browser holds no seat in rather than serving another", async () => {
    const { browser, first, second } = await twoSeats();
    const stranger = await createClass(harness, { name: "Someone else's class" });

    const res = await browser.get(`/v1/whoami?session=${stranger.sessionId}`);
    expect(res.status).toBe(200);
    expect(res.body.sessionId).toBeNull();
    expect(res.body.reason).toBe("no_grant_for_requested_session");
    expect(res.body.requestedSession).toBe(stranger.sessionId);
    // The one answer that must never come back: a different session's seat.
    expect(res.body.sessionId).not.toBe(first.sessionId);
    expect(res.body.sessionId).not.toBe(second.sessionId);
  });

  it("still refuses cleanly when the requested id is not a session at all", async () => {
    const { browser } = await twoSeats();
    const res = await browser.get("/v1/whoami?session=not-a-real-session");
    expect(res.status).toBe(200);
    expect(res.body.sessionId).toBeNull();
    expect(res.body.reason).toBe("no_grant_for_requested_session");
  });

  it("would have picked the wrong class under the old first-valid-cookie rule", async () => {
    const { browser, first } = await twoSeats();

    // The rule the client used to depend on, reproduced against this exact jar: walk
    // the cookies the browser sends and take the first name that validates. Because
    // equal-path cookies go out oldest-first, that resolves to the *older* class.
    const byFirstValidCookie = ((): string | null => {
      for (const name of browser.cookies.keys()) {
        if (name.startsWith("cre_test_")) return name.slice("cre_test_".length);
      }
      return null;
    })();

    // This is the bug, stated as a fact about the jar rather than a story about it:
    // the newer seat is the one the player just took, and it is not the one that rule
    // names. The explicit `?session=` answer above is what removes the guess.
    expect(byFirstValidCookie).toBe(first.sessionId);
  });

  it("keeps a professor's own console and a student seat distinct in one browser", async () => {
    // A professor hosting two sections, or helping with a colleague's class, holds a
    // professor grant and a student grant at once. Naming one must not return the other.
    const hosted = await createClass(harness, { name: "Section A" });
    const student = { sessionId: "", name: "Section B" } as Seat;
    await joinOne(hosted.professor, student, "Visiting Fund");

    const asProfessor = await hosted.professor.get(`/v1/whoami?session=${hosted.sessionId}`);
    expect(asProfessor.body.sessionId).toBe(hosted.sessionId);
    expect(asProfessor.body.role).toBe("professor");

    const asStudent = await hosted.professor.get(`/v1/whoami?session=${student.sessionId}`);
    expect(asStudent.body.sessionId).toBe(student.sessionId);
    expect(asStudent.body.role).toBe("student");
  });

  it("resolves the named session's own state, not the other seat's", async () => {
    const { browser, first, second } = await twoSeats();

    const named = await browser.get(`/v1/sessions/${second.sessionId}/state`);
    expect(named.status).toBe(200);
    expect(named.body.session.id).toBe(second.sessionId);
    expect(named.body.session.name).toBe("Afternoon section");

    const other = await browser.get(`/v1/sessions/${first.sessionId}/state`);
    expect(other.body.session.name).toBe("Morning section");
  });
});
