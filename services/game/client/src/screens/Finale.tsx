/**
 * The final debrief: standings, the analytics board, and the engine's own ten answers.
 *
 * Everything here is the finalized payload the engine computed over recorded history —
 * the client only arranges it. Model quality and game performance are kept as separate
 * boards and never combined into a single score. Outcomes are never narrated as proof
 * that a decision was good or bad; where the engine's debrief marks an override or a
 * luck case, the language stays neutral.
 */

import { Navigate } from "react-router-dom";

import { SessionTopbar } from "../chrome";
import { Kv, Panel } from "../components";
import { money, pct } from "../format";
import { useSession } from "../session";
import { normalizeFinaleStandings } from "../api";
import type { Finale, FinaleStanding } from "../api";

export function Finale() {
  const { state } = useSession();
  if (!state) return null;

  if (state.session.phase !== "finale") {
    return <Navigate to="/game/results" replace />;
  }

  const finale: Finale | null = state.finale;
  if (!finale) return null;

  const standings = normalizeFinaleStandings(finale.standings).sort((a, b) => a.rank - b.rank);
  const winner = standings[0] ?? null;
  const analytics = finale.analytics as Record<string, unknown>[];
  const debrief = finale.debrief as Record<string, unknown>;
  const answers = Array.isArray(debrief.answers) ? (debrief.answers as Record<string, unknown>[]) : [];

  return (
    <div className="shell">
      <SessionTopbar state={state} />
      <main className="shell-main wide">
        <div className="page-head">
          <span className="panel-label">Final debrief</span>
          <h2>The market has closed</h2>
          <p className="sub">
            Four years, resolved. Standings are the game; the analytics board is the model.
            They are never combined into one score.
          </p>
        </div>

        <div className="stack">
          {winner ? <GameWinner winner={winner} isMine={winner.fund_id === state.you.fundId} /> : null}

          <div className="grid-2">
            <Panel label="Game standings" data-testid="finale-standings">
              <table className="board">
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th>Fund</th>
                    <th className="num">NAV</th>
                    <th className="num">Return</th>
                    <th className="num">Assets</th>
                    <th className="num">LTV</th>
                  </tr>
                </thead>
                <tbody>
                  {standings.map((row) => (
                    <tr key={row.fund_id} className={row.fund_id === state.you.fundId ? "mine" : undefined}>
                      <td>{row.rank}</td>
                      <td>{row.fund_name}</td>
                      <td className="num mono">{money(row.nav, 0)}</td>
                      <td className="num mono">{pct(row.cumulative_return, 1)}</td>
                      <td className="num">{row.assets}</td>
                      <td className="num mono">{row.portfolio_ltv === null ? "—" : pct(row.portfolio_ltv, 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>

            <Panel label="Model board" data-testid="finale-analytics">
              <AnalyticsBoard rows={analytics} />
            </Panel>
          </div>

          {answers.length > 0 ? <TeachingAnswers answers={answers} /> : null}

          <Panel label="How to read this">
            <div className="grid-2">
              <div>
                <Kv k="Best model" v={<span className="v small">lowest valuation MAE on the analytics board</span>} />
                <Kv k="Best fund" v={<span className="v small">highest final NAV — a fund is capital, not a model</span>} />
              </div>
              <div>
                <Kv k="Overrides" v={<span className="v small">decisions that deviated from the frozen policy; recorded, never penalized</span>} />
                <Kv k="Outcome bias" v={<span className="v small">a realized year proves what happened, not that the decision was right</span>} />
              </div>
            </div>
          </Panel>
        </div>
      </main>
    </div>
  );
}

function GameWinner({ winner, isMine }: { winner: FinaleStanding; isMine: boolean }) {
  return (
    <div className="locked-banner" data-testid="game-winner">
      <div>
        <span className="panel-label">Game winner</span>
        <div className="l-sub" style={{ fontSize: 22, fontWeight: 700, color: "var(--white)" }}>
          {winner.fund_name} {isMine ? "— your fund" : ""}
        </div>
        <div className="l-sub">
          NAV {money(winner.nav, 0)} · {pct(winner.cumulative_return, 1)} total return · {winner.assets}{" "}
          {winner.assets === 1 ? "property" : "properties"} · portfolio LTV{" "}
          {winner.portfolio_ltv === null ? "—" : pct(winner.portfolio_ltv, 0)}
        </div>
      </div>
    </div>
  );
}

function AnalyticsBoard({ rows }: { rows: Record<string, unknown>[] }) {
  const shaped = rows
    .map((row) => ({
      fund: String(row.fund_name ?? row.team_name ?? row.fund_id ?? row.team_id ?? ""),
      valuationMae: typeof row.valuation_mae === "number" ? row.valuation_mae : null,
      noiGrowthMae: typeof row.noi_growth_mae === "number" ? row.noi_growth_mae : null,
      downside: typeof row.downside_calibration === "number" ? row.downside_calibration : null,
      overrides: typeof row.decision_overrides === "number" ? row.decision_overrides : null,
      investedOverrides: typeof row.invested_overrides === "number" ? row.invested_overrides : null,
      discipline: typeof row.policy_discipline_rate === "number" ? row.policy_discipline_rate : null,
    }))
    .filter((row) => row.valuationMae !== null);

  if (shaped.length === 0) {
    return <p className="help">The engine recorded no model metrics for this game.</p>;
  }

  return (
    <table className="board">
      <thead>
        <tr>
          <th>Fund</th>
          <th className="num">Valuation MAE</th>
          <th className="num">NOI MAE</th>
          <th className="num">Calibration</th>
          <th className="num">Overrides</th>
          <th className="num">Discipline</th>
        </tr>
      </thead>
      <tbody>
        {shaped.map((row) => (
          <tr key={row.fund}>
            <td>{row.fund}</td>
            <td className="num mono">{money(row.valuationMae)}</td>
            <td className="num mono">{row.noiGrowthMae === null ? "—" : pct(row.noiGrowthMae, 1)}</td>
            <td className="num mono">{row.downside === null ? "—" : pct(row.downside, 1)}</td>
            <td className="num">
              {row.overrides ?? "—"}
              {row.investedOverrides !== null && row.investedOverrides !== undefined ? (
                <span className="dim"> ({row.investedOverrides} invested)</span>
              ) : null}
            </td>
            <td className="num mono">{row.discipline === null ? "—" : pct(row.discipline, 0)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function TeachingAnswers({ answers }: { answers: Record<string, unknown>[] }) {
  return (
    <Panel label="The ten questions, answered" data-testid="finale-answers">
      <table className="board">
        <thead>
          <tr>
            <th style={{ width: "42%" }}>Question</th>
            <th>Answer</th>
          </tr>
        </thead>
        <tbody>
          {answers.map((row, i) => (
            <tr key={i}>
              <td>{String(row.question ?? row.q ?? "")}</td>
              <td>
                {typeof row.answer === "string" ? row.answer : row.answer !== undefined ? JSON.stringify(row.answer) : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="help mt-8">
        Deterministic calculations over the recorded game — no generated narration. A row is
        omitted rather than guessed when the data does not support it.
      </p>
    </Panel>
  );
}
