/**
 * The persistent header. Two variants: the marketing shell for public screens and
 * the session shell for everyone in the room. The session shell carries the fund's
 * name, the phase, and — during play — the live cash/assets/nav line.
 */

import { Link } from "react-router-dom";

import { money } from "./format";
import type { StateView } from "./api";

export function Brand({ light = false }: { light?: boolean }) {
  return (
    <Link to="/" className="brand" aria-label="CRE Investment Committee home">
      <span className="brand-mark">CRE Investment Committee</span>
      {!light ? <span className="brand-sub">REAL 605</span> : null}
    </Link>
  );
}

export function PublicTopbar() {
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <Brand />
        <div className="topbar-spacer" />
        <Link to="/professor" className="btn btn-ghost btn-sm">
          Professor? Host a session
        </Link>
      </div>
    </header>
  );
}

/**
 * The practice header, exactly as specified: fund name, PRACTICE · NOT SCORED,
 * the cash/assets line, and (during rounds) the fund's live NAV.
 */
export function SessionTopbar({ state }: { state: StateView }) {
  const { session, you, yourFund } = state;
  const isProfessor = you.role === "professor";
  const fundName = yourFund?.name ?? "Professor Console";
  const inPlay = session.phase === "practice" || session.phase === "round";
  const notScored = session.isPracticeRound && (session.phase === "practice" || session.phase === "practice_results");
  const myFundSummary = inPlay
    ? state.round?.public.funds.find((f) => f.team_id === you.fundId)
    : undefined;

  return (
    <header className="topbar">
      <div className="topbar-inner">
        <div className="row" style={{ gap: 14 }}>
          <span className="brand-mark">{fundName}</span>
          {notScored ? (
            <span className="badge badge-warn">Practice · Not scored</span>
          ) : (
            <span className="badge badge-navy">{session.roundLabel}</span>
          )}
        </div>
        <div className="topbar-spacer" />
        {inPlay && myFundSummary && !isProfessor ? (
          <div className="topbar-meta" aria-label="Fund position">
            <strong style={{ color: "var(--white)", fontVariantNumeric: "tabular-nums" }}>
              CASH {money(myFundSummary.cash)}
            </strong>
            <span style={{ margin: "0 10px", color: "var(--slate-500)" }}>|</span>
            ASSETS {myFundSummary.assets}
            <span style={{ margin: "0 10px", color: "var(--slate-500)" }}>|</span>
            NAV {money(myFundSummary.nav)}
          </div>
        ) : null}
        {isProfessor ? <span className="topbar-code">{state.session.name}</span> : null}
        <span className="topbar-user">
          signed in as <strong>{you.displayName}</strong>
        </span>
      </div>
    </header>
  );
}
