/**
 * Session resolution, client side.
 *
 * The provider used to mount by asking `/v1/whoami` and taking whatever came back.
 * Now it states which session it means, in priority order, and pins the answer per
 * tab. These tests cover the three cases that decide classroom behaviour:
 *
 *   - a join just handed back an id, so that id wins;
 *   - a tab's pin survives a refresh, so a student stays where they were;
 *   - a stale hint or pin is inert, so a borrowed link names nothing.
 *
 * The last one is the security-relevant direction: naming a session must never be a
 * way to *become* it. That is enforced by the server refusing a session the browser
 * holds no grant for, and these tests assert the client does not paper over the
 * refusal by falling into some other seat.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  askWhoami,
  readPin,
  resolveSession,
  sessionHintFromUrl,
  writePin,
  type WhoamiAnswer,
} from "./session";

const EMPTY: WhoamiAnswer = { sessionId: null, sessions: [], ambiguous: false };

function fakeAsk(answers: Record<string, WhoamiAnswer>): {
  ask: (sessionId: string | null) => Promise<WhoamiAnswer>;
  asked: (string | null)[];
} {
  const asked: (string | null)[] = [];
  return {
    asked,
    ask: async (sessionId: string | null) => {
      asked.push(sessionId);
      return answers[sessionId ?? ""] ?? EMPTY;
    },
  };
}

const seat = (sessionId: string): WhoamiAnswer => ({
  sessionId,
  sessions: [{ sessionId, role: "student", memberId: `mem_${sessionId}` }],
  ambiguous: false,
});

describe("the ?s= hint", () => {
  it("reads the id join, reclaim and demo put there", () => {
    expect(sessionHintFromUrl("?s=sess_abc")).toBe("sess_abc");
    expect(sessionHintFromUrl("?s=sess_abc&other=1")).toBe("sess_abc");
  });

  it("is absent when the URL says nothing usable", () => {
    expect(sessionHintFromUrl("")).toBeNull();
    expect(sessionHintFromUrl("?other=1")).toBeNull();
    expect(sessionHintFromUrl("?s=")).toBeNull();
    expect(sessionHintFromUrl("?s=%20")).toBeNull();
  });
});

describe("resolveSession", () => {
  it("prefers the named session over anything the tab remembered", async () => {
    const { ask, asked } = fakeAsk({ sess_b: seat("sess_b"), sess_pin: seat("sess_pin") });
    const answer = await resolveSession(ask, ["sess_b", "sess_pin"]);
    expect(answer.sessionId).toBe("sess_b");
    // The pin is not even consulted once the hint is confirmed.
    expect(asked).toEqual(["sess_b"]);
  });

  it("falls back to the tab's pin when the hint names no seat it holds", async () => {
    // A shared or stale link: the browser has no grant for `sess_stale`, so the link is
    // inert and the tab stays where it was.
    const { ask, asked } = fakeAsk({ sess_pin: seat("sess_pin") });
    const answer = await resolveSession(ask, ["sess_stale", "sess_pin"]);
    expect(answer.sessionId).toBe("sess_pin");
    expect(asked).toEqual(["sess_stale", "sess_pin"]);
  });

  it("asks without naming a session when no hint or pin resolves", async () => {
    const { ask, asked } = fakeAsk({ "": seat("sess_only") });
    const answer = await resolveSession(ask, [null, null]);
    expect(answer.sessionId).toBe("sess_only");
    expect(asked).toEqual([null]);
  });

  it("surfaces ambiguity rather than choosing between two held seats", async () => {
    const ambiguous: WhoamiAnswer = {
      sessionId: null,
      sessions: [
        { sessionId: "sess_a", role: "student", memberId: "m1" },
        { sessionId: "sess_b", role: "student", memberId: "m2" },
      ],
      ambiguous: true,
    };
    const { ask } = fakeAsk({ "": ambiguous });
    const answer = await resolveSession(ask, [null, null]);
    expect(answer.sessionId).toBeNull();
    expect(answer.ambiguous).toBe(true);
    expect(answer.sessions.map((s) => s.sessionId)).toEqual(["sess_a", "sess_b"]);
  });

  it("does not treat a refusal as a seat when both hints are stale", async () => {
    // Two stale names must not become an empty-string session or a guess. A null answer
    // is what sends the player to the picker or to /join.
    const { ask, asked } = fakeAsk({ "": EMPTY });
    const answer = await resolveSession(ask, ["sess_gone", "sess_also_gone"]);
    expect(answer.sessionId).toBeNull();
    expect(asked).toEqual(["sess_gone", "sess_also_gone", null]);
  });
});

describe("the tab pin", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("round-trips a session id and clears on null", () => {
    expect(readPin()).toBeNull();
    writePin("sess_pin");
    expect(readPin()).toBe("sess_pin");
    writePin(null);
    expect(readPin()).toBeNull();
  });

  it("is per tab, so one browser can run two sections in two tabs", () => {
    writePin("sess_a");
    // A second tab is a separate sessionStorage, which is the whole reason the pin is
    // not localStorage: a professor watching two sections must not have them collide.
    expect(window.sessionStorage.getItem("cre_session")).toBe("sess_a");
  });
});

describe("askWhoami", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it("names the session it is asking about", async () => {
    const calls: string[] = [];
    vi.stubGlobal("fetch", async (url: string) => {
      calls.push(url);
      return {
        ok: true,
        json: async () => seat("sess_b"),
      } as unknown as Response;
    });

    const answer = await askWhoami("sess_b");
    expect(calls).toEqual(["/v1/whoami?session=sess_b"]);
    expect(answer.sessionId).toBe("sess_b");
  });

  it("asks unqualified when no session is named", async () => {
    const calls: string[] = [];
    vi.stubGlobal("fetch", async (url: string) => {
      calls.push(url);
      return { ok: true, json: async () => EMPTY } as unknown as Response;
    });

    await askWhoami(null);
    expect(calls).toEqual(["/v1/whoami"]);
  });

  it("reads a refusal as no seat, not as an error to retry", async () => {
    vi.stubGlobal("fetch", async () => ({
      ok: true,
      json: async () => ({ sessionId: null, reason: "no_grant_for_requested_session" }),
    }) as unknown as Response);

    const answer = await askWhoami("sess_someone_else");
    expect(answer.sessionId).toBeNull();
    expect(answer.sessions).toEqual([]);
  });

  it("reports no seat when the service cannot be reached", async () => {
    vi.stubGlobal("fetch", async () => {
      throw new Error("offline");
    });
    const answer = await askWhoami(null);
    expect(answer.sessionId).toBeNull();
    expect(answer.ambiguous).toBe(false);
  });

  it("tolerates an older server that does not list seats", async () => {
    // The client must not require `sessions` to mount: a rolling deploy can serve
    // either shape, and a missing list is simply an empty one.
    vi.stubGlobal("fetch", async () => ({
      ok: true,
      json: async () => ({ sessionId: "sess_old" }),
    }) as unknown as Response);
    const answer = await askWhoami("sess_old");
    expect(answer.sessionId).toBe("sess_old");
    expect(answer.sessions).toEqual([]);
    expect(answer.ambiguous).toBe(false);
  });
});
