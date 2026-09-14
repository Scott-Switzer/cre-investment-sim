/**
 * A contract-shaped fake engine.
 *
 * The distributed-state suite is about revisions, locks, idempotency and races —
 * none of which involve CRE economics. Driving those tests through the real Python
 * engine would make a 20-second loop out of what should be 200 ms, and would make
 * failures harder to read because a game result would be in the diff.
 *
 * So this fake implements the *shape* of the engine's contract — the same request and
 * response fields, the same determinism, the same refusal to reveal a reserve before
 * resolution — and nothing about the economics. The milestone suite uses the real
 * engine, and the contract suite pins the two shapes together.
 *
 * It is deliberately observable: `calls` records every invocation, which is how the
 * tests assert that a double-clicked resolve produced one resolution even though the
 * engine was legitimately called twice.
 */

import type {
  BundleSummary,
  CreateGameResponse,
  Engine,
  EngineBundle,
  EngineDecision,
  EngineHealth,
  EngineTeamSpec,
  OpenRoundResponse,
  PoolProperty,
  PoolResponse,
  ResolveRoundResponse,
} from "../engineClient.js";

const BUNDLE_ID = "test-bundle-v1";

export const FAKE_POOL: PoolProperty[] = [
  pool("P1", "Test Industrial A", "Industrial", "North", 10, 0.6),
  pool("P2", "Test Industrial B", "Industrial", "South", 20, 0.6),
  pool("P3", "Test Office A", "Office", "North", 30, 0.55),
  pool("P4", "Test Office B", "Office", "South", 40, 0.55),
];

function pool(
  id: string,
  name: string,
  type: string,
  submarket: string,
  ask: number,
  maxLtv: number,
): PoolProperty {
  return {
    property_id: id,
    property_name: name,
    property_type: type,
    submarket,
    asking_price: ask,
    max_ltv: maxLtv,
    current_noi: Math.round(ask * 0.06 * 1e6) / 1e6,
    going_in_cap: 0.06,
    debt_rate: 0.062,
    occupancy: 0.9,
    building_sf: 50_000,
    units: null,
    year_built: 1998,
    acquisition_cost_rate: 0.02,
    capital_reserve_rate: 0.008,
    capital_reserve_rate_note: "fake engine",
  };
}

/** Practice offers P1; each scored round offers two of the remaining properties. */
export function dealsForRound(round: number): PoolProperty[] {
  if (round < 0) return FAKE_POOL.filter((p) => p.property_id === "P1");
  const start = 1 + ((round * 2) % 3);
  const ids = [FAKE_POOL[start % 4]!.property_id, FAKE_POOL[(start + 1) % 4]!.property_id];
  return FAKE_POOL.filter((p) => ids.includes(p.property_id));
}

interface FakeState {
  round: number;
  resolvedRounds: number;
  fundIds: string[];
  cash: Record<string, number>;
  firstRoundWinners: string[] | null;
}

function publicRound(state: FakeState, round: number) {
  const deals = dealsForRound(round);
  return {
    round_number: round,
    stage: round < 0 ? "practice" : `round_${round + 1}`,
    is_practice: round < 0,
    round_state: "open",
    total_rounds: 4,
    // No reserve, no future outcome: the fake is as strict about this as the real
    // engine, so a leak test against it means something.
    deals: deals.map((d) => ({ ...d })),
    market: { round_number: round, policy_rate: 0.045, vacancy: { Office: 0.11 } },
    funds: state.fundIds.map((id) => ({
      team_id: id,
      team_name: id,
      nav: state.cash[id] ?? 100,
      cash: state.cash[id] ?? 100,
      debt: 0,
      assets: 0,
      cumulative_return: 0,
    })),
    economics: { acquisition_cost_rate: 0.02, capital_reserve_rate: { Office: 0.012 } },
  };
}

export class FakeEngine implements Engine {
  calls: { method: string; args: unknown }[] = [];
  /** Set to make the next call fail, for exercising the engine-failure path. */
  failNext: string | null = null;
  readonly bundle: EngineBundle = {
    bundle_id: BUNDLE_ID,
    display_name: "Test Dataset",
    engine_version: "test",
    economics_version: "test",
    economics_digest: "test-digest",
    packet_version: BUNDLE_ID,
    seed: 1234,
    candidate_pool_hash: "fake-pool-hash",
    schema_version: 1,
    description: "fake",
  };

  reset(): void {
    this.calls = [];
  }

  count(method: string): number {
    return this.calls.filter((c) => c.method === method).length;
  }

  private record(method: string, args: unknown): void {
    this.calls.push({ method, args });
    if (this.failNext === method) {
      this.failNext = null;
      const err = new Error(`fake engine failure in ${method}`);
      err.name = "FetchError";
      throw err;
    }
  }

  async health(): Promise<EngineHealth> {
    return {
      status: "ok",
      game: "cre-investment-committee",
      engine_version: "test",
      economics_version: "test",
      economics_digest: "test-digest",
      schema_version: 1,
      serde_schema_version: 2,
    };
  }

  /**
   * Returns the *summary* shape, exactly as the real engine does — no seed, no
   * hashes. An earlier version of this fake returned the whole bundle, which made the
   * "a professor can never choose a seed" test pass for the wrong reason: a fake that
   * is looser than the real engine hides precisely the leaks worth catching.
   */
  async listBundles(): Promise<{ bundles: BundleSummary[] }> {
    return {
      bundles: [
        {
          bundle_id: this.bundle.bundle_id,
          display_name: this.bundle.display_name,
          packet_version: this.bundle.packet_version,
          economics_version: this.bundle.economics_version,
          description: this.bundle.description,
        },
      ],
    };
  }

  async bundlePool(bundleId: string): Promise<PoolResponse> {
    this.record("bundlePool", { bundleId });
    if (bundleId !== BUNDLE_ID) throw new Error(`unknown bundle '${bundleId}'`);
    return {
      bundle: this.bundle,
      candidate_pool_hash: this.bundle.candidate_pool_hash,
      pool_count: FAKE_POOL.length,
      properties: FAKE_POOL,
    };
  }

  async createGameState(
    bundleId: string,
    teams: EngineTeamSpec[],
    scenario = "Base Case",
  ): Promise<CreateGameResponse> {
    this.record("createGameState", { bundleId, teams, scenario });
    const state: FakeState = {
      round: -1,
      resolvedRounds: 0,
      fundIds: teams.map((t) => t.team_id).sort(),
      cash: Object.fromEntries(teams.map((t) => [t.team_id, 100])),
      firstRoundWinners: null,
    };
    return { bundle: this.bundle, state, public: publicRound(state, -1) };
  }

  async openRound(state: unknown): Promise<OpenRoundResponse> {
    this.record("openRound", { state });
    const current = state as FakeState;
    const round = current.round + 1;
    if (round >= 4) {
      return { state: current, public: publicRound(current, current.round), game_complete: true };
    }
    const next: FakeState = { ...current, round };
    return { state: next, public: publicRound(next, round), game_complete: false };
  }

  async resolveRound(
    state: unknown,
    decisions: EngineDecision[],
  ): Promise<ResolveRoundResponse> {
    this.record("resolveRound", { state, decisions });
    const current = state as FakeState;
    const round = current.round;
    const deals = dealsForRound(round);

    const auctions = deals.map((deal) => {
      const ask = deal.asking_price ?? 0;
      const reserve = Math.round(ask * 0.85 * 1e6) / 1e6;
      const bids = decisions
        .filter((d) => d.property_id === deal.property_id && d.action === "BID")
        .map((d) => ({ ...d, bid: d.bid ?? 0, ltv: d.ltv ?? 0.6 }));
      // Deterministic: highest price, and a tie broken by the lower leverage — the
      // same rule the real engine documents, so tests exercise the same edge case.
      const ranked = [...bids].sort((a, b) => b.bid - a.bid || a.ltv - b.ltv);
      const winner = ranked.find((b) => b.bid >= reserve) ?? null;
      const cap = 0.06;
      const realized = winner ? Math.round(winner.bid * 1.03 * 1e6) / 1e6 : null;
      return {
        property_id: deal.property_id,
        sold: winner !== null,
        reason: winner ? "sold" : bids.length ? "below_reserve" : "no_bids",
        winning_team_id: winner?.team_id ?? null,
        winning_bid: winner?.bid ?? null,
        winning_ltv: winner?.ltv ?? null,
        // Revealed only here: the reserve is absent from `publicRound`.
        reserve_price: reserve,
        realized_value: realized,
        realized_noi: realized === null ? null : Math.round(realized * cap * 1e6) / 1e6,
        noi_growth_actual: winner ? 0.02 : null,
        cap_rate_actual: winner ? cap : null,
        asking_price: ask,
      };
    });

    const cash = { ...current.cash };
    for (const a of auctions) {
      if (a.sold && a.winning_team_id && a.winning_bid !== null) {
        cash[a.winning_team_id] = Math.round((cash[a.winning_team_id]! - a.winning_bid) * 1e6) / 1e6;
      }
    }
    const next: FakeState = {
      ...current,
      resolvedRounds: round < 0 ? current.resolvedRounds : current.resolvedRounds + 1,
      cash,
    };

    const pnl = current.fundIds.map((id) => ({
      team_id: id,
      team_name: id,
      nav: cash[id] ?? 100,
      cumulative_return: 0,
      value_channel: 0,
      noi_income: 0,
      interest_paid: 0,
      acquisition_costs: 0,
      reserves: 0,
      net_carry: 0,
      gross_ltv: 0,
      weighted_debt_rate: 0,
      return_on_cost: 0,
      assets: 0,
    }));

    return {
      state: next,
      public_results: {
        round_number: round,
        auctions,
        pnl,
        standings: [...next.fundIds]
          .sort((a, b) => (cash[b] ?? 0) - (cash[a] ?? 0))
          .map((id, i) => ({
            rank: i + 1,
            team_id: id,
            team_name: id,
            nav: cash[id] ?? 0,
            cash: cash[id] ?? 0,
            debt: 0,
            assets: 0,
            cumulative_return: 0,
          })),
      },
      analytics_updates: [],
      rejected_decisions: this.rejectionsFor(decisions, deals, current),
      game_complete: round >= 3,
    };
  }

  /**
   * Mimics the real engine's legality rules that a student can trip: an LTV above the
   * property's own ceiling, and a bid the fund cannot fund. The second is important
   * to reproduce here — it is the refusal a student meets in class, and the one the
   * game service deliberately does not pre-empt because it is the engine's rule.
   */
  private rejectionsFor(
    decisions: EngineDecision[],
    deals: PoolProperty[],
    state: FakeState,
  ): { team_id: string; property_id: string; reason: string }[] {
    const out: { team_id: string; property_id: string; reason: string }[] = [];
    for (const d of decisions) {
      if (d.action !== "BID" || d.bid == null || d.ltv == null) continue;
      const bid = d.bid;
      const ltv = d.ltv;
      const deal = deals.find((p) => p.property_id === d.property_id);
      if (!deal) {
        out.push({ team_id: d.team_id, property_id: d.property_id, reason: "not in this round" });
        continue;
      }
      if ((deal.max_ltv ?? 1) < ltv - 1e-9) {
        out.push({
          team_id: d.team_id,
          property_id: d.property_id,
          reason: "LTV above the property ceiling",
        });
        continue;
      }
      if ((state.cash[d.team_id] ?? 0) < bid) {
        out.push({
          team_id: d.team_id,
          property_id: d.property_id,
          reason: "insufficient equity",
        });
      }
    }
    return out;
  }

  async teamView(state: unknown, teamId: string): Promise<Record<string, unknown>> {
    this.record("teamView", { state, teamId });
    return { team_id: teamId };
  }
}
