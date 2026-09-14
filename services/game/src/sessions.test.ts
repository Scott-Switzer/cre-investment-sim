/**
 * Sessions and identity.
 *
 * The theme is the recovery paths. Anonymous, device-bound identity is the right
 * trade for no accounts, but it means a cleared cookie loses a seat — so joining,
 * reclaiming and refusing all have to be legible rather than merely correct.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { startHarness, type Harness } from "./testing/harness.js";
import { createClass, joinClass } from "./testing/scenarios.js";
import { canonicalJoinCode, isJoinCodeShaped } from "./ids.js";

let harness: Harness;

beforeEach(async () => {
  harness = await startHarness();
});

afterEach(async () => {
  await harness.close();
});

describe("join codes", () => {
  it("avoids the characters people mis-hear and mistype", () => {
    const code = canonicalJoinCode("ABCDEFGHJKMNPQRTUVWXYZ2346789");
    expect(code).not.toMatch(/[ILOS015]/);
  });

  it("folds a code typed with the look-alikes onto the real one", () => {
    // "o1-8s" must reach the session whose code is "QJ8Z", or a student writing a
    // code down from a whiteboard is simply locked out.
    expect(canonicalJoinCode("o1-8s")).toBe(canonicalJoinCode("QJ8Z"));
    // Spaces and dashes are separators a student may add while reading a code aloud.
    expect(canonicalJoinCode(" ab cd ef ")).toBe("ABCDEF");
    expect(isJoinCodeShaped("ab cd ef")).toBe(true);
    expect(isJoinCodeShaped("ab cd")).toBe(false);
    expect(isJoinCodeShaped("abcdefghi")).toBe(false);
  });

  it("issues a code of the documented length", () => {
    return startHarness().then(async (h) => {
      const fixture = await createClass(h);
      expect(fixture.joinCode).toHaveLength(6);
      expect(fixture.joinCode).toBe(canonicalJoinCode(fixture.joinCode));
      await h.close();
    });
  });
});

describe("creating a class", () => {
  it("refuses the wrong professor passcode", async () => {
    const res = await harness.browser("nobody").post("/v1/sessions", {
      name: "Sneaky",
      professorPasscode: "not-the-passcode",
    });
    expect(res.status).toBe(403);
    expect(res.body.detail).toMatch(/passcode/);
  });

  it("refuses an unknown dataset rather than falling back to a default", async () => {
    const res = await harness.browser("prof").post("/v1/sessions", {
      name: "Wrong dataset",
      professorPasscode: "frenzel",
      bundleId: "does-not-exist",
    });
    expect(res.status).toBe(400);
    expect(res.body.detail).toMatch(/unknown dataset/);
  });

  it("chooses a bundle, and the pool it pins, at creation", async () => {
    // The pool is resolved before the class exists, so a dataset that will not load is
    // discovered by the professor and not at the first student upload.
    const fixture = await createClass(harness);
    const state = await fixture.professor.get(`/v1/sessions/${fixture.sessionId}/state`);
    expect(state.body.session.bundleId).toBe("test-bundle-v1");
    expect(state.body.session.poolCount).toBe(4);
    expect(state.body.session.candidatePoolHash).toBe("fake-pool-hash");
  });

  it("never exposes a seed a professor could choose", async () => {
    // Risk R3. The bundle carries a seed as engine metadata; no request field accepts
    // one, because a different seed keeps property ids and changes what they mean.
    const list = await harness.browser("prof").get("/v1/bundles");
    expect(list.status).toBe(200);
    expect(list.body.bundles[0]).not.toHaveProperty("seed");
    // Exactly the engine's own BundleSummary: identity, the packet and economics it
    // pairs, and nothing that could select a pool.
    expect(Object.keys(list.body.bundles[0]).sort()).toEqual([
      "bundle_id",
      "description",
      "display_name",
      "economics_version",
      "packet_version",
    ]);
  });
});

describe("joining", () => {
  it("puts two students in the same fund when they name the same fund", async () => {
    const fixture = await createClass(harness, { fundNames: ["Value Fund"] });
    const dana = await joinClass(harness, {
      joinCode: fixture.joinCode,
      displayName: "Dana",
      newFundName: "Value Fund",
    });
    const ravi = await joinClass(harness, {
      joinCode: fixture.joinCode,
      displayName: "Ravi",
      fundId: dana.fundId,
    });
    expect(ravi.fundId).toBe(dana.fundId);

    const state = await dana.browser.get(`/v1/sessions/${fixture.sessionId}/state`);
    expect(state.body.funds).toHaveLength(1);
    expect(state.body.funds[0].memberCount).toBe(2);
  });

  it("refuses an unknown join code with the code it was given", async () => {
    const res = await harness.browser("Dana").post("/v1/join", {
      joinCode: "ZZZZZZ",
      displayName: "Dana",
      newFundName: "Value Fund",
    });
    expect(res.status).toBe(404);
    expect(res.body.detail).toMatch(/ZZZZZZ/);
    expect(res.body.detail).toMatch(/professor/);
  });

  it("refuses a malformed join code before doing any lookup", async () => {
    const res = await harness.browser("Dana").post("/v1/join", {
      joinCode: "ab",
      displayName: "Dana",
      newFundName: "Value Fund",
    });
    expect(res.status).toBe(400);
    expect(res.body.detail).toMatch(/six-character/);
  });

  it("refuses a join with no display name", async () => {
    const fixture = await createClass(harness);
    const res = await harness.browser("anon").post("/v1/join", {
      joinCode: fixture.joinCode,
      displayName: "   ",
      newFundName: "Value Fund",
    });
    expect(res.status).toBe(400);
    expect(res.body.detail).toMatch(/display name/);
  });

  it("makes a student choose a fund rather than defaulting one silently", async () => {
    const fixture = await createClass(harness);
    const res = await harness.browser("Dana").post("/v1/join", {
      joinCode: fixture.joinCode,
      displayName: "Dana",
      newFundName: "",
    });
    expect(res.status).toBe(400);
    expect(res.body.detail).toMatch(/choose a fund to join/);
  });

  it("creates a new fund when the name is new", async () => {
    const fixture = await createClass(harness, { fundNames: ["Value Fund"] });
    const result = await joinClass(harness, {
      joinCode: fixture.joinCode,
      displayName: "Dana",
      newFundName: "Growth Fund",
    });
    const state = await result.browser.get(`/v1/sessions/${fixture.sessionId}/state`);
    expect(state.body.funds.map((f: { name: string }) => f.name)).toEqual([
      "Growth Fund",
      "Value Fund",
    ]);
  });
});

describe("authentication", () => {
  it("refuses state for a session the cookie was not issued for", async () => {
    const one = await createClass(harness);
    const two = await createClass(harness);
    const student = await joinClass(harness, { joinCode: one.joinCode, displayName: "Dana" });

    // Borrow the student's cookie value for a different session's cookie name.
    const stolen = [...student.browser.cookies.values()][0]!;
    const forged = harness.browser("attacker");
    forged.cookies.set(`cre_test_${two.sessionId}`, stolen);

    const res = await forged.get(`/v1/sessions/${two.sessionId}/state`);
    expect(res.status).toBe(403);
    expect(res.body.detail).toMatch(/different session/);
  });

  it("refuses a tampered cookie", async () => {
    const fixture = await createClass(harness);
    const student = await joinClass(harness, { joinCode: fixture.joinCode, displayName: "Dana" });
    const [name, value] = [...student.browser.cookies.entries()][0]!;
    // Flip the payload while keeping the signature field shape.
    const tampered = forgedGrant(value);
    const attacker = harness.browser("attacker");
    attacker.cookies.set(name, tampered);
    const res = await attacker.get(`/v1/sessions/${fixture.sessionId}/state`);
    expect(res.status).toBe(401);
  });

  it("refuses an anonymous request", async () => {
    const fixture = await createClass(harness);
    const res = await harness.browser("anon").get(`/v1/sessions/${fixture.sessionId}/state`);
    expect(res.status).toBe(401);
  });

  it("lets a professor get back in after a browser refresh", async () => {
    const fixture = await createClass(harness);
    const fresh = harness.browser("professor-again");
    const signIn = await fresh.post(`/v1/sessions/${fixture.sessionId}/professor`, {
      passcode: "frenzel",
      displayName: "Professor Frenzel",
    });
    expect(signIn.status).toBe(200);
    const state = await fresh.get(`/v1/sessions/${fixture.sessionId}/state`);
    expect(state.status).toBe(200);
    expect(state.body.you.role).toBe("professor");
    expect(state.body.session.joinCode).toBe(fixture.joinCode);
  });

  it("reclaims a seat by display name when a browser has lost its cookies", async () => {
    const fixture = await createClass(harness);
    const dana = await joinClass(harness, {
      joinCode: fixture.joinCode,
      displayName: "Dana",
      newFundName: "Value Fund",
    });
    const freshBrowser = harness.browser("Dana's new laptop");
    const res = await freshBrowser.post(`/v1/sessions/${fixture.sessionId}/reclaim`, {
      displayName: "dana",
    });
    expect(res.status).toBe(200);
    expect(res.body.fundId).toBe(dana.fundId);
    const state = await freshBrowser.get(`/v1/sessions/${fixture.sessionId}/state`);
    expect(state.body.you.displayName).toBe("Dana");
  });

  it("refuses to reclaim a seat that does not exist", async () => {
    const fixture = await createClass(harness);
    const res = await harness.browser("stranger").post(
      `/v1/sessions/${fixture.sessionId}/reclaim`,
      { displayName: "Nobody" },
    );
    expect(res.status).toBe(404);
  });

  it("requires a passcode to list a professor's sessions", async () => {
    expect((await harness.browser("x").get("/v1/sessions")).status).toBe(403);
    const ok = await harness.browser("prof").get("/v1/sessions", {
      "x-professor-passcode": "frenzel",
    });
    expect(ok.status).toBe(200);
    expect(Array.isArray(ok.body.sessions)).toBe(true);
  });

  it("reports a seat that no longer exists distinctly from one that is not signed in", async () => {
    // The distinction the client needs: "join again" versus "sign in".
    const fixture = await createClass(harness);
    const student = await joinClass(harness, { joinCode: fixture.joinCode, displayName: "Dana" });
    const store = harness.store.inspect(fixture.sessionId)!;
    store.members.delete(student.memberId);
    const res = await student.browser.get(`/v1/sessions/${fixture.sessionId}/state`);
    expect(res.status).toBe(401);
    expect(res.body.detail).toMatch(/seat no longer exists/);
  });
});

/** Break the signature so the server has to reject it on the MAC, not on shape. */
function forgedGrant(token: string): string {
  const [payload, signature] = token.split(".");
  if (!payload || !signature) throw new Error("unexpected cookie shape");
  const decoded = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
  decoded.fundId = "fund_someone_elses";
  const forged = Buffer.from(JSON.stringify(decoded)).toString("base64url");
  return `${forged}.${signature}`;
}
