/**
 * Professor session export: clean CSVs of everything already revealed.
 *
 * Deliberately narrow: it reads only the game service's own aggregate (session,
 * funds, members, rounds, decisions) plus the finalized debrief payload. It never
 * decodes hidden engine state, never exports cookies/secrets, and includes reserve
 * values only when they are part of the revealed round results the engine already
 * published. The ZIP writer is store-only (no compression) so it needs no
 * dependencies; payloads are a few hundred KB at class scale.
 */

import type { AppContext } from "./context.js";
import type { SessionState } from "./domain.js";
import type { DecisionState } from "./domain.js";
import { PRACTICE_ROUND } from "./domain.js";
import { notFound } from "./errors.js";

function csv(rows: (string | number | null)[][]): string {
  return rows
    .map((row) =>
      row
        .map((cell) => {
          if (cell === null) return "";
          const text = String(cell);
          return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
        })
        .join(","),
    )
    .join("\n");
}

function money(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "";
  return value.toFixed(2);
}

function pct(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "";
  return (value * 100).toFixed(3);
}

type Results = Record<string, unknown>;

function asResults(value: unknown): Results {
  return (value ?? {}) as Results;
}

function asList(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? (value as Record<string, unknown>[]) : [];
}

export interface ExportBundle {
  filename: string;
  files: { name: string; content: string }[];
}

export async function buildExport(ctx: AppContext, session: SessionState): Promise<ExportBundle> {
  const sessionId = session.id;
  const rounds = await ctx.store.listRounds(sessionId);
  const models = await ctx.store.listAllModels(sessionId);
  const members = await ctx.store.transact(sessionId, (tx) => [...tx.aggregate.members.values()]);
  const funds = await ctx.store.transact(sessionId, (tx) => [...tx.aggregate.funds.values()]);
  const decisionsByRound = new Map<number, DecisionState[]>();
  for (const round of rounds) {
    decisionsByRound.set(round.round, await ctx.store.listDecisions(sessionId, round.round));
  }

  // 1. session summary
  const sessionSummary = csv([
    ["field", "value"],
    ["session_id", session.id],
    ["name", session.name],
    ["bundle_id", session.bundleId],
    ["bundle", session.bundleDisplayName],
    ["mode", session.mode],
    ["max_team_size", session.maxTeamSize],
    ["total_rounds", session.totalRounds],
    ["practice_enabled", session.practiceEnabled ? "yes" : "no"],
    ["created_at", session.createdAt],
    ["finalized_at", session.finalizedAt ?? ""],
  ]);

  // 2. fund standings — final after finalize, otherwise last revealed round.
  const finale = asResults(session.finale);
  const standings = asList(finale.standings);
  const standingById = new Map(standings.map((row) => [String(row.fund_id ?? row.team_id), row]));
  const fundFinal = csv([
    [
      "rank",
      "fund",
      "members",
      "nav",
      "cash",
      "debt",
      "assets",
      "return",
      "portfolio_ltv",
    ],
    ...funds
      .map((fund) => {
        const row = standingById.get(fund.id);
        return {
          fund,
          row,
          rank: standings.findIndex((s) => String(s.fund_id ?? s.team_id) === fund.id) + 1,
        };
      })
      .sort((a, b) => a.rank - b.rank)
      .map(({ fund, row }) => [
        row ? standings.findIndex((s) => String(s.fund_id ?? s.team_id) === fund.id) + 1 : "",
        fund.name,
        members.filter((m) => m.fundId === fund.id).map((m) => m.displayName).join(" | "),
        row ? money(row.nav) : "",
        row ? money(row.cash) : "",
        row ? money(row.debt) : "",
        row ? money(row.assets ?? row.asset_value) : "",
        row ? pct(row.cumulative_return ?? row.total_return) : "",
        row ? pct(row.portfolio_ltv ?? row.gross_ltv) : "",
      ]),
  ]);

  // 3. round decisions — every fund's submission per round, revealed or not:
  // these are the exporter's own fund's data, so no sealing concern.
  const roundDecisionRows: (string | number | null)[][] = [
    ["round", "fund", "property_id", "action", "bid", "ltv"],
  ];
  for (const round of rounds) {
    for (const decision of decisionsByRound.get(round.round) ?? []) {
      for (const item of decision.items) {
        roundDecisionRows.push([
          round.round === PRACTICE_ROUND ? "practice" : round.round,
          funds.find((f) => f.id === decision.fundId)?.name ?? decision.fundId,
          item.propertyId,
          item.action,
          item.bid,
          item.ltv,
        ]);
      }
    }
  }
  const roundDecisions = csv(roundDecisionRows);

  // 3b. management stances — what each fund chose to do with the buildings it owned.
  // Empty for a tier that has no management decision, and written as an empty file
  // (header only) rather than omitted, so the export's shape does not change with the
  // course tier.
  const roundStanceRows: (string | number | null)[][] = [
    ["round", "fund", "property_id", "stance"],
  ];
  for (const round of rounds) {
    for (const decision of decisionsByRound.get(round.round) ?? []) {
      for (const stance of decision.stances ?? []) {
        roundStanceRows.push([
          round.round === PRACTICE_ROUND ? "practice" : round.round,
          funds.find((f) => f.id === decision.fundId)?.name ?? decision.fundId,
          stance.propertyId,
          stance.stance,
        ]);
      }
    }
  }
  const roundStances = csv(roundStanceRows);

  // 4. round results — property outcomes, only from revealed results.
  const resultRows: (string | number | null)[][] = [
    [
      "round",
      "property_id",
      "sold",
      "winning_fund",
      "winning_bid",
      "seller_reserve",
      "your_bid",
      "realized_yr1_value",
      "realized_noi_growth",
      "year_end_cap_rate",
    ],
  ];
  for (const round of rounds) {
    if (!round.results) continue;
    const results = asResults(round.results);
    const outcomes = asList(results.properties ?? results.property_outcomes);
    const auctions = asList(results.auctions ?? results.outcomes);
    for (const outcome of outcomes) {
      const auction = auctions.find(
        (a) => String(a.property_id ?? a.id) === String(outcome.property_id ?? outcome.id),
      );
      resultRows.push([
        round.round === PRACTICE_ROUND ? "practice" : round.round,
        String(outcome.property_id ?? outcome.id ?? ""),
        auction ? (auction.sold ?? auction.winning_bid !== null ? "yes" : "no") : "",
        auction ? String(auction.winning_team_name ?? auction.winning_fund ?? "") : "",
        auction ? money(auction.winning_bid) : "",
        auction ? money(auction.seller_reserve) : "",
        String(outcome.your_bid ?? outcome.student_bid ?? ""),
        money(outcome.realized_yr1_value ?? outcome.exit_value ?? outcome.realized_value),
        pct(outcome.realized_noi_growth ?? outcome.noi_growth),
        pct(outcome.year_end_cap_rate ?? outcome.exit_cap_rate),
      ]);
    }
  }
  const roundResults = csv(resultRows);

  // 5. model metrics — per fund, from the finalize analytics where present.
  const analytics = asList(finale.analytics);
  const modelRows: (string | number | null)[][] = [
    [
      "fund",
      "model",
      "rows",
      "valuation_mae",
      "noi_growth_mae",
      "downside_calibration",
      "decision_overrides",
      "invested_overrides",
      "policy_discipline_rate",
    ],
  ];
  for (const fund of funds) {
    const model = models.find((m) => m.fundId === fund.id);
    const row = analytics.find(
      (a) => String(a.fund_id ?? a.team_id) === fund.id || String(a.fund) === fund.name,
    );
    modelRows.push([
      fund.name,
      model?.modelName ?? "",
      model?.rowCount ?? "",
      row ? money(row.valuation_mae ?? row.mean_error) : "",
      row ? pct(row.noi_growth_mae) : "",
      row ? pct(row.downside_calibration ?? row.brier_score) : "",
      row ? String(row.decision_overrides ?? row.overrides ?? "") : "",
      row ? String(row.invested_overrides ?? row.invested_override_count ?? "") : "",
      row ? pct(row.policy_discipline_rate) : "",
    ]);
  }
  const modelMetrics = csv(modelRows);

  // 6. override metrics — per fund per round where the engine's finalized
  // debrief breaks them out; otherwise the fund-level tallies above suffice.
  const debrief = asResults(finale.debrief);
  const overrideRows: (string | number | null)[][] = [
    ["fund", "decision_overrides", "invested_overrides", "policy_discipline_rate"],
  ];
  const debriefOverrides = asList(debrief.override_summary ?? debrief.overrides);
  for (const row of debriefOverrides) {
    overrideRows.push([
      String(row.fund_id ?? row.team_id ?? row.fund ?? ""),
      String(row.decision_overrides ?? row.overrides ?? ""),
      String(row.invested_overrides ?? ""),
      pct(row.policy_discipline_rate),
    ]);
  }
  const overrideMetrics = csv(overrideRows);

  const files = [
    { name: "session_summary.csv", content: sessionSummary },
    { name: "fund_final_standings.csv", content: fundFinal },
    { name: "round_decisions.csv", content: roundDecisions },
    { name: "round_management_stances.csv", content: roundStances },
    { name: "round_results.csv", content: roundResults },
    { name: "model_metrics.csv", content: modelMetrics },
    { name: "override_metrics.csv", content: overrideMetrics },
  ];

  return {
    filename: `cre-investment-committee-${session.name.replace(/[^\w.-]+/g, "-").slice(0, 48)}.zip`,
    files,
  };
}

/**
 * Minimal store-only ZIP. Each entry: local header, raw (uncompressed) bytes,
 * central directory. CRC-32 is required by strict readers.
 */
export function zipStore(files: { name: string; content: string }[]): Buffer {
  const chunks: Buffer[] = [];
  const central: Buffer[] = [];
  const encoder = new TextEncoder();
  let offset = 0;

  const crcTable = (() => {
    const table = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      table[n] = c >>> 0;
    }
    return table;
  })();

  const crc32 = (bytes: Uint8Array): number => {
    let c = 0xffffffff;
    for (const b of bytes) c = crcTable[(c ^ b) & 0xff]! ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  };

  for (const file of files) {
    const name = Buffer.from(file.name, "utf8");
    const data = Buffer.from(encoder.encode(file.content));
    const crc = crc32(data);
    const now = new Date();
    const dosTime = ((now.getHours() << 11) | (now.getMinutes() << 5) | (now.getSeconds() >> 1)) & 0xffff;
    const dosDate =
      (((now.getFullYear() - 1980) << 9) | ((now.getMonth() + 1) << 5) | now.getDate()) & 0xffff;

    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(0x0800, 6); // UTF-8 names
    local.writeUInt16LE(0, 8); // stored
    local.writeUInt16LE(dosTime, 10);
    local.writeUInt16LE(dosDate, 12);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(data.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(name.length, 26);
    local.writeUInt16LE(0, 28);

    chunks.push(local, name, data);

    const entry = Buffer.alloc(46);
    entry.writeUInt32LE(0x02014b50, 0);
    entry.writeUInt16LE(20, 4);
    entry.writeUInt16LE(20, 6);
    entry.writeUInt16LE(0x0800, 8);
    entry.writeUInt16LE(0, 10);
    entry.writeUInt16LE(dosTime, 12);
    entry.writeUInt16LE(dosDate, 14);
    entry.writeUInt32LE(crc, 16);
    entry.writeUInt32LE(data.length, 20);
    entry.writeUInt32LE(data.length, 24);
    entry.writeUInt16LE(name.length, 28);
    entry.writeUInt32LE(offset, 42);
    central.push(entry, name);

    offset += 30 + name.length + data.length;
  }

  const centralSize = central.reduce((sum, chunk) => sum + chunk.length, 0);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(files.length, 8);
  end.writeUInt16LE(files.length, 10);
  end.writeUInt32LE(centralSize, 12);
  end.writeUInt32LE(offset, 16);

  return Buffer.concat([...chunks, ...central, end]);
}
