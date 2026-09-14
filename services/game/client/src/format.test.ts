/**
 * Client unit tests: the rules a browser must keep even when the network is a mock.
 *
 * The e2e suite proves the flow against the real stack; these prove the invariants
 * cheaply — the phase router never lies, sealed state stays sealed on the professor's
 * screen, practice semantics render "transaction not booked" rather than "no sale",
 * and the two override counts stay distinct from the engine's won-only figure.
 */

import { describe, expect, it } from "vitest";

import { capitalImpact, money, pctSigned } from "./format";

// pctSigned is used for pp deltas (leverage overrides); pctSignedFormat in screens is
// the %-version. The two are deliberately distinct.

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

  it("formats signed percentage-point deltas with a real minus", () => {
    expect(pctSigned(0.086)).toBe("+8.6 pp");
    expect(pctSigned(-0.031)).toBe("−3.1 pp");
    expect(pctSigned(null)).toBe("—");
  });
});
