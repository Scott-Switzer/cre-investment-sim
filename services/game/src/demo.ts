/**
 * Demo mode: one human fund against three deterministic bot funds.
 *
 * Boundaries kept deliberately narrow. The engine is still the only adjudicator —
 * bot "models" are ordinary prediction rows like any student's, and bot "decisions"
 * are ordinary DecisionItems derived from those rows. What lives here is the demo
 * scaffolding the engine cannot provide: the bot archetypes, their deterministic
 * model rows over the candidate pool, and their deterministic submissions.
 * No economics, no NAV arithmetic, no auction logic.
 *
 * Bots are pure functions of (model row, offered deal). They never look at the
 * human's submissions and never see hidden state; a bot that loses is a bot whose
 * policy lost, which is the point of the demo.
 */

import type { DecisionItem } from "./domain.js";

export const DEMO_BOT_NAMES = ["Value Partners", "Growth Alliance", "Risk Counsel"] as const;

export interface BotArchetype {
  /** fair value = ask × factor */
  valueFactor: number;
  /** bid discipline: max bid = fair value × discipline */
  bidDiscipline: number;
  /** target LTV */
  ltv: number;
  /** predicted NOI growth */
  noiGrowth: number;
  /** downside probability */
  downside: number;
  /** Bid only when the model's own max bid clears ask × this threshold. */
  minUpside: number;
}

const ARCHETYPES: Record<(typeof DEMO_BOT_NAMES)[number], BotArchetype> = {
  "Value Partners": {
    valueFactor: 0.98,
    bidDiscipline: 0.95,
    ltv: 0.55,
    noiGrowth: 0.022,
    downside: 0.28,
    minUpside: 0.96,
  },
  "Growth Alliance": {
    valueFactor: 1.05,
    bidDiscipline: 1.0,
    ltv: 0.65,
    noiGrowth: 0.041,
    downside: 0.41,
    minUpside: 0.98,
  },
  "Risk Counsel": {
    valueFactor: 0.93,
    bidDiscipline: 0.88,
    ltv: 0.5,
    noiGrowth: 0.013,
    downside: 0.55,
    minUpside: 1.02,
  },
};

/** The human's clearly-marked demo forecast — never presented as user-built. */
export const HUMAN_ARCHETYPE: BotArchetype = {
  valueFactor: 0.97,
  bidDiscipline: 0.92,
  ltv: 0.6,
  noiGrowth: 0.028,
  downside: 0.33,
  minUpside: 0.97,
};

export function demoBotArchetype(fundName: string): BotArchetype {
  return (
    ARCHETYPES[fundName as (typeof DEMO_BOT_NAMES)[number]] ?? ARCHETYPES["Value Partners"]
  );
}

export interface DemoPoolDeal {
  property_id: string;
  asking_price: number | null;
  max_ltv: number | null;
}

export interface DemoModelRow {
  propertyId: string;
  forecast: {
    modelName: string;
    predictedFairValue: number;
    predictedNoiGrowth: number;
    probabilityOfDownside: number | null;
    confidence: number | null;
  };
  policy: { maxBid: number; targetLtv: number };
}

/** Deterministic model rows for one archetype over the candidate pool. */
export function demoModelRows(
  archetype: BotArchetype,
  pool: DemoPoolDeal[],
  modelName: string,
): DemoModelRow[] {
  return pool
    .filter((p) => p.asking_price !== null && Number.isFinite(p.asking_price))
    .map((p) => {
      const ask = p.asking_price ?? 10;
      const fairValue = round6(ask * archetype.valueFactor);
      const maxBid = round6(fairValue * archetype.bidDiscipline);
      return {
        propertyId: p.property_id,
        forecast: {
          modelName,
          predictedFairValue: fairValue,
          predictedNoiGrowth: archetype.noiGrowth,
          probabilityOfDownside: archetype.downside,
          confidence: 0.7,
        },
        policy: { maxBid, targetLtv: archetype.ltv },
      };
    });
}

/**
 * A bot's submission for the offered deals: bid at its own policy price when the
 * deal clears its upside threshold, pass otherwise. Pure function of (archetype,
 * model rows, offered deals) — the same call always produces the same submission.
 */
export function demoBotDecision(
  archetype: BotArchetype,
  rows: Map<string, DemoModelRow>,
  offered: { property_id: string; asking_price: number | null; max_ltv: number | null }[],
): DecisionItem[] {
  return offered.map((deal) => {
    const row = rows.get(deal.property_id);
    const ask = deal.asking_price;
    if (!row || ask === null || !Number.isFinite(ask)) {
      return { propertyId: deal.property_id, action: "PASS", bid: null, ltv: null };
    }
    const threshold = ask * archetype.minUpside;
    if (row.policy.maxBid < threshold) {
      return { propertyId: deal.property_id, action: "PASS", bid: null, ltv: null };
    }
    const ltvCeiling = deal.max_ltv ?? row.policy.targetLtv;
    return {
      propertyId: deal.property_id,
      action: "BID",
      bid: row.policy.maxBid,
      ltv: round6(Math.min(row.policy.targetLtv, ltvCeiling)),
    };
  });
}

function round6(value: number): number {
  return Math.round(value * 1e6) / 1e6;
}
