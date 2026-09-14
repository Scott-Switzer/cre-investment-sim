/**
 * The locked-in state. No competitor data exists yet — the SSE doorbell updates only
 * the submission count, and the phase change to results is what moves the room.
 */

import { Navigate } from "react-router-dom";

import { SessionTopbar } from "../chrome";
import { useSession } from "../session";

export function Waiting() {
  const { state } = useSession();
  if (!state) return null;
  const { session, round } = state;

  if (session.phase === "practice_results" || session.phase === "round_results" || session.phase === "finale") {
    return <Navigate to="/game/results" replace />;
  }
  if (session.phase === "practice" || session.phase === "round") {
    // Still open — either not submitted yet (board should have it) or submitted and waiting.
    if (!round?.myDecision) return <Navigate to="/game/practice" replace />;
  }
  if (session.phase === "lobby" || session.phase === "model_checkin") {
    return <Navigate to={session.phase === "lobby" ? "/lobby" : "/model"} replace />;
  }

  const submitted = round?.submittedFunds ?? 0;
  const total = round?.totalFunds ?? 0;

  return (
    <div className="shell">
      <SessionTopbar state={state} />
      <main className="shell-main narrow" style={{ display: "flex", flexDirection: "column", justifyContent: "center" }}>
        <div className="locked-banner" style={{ padding: "28px 24px" }} data-testid="waiting-banner">
          <div>
            <span className="panel-label">Decisions locked</span>
            <div className="l-sub" style={{ fontSize: 15, marginTop: 6 }}>
              {session.isPracticeRound ? "Your fund submitted Practice." : "Your fund submitted its decisions."}
            </div>
          </div>
        </div>

        <div className="card card-pad mt-20" data-testid="submission-count">
          <div className="spread">
            <span className="panel-label">Funds submitted</span>
            <span className="stat-value" style={{ fontSize: 24, fontVariantNumeric: "tabular-nums" }}>
              {submitted} / {total}
            </span>
          </div>
          <div style={{ height: 8, background: "var(--slate-200)", borderRadius: 4, marginTop: 10, overflow: "hidden" }}>
            <div
              style={{
                width: total === 0 ? 0 : `${Math.round((submitted / total) * 100)}%`,
                height: "100%",
                background: "var(--navy-600)",
                transition: "width 300ms ease",
              }}
            />
          </div>
        </div>

        <p className="mt-20 help" style={{ textAlign: "center", fontSize: 15 }}>
          Waiting for Professor Frenzel{round?.isPractice ? " to close the practice market…" : " to close the market…"}
        </p>
        <p className="help" style={{ textAlign: "center" }}>
          Sealed-bid rules: no bids are visible to anyone until the market closes.
        </p>
      </main>
    </div>
  );
}
