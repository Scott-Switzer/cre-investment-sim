/**
 * The finale payload the deployed service actually returns.
 *
 * The service forwards the engine's `finalize` verbatim, so a standing row is
 * named by team and carries no `portfolio_ltv`. These tests pin that shape: the
 * screens read `fund_id`/`fund_name`, and against the real payload they rendered a
 * nameless table and never highlighted the reader's own fund.
 */

import { describe, expect, it } from "vitest";

import { normalizeFinaleStandings } from "./api";

/** Copied from a live 310 finale on staging. */
const ENGINE_ROW = {
  rank: 1,
  team_id: "fund_2_d938a012ce704e9e8b93",
  team_name: "smoke-310 Fund 003",
  nav: 100,
  cash: 100,
  debt: 0,
  assets: 0,
  cumulative_return: 0,
};

describe("normalizeFinaleStandings", () => {
  it("resolves the fund identity from the engine's team names", () => {
    const [row] = normalizeFinaleStandings([ENGINE_ROW]);
    expect(row!.fund_id).toBe(ENGINE_ROW.team_id);
    expect(row!.fund_name).toBe(ENGINE_ROW.team_name);
  });

  it("treats an unpublished LTV as absent, never as zero", () => {
    const [row] = normalizeFinaleStandings([ENGINE_ROW]);
    expect(row!.portfolio_ltv).toBeNull();
  });

  it("preserves the published figures", () => {
    const [row] = normalizeFinaleStandings([ENGINE_ROW]);
    expect(row!.rank).toBe(1);
    expect(row!.nav).toBe(100);
    expect(row!.cumulative_return).toBe(0);
  });

  it("still accepts rows written with the older fund_* spelling", () => {
    const [row] = normalizeFinaleStandings([
      { rank: 2, fund_id: "fund_9", fund_name: "Laguna Advisors", nav: 98, cash: 90, debt: 5, assets: 1, cumulative_return: -0.02, portfolio_ltv: 0.64 },
    ]);
    expect(row!.fund_id).toBe("fund_9");
    expect(row!.fund_name).toBe("Laguna Advisors");
    expect(row!.portfolio_ltv).toBe(0.64);
  });

  it("prefers the engine's team identity when both spellings are present", () => {
    const [row] = normalizeFinaleStandings([
      { ...ENGINE_ROW, fund_id: "stale", fund_name: "Stale Name" },
    ]);
    expect(row!.fund_id).toBe(ENGINE_ROW.team_id);
    expect(row!.fund_name).toBe(ENGINE_ROW.team_name);
  });

  it("falls back to the id when a row carries no name at all", () => {
    const [row] = normalizeFinaleStandings([
      { rank: 3, team_id: "fund_7", nav: 95, cash: 95, debt: 0, assets: 0, cumulative_return: -0.05 },
    ]);
    expect(row!.fund_name).toBe("fund_7");
  });

  it("orders nothing and invents nothing for an empty board", () => {
    expect(normalizeFinaleStandings([])).toEqual([]);
  });
});
