/**
 * Bigscreen: a read-only, control-free projector view for the classroom.
 *
 * The professor opens `/bigscreen` in a second tab after signing in. It shows only
 * what the phase has legitimately revealed — lobby join code and lock counts, the
 * round clock and submission counts, revealed winners, standings, and the finale.
 * Sealed bids never appear here; the screen is routinely projected.
 */

import { useEffect, useState } from "react";

import { api } from "../api";
import type { RoundResults, StateView } from "../api";
import { money, pct } from "../format";

export function Bigscreen() {
  const { status, state, refresh } = useBigscreenState();

  if (status === "none") return <NoSeat />;
  if (status === "loading" || !state) return <div className="bigscreen-loading">…</div>;

  const phase = state.session.phase;
  return (
    <div className="bigscreen" data-testid="bigscreen">
      <BigHeader phase={phase} state={state} />
      <main className="bigscreen-main">
        {phase === "lobby" || phase === "model_checkin" ? <LobbyMode state={state} /> : null}
        {phase === "practice" || phase === "round" ? <RoundMode state={state} /> : null}
        {phase === "practice_results" || phase === "round_results" ? (
          <RevealMode state={state} />
        ) : null}
        {phase === "finale" ? <FinaleMode state={state} /> : null}
      </main>
      <footer className="bigscreen-footer">
        REAL 605 · CRE INVESTMENT COMMITTEE
        <button className="btn btn-small" onClick={refresh} style={{ marginLeft: "auto" }}>
          Refresh
        </button>
      </footer>
    </div>
  );
}

/**
 * Bigscreen needs its own polling loop: it sits on a projector, nobody clicks it.
 * It uses the same state view as everyone else — there is no bigscreen API.
 */
function useBigscreenState() {
  const [state, setState] = useState<StateView | null>(null);
  const [status, setStatus] = useState<"loading" | "none" | "ready">("loading");

  useEffect(() => {
    let alive = true;
    let lastRevision = -1;

    async function tick() {
      try {
        // The session id is found from the professor's own state; bigscreen has no
        // seat of its own, so it reads via a signed fetch through the same origin.
        const sessions = await fetch("/v1/sessions", { credentials: "include" })
          .then((res) => (res.ok ? res.json() : null))
          .then((body) => (body as { sessions?: { id: string }[] } | null)?.sessions ?? null)
          .catch(() => null);
        if (!alive) return;
        if (!sessions || sessions.length === 0) {
          setStatus("none");
          return;
        }
        const sessionId = sessions[0]!.id;
        const view = await api.state(sessionId, lastRevision >= 0 ? lastRevision : null);
        if (!alive) return;
        if ("unchanged" in view) {
          lastRevision = view.revision;
          return;
        }
        const full = view as StateView;
        if (full.you.role !== "professor") {
          setStatus("none");
          return;
        }
        lastRevision = full.session.revision;
        setState(full);
        setStatus("ready");
      } catch {
        // A transient failure keeps the last frame; the loop retries.
      }
    }

    void tick();
    const timer = setInterval(tick, 4000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  return { status, state, refresh: () => void 0 };
}

function NoSeat() {
  return (
    <div className="bigscreen">
      <div className="bigscreen-loading" data-testid="bigscreen-noseat">
        No projector session. Sign in as the professor in another tab first.
      </div>
    </div>
  );
}

function BigHeader({ phase, state }: { phase: string; state: StateView }) {
  const label =
    phase === "lobby" || phase === "model_checkin"
      ? "LOBBY"
      : phase === "practice"
        ? "PRACTICE"
        : phase === "practice_results"
          ? "PRACTICE RESULTS"
          : phase === "round"
            ? `ROUND ${state.session.currentRound + 1} OF ${state.session.totalRounds}`
            : phase === "round_results"
              ? "ROUND RESULTS"
              : "FINAL";
  return (
    <header className="bigscreen-header">
      <span className="bs-brand">PACIFIC CRE PARTNERS</span>
      <span className="bs-phase">{label}</span>
      <span className="bs-clock">{new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
    </header>
  );
}

function LobbyMode({ state }: { state: StateView }) {
  const locked = state.funds.filter((f) => f.modelStatus === "locked").length;
  return (
    <div className="bs-center">
      <div className="bs-title">CRE INVESTMENT COMMITTEE</div>
      <div className="bs-code" data-testid="bigscreen-joincode">
        {state.session.name}
      </div>
      <div className="bs-row">
        <div className="bs-stat">
          <div className="bs-stat-num">{state.members.filter((m) => !m.isProfessor).length}</div>
          <div className="bs-stat-label">students</div>
        </div>
        <div className="bs-stat">
          <div className="bs-stat-num">{state.funds.length}</div>
          <div className="bs-stat-label">funds</div>
        </div>
        <div className="bs-stat">
          <div className="bs-stat-num">
            {locked} / {state.funds.length}
          </div>
          <div className="bs-stat-label">models locked</div>
        </div>
      </div>
    </div>
  );
}

function RoundMode({ state }: { state: StateView }) {
  const round = state.round;
  const submitted = round?.submittedFunds ?? 0;
  const total = round?.totalFunds ?? 0;
  const deadline = state.session.roundDeadlineAt;
  const paused = state.session.timerPausedAt !== null;
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const remaining = deadline === null ? null : Math.max(0, deadline - now);

  return (
    <div className="bs-center">
      <div className="bs-title">
        {state.session.isPracticeRound ? "Practice" : `Round ${state.session.currentRound + 1}`}
      </div>
      {deadline !== null ? (
        <div className="bs-countdown" data-testid="bigscreen-countdown">
          {paused ? "PAUSED" : fmtClock(remaining ?? 0)}
        </div>
      ) : null}
      <div className="bs-row">
        <div className="bs-stat">
          <div className="bs-stat-num" data-testid="bigscreen-submitted">
            {submitted} / {total}
          </div>
          <div className="bs-stat-label">funds submitted</div>
        </div>
      </div>
      <div className="bs-sealed">Bids are sealed until the round closes.</div>
    </div>
  );
}

function RevealMode({ state }: { state: StateView }) {
  const results = state.round?.results;
  if (!results) {
    return (
      <div className="bs-center">
        <div className="bs-title">Revealing…</div>
      </div>
    );
  }
  return (
    <div className="bs-center">
      <div className="bs-title">Round results</div>
      <div className="bs-row">
        {results.auctions.map((auction) => (
          <div className="bs-stat" key={auction.property_id}>
            <div className="bs-stat-num small">
              {auction.sold && auction.winning_team_id ? "SOLD" : "NO SALE"}
            </div>
            <div className="bs-stat-label">
              {auction.property_id}
              {auction.sold && auction.winning_team_id ? ` · ${auction.winning_team_id}` : ""}
            </div>
          </div>
        ))}
      </div>
      <StandingsTable results={results} />
    </div>
  );
}

function FinaleMode({ state }: { state: StateView }) {
  const finale = state.finale;
  if (!finale) return <div className="bs-center"><div className="bs-title">Finalizing…</div></div>;
  const standings = [...finale.standings].sort((a, b) => a.rank - b.rank);
  const winner = standings[0];
  return (
    <div className="bs-center">
      <div className="bs-title">Final standings</div>
      {winner ? (
        <div className="bs-winner" data-testid="bigscreen-winner">
          {winner.fund_name} · NAV {money(winner.nav, 0)} · {pct(winner.cumulative_return, 1)}
        </div>
      ) : null}
      <table className="bs-table">
        <thead>
          <tr>
            <th>Rank</th>
            <th>Fund</th>
            <th>NAV</th>
            <th>Return</th>
          </tr>
        </thead>
        <tbody>
          {standings.map((row) => (
            <tr key={row.fund_id}>
              <td>{row.rank}</td>
              <td>{row.fund_name}</td>
              <td>{money(row.nav, 0)}</td>
              <td>{pct(row.cumulative_return, 1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StandingsTable({ results }: { results: RoundResults | null }) {
  if (!results) return null;
  const standings = [...results.standings].sort((a, b) => a.rank - b.rank);
  return (
    <table className="bs-table">
      <thead>
        <tr>
          <th>Rank</th>
          <th>Fund</th>
          <th>NAV</th>
          <th>Return</th>
        </tr>
      </thead>
      <tbody>
        {standings.map((row) => (
          <tr key={row.team_id}>
            <td>{row.rank}</td>
            <td>{row.team_name}</td>
            <td>{money(row.nav, 0)}</td>
            <td>{pct(row.cumulative_return, 1)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function fmtClock(ms: number): string {
  const total = Math.floor(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}
