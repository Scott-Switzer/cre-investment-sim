/**
 * Client unit tests: the rules a browser must keep even when the network is a mock.
 *
 * The e2e suite proves the flow against the real stack; these prove the invariants
 * cheaply — the phase router never lies, sealed state stays sealed on the professor's
 * screen, practice semantics render "transaction not booked" rather than "no sale",
 * and the two override counts stay distinct from the engine's won-only figure.
 */

import { describe, expect, it } from "vitest";

import { capitalImpact, debtYieldAt, money, pctSigned, signedPercent, signedPoints } from "./format";

describe("presentation arithmetic", () => {
  it("capital impact follows the engine's published rule", () => {
    // equity = price × (1 − ltv); deal costs = price × 2% — equity_required_for()
    const impact = capitalImpact(43.6, 0.58, 0.02);
    expect(impact.loan).toBeCloseTo(43.6 * 0.58, 6);
    expect(impact.equity).toBeCloseTo(43.6 * 0.42, 6);
    expect(impact.dealCosts).toBeCloseTo(0.872, 6);
    expect(impact.total).toBeCloseTo(43.6 * 0.42 + 0.872, 6);
  });

  it("formats money on the $M scale the game speaks", () => {
    expect(money(100)).toBe("$100.0M");
    expect(money(0)).toBe("$0.0M");
    expect(money(-4.5)).toBe("−$4.5M");
    expect(money(null)).toBe("—");
    expect(money(1500)).toBe("$1.5B");
  });
});

describe("percentage semantics", () => {
  it("signedPercent emits % for rates: upside, growth, valuation error", () => {
    expect(signedPercent(0.086)).toBe("+8.6%");
    expect(signedPercent(-0.031)).toBe("−3.1%");
    expect(signedPercent(0)).toBe("+0.0%");
    expect(signedPercent(null)).toBe("—");
  });

  it("signedPoints emits pp only for differences between rates", () => {
    expect(signedPoints(0.03)).toBe("+3.0 pp");
    expect(signedPoints(-0.012)).toBe("−1.2 pp");
    expect(signedPoints(null)).toBe("—");
  });

  it("pctSigned (legacy alias) now emits % — never pp", () => {
    // A rate like predicted upside must never read "+3.3 pp".
    expect(pctSigned(0.033)).toBe("+3.3%");
    expect(pctSigned(-0.078)).toBe("−7.8%");
  });
});

describe("debt yield", () => {
  it("is NOI ÷ loan amount, not NOI ÷ price", () => {
    // Known deal: NOI 2.1, ask 43.2, max LTV 0.65.
    // Cap rate = 2.1/43.2 = 4.86%; debt yield = 2.1/(43.2×0.65) = 7.48%.
    const noi = 2.1;
    const ask = 43.2;
    const maxLtv = 0.65;
    expect(debtYieldAt(noi, ask, maxLtv)).toBeCloseTo(2.1 / (43.2 * 0.65), 8);
    // And it must NOT equal the cap rate.
    expect(debtYieldAt(noi, ask, maxLtv)).not.toBeCloseTo(2.1 / 43.2, 8);
  });

  it("handles missing inputs without throwing", () => {
    expect(debtYieldAt(null, 43.2, 0.65)).toBeNull();
    expect(debtYieldAt(2.1, null, 0.65)).toBeNull();
    expect(debtYieldAt(2.1, 43.2, null)).toBeNull();
    expect(debtYieldAt(2.1, 0, 0.65)).toBeNull();
  });
});
