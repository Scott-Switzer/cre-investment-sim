/**
 * The professor console.
 *
 * Sign-in re-issues the professor cookie (the passcode is the only secret). The grid
 * shows who is in and what they have locked — never bid amounts, because this screen
 * is routinely projected for the room. Controls are enabled only when the server's
 * phase machine says they are legal, and every transition sends If-Match so a
 * double-click is refused rather than resolved twice.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, ApiError } from "../api";
import { Badge, ErrorBox, Loading, Panel } from "../components";
import { SessionTopbar } from "../chrome";
import { useSession } from "../session";
import type { FundView, ModelStatus, SubmissionGridRow } from "../api";

type ProfessorAction = "begin_checkin" | "start_game" | "close_round";

export function Professor() {
  const { status, state } = useSession();

  // The route is deliberately outside the student gate: this screen is its own gate.
  // No seat → the passcode form (which mints the professor cookie). Seat with a
  // professor role → the console. Anything else cannot be here.
  if (status === "loading") return <Loading />;
  if (status === "none" || !state) return <ProfessorSignIn />;
  if (state.you.role !== "professor") return <ProfessorSignIn />;
  return <ProfessorConsole />;
}

function ProfessorConsole() {
  const { state, refresh } = useSession();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!state) return null;
  const { session, funds, members, round, grid } = state;

  const phase = session.phase;
  const canBeginCheckIn = phase === "lobby";
  const canStartGame = phase === "model_checkin";
  const canClose = phase === "practice" || phase === "round";
  const canReveal = phase === "practice_results" || phase === "round_results";

  const modelsLocked = funds.filter((f) => f.modelStatus === "locked").length;
  const practiceSubmitted = round?.submittedFunds ?? 0;
  const joinCode = (state as unknown as { session: { joinCode?: string } }).session.joinCode ?? "";

  async function run(action: Exclude<ProfessorAction, null>) {
    setBusy(true);
    setError(null);
    try {
      if (action === "begin_checkin") await api.beginCheckIn(session.id, session.revision);
      if (action === "start_game") await api.startGame(session.id, session.revision);
      if (action === "close_round") await api.closeRound(session.id, session.revision);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The action failed.");
      setBusy(false);
    }
  }

  return (
    <div className="shell">
      <SessionTopbar state={state} />
      <main className="shell-main wide">
        <div className="page-head spread">
          <div>
            <span className="panel-label">{session.name}</span>
            <h2>CRE Investment Committee — Professor console</h2>
            <p className="sub">{session.bundleDisplayName} · {session.poolCount} candidates · {session.totalRounds} scored rounds</p>
          </div>
          <div className="row" style={{ gap: 10 }}>
            <div>
              <div className="stat-label" style={{ color: "var(--slate-500)", fontSize: 10.5, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase" }}>
                Join code
              </div>
              <span className="topbar-code" style={{ fontSize: 20, padding: "6px 14px" }} data-testid="join-code">
                {joinCode}
              </span>
            </div>
            <Badge tone={phase === "lobby" ? "neutral" : "ok"}>{phase.replace("_", " ")}</Badge>
          </div>
        </div>

        {error ? <div className="mb-16"><ErrorBox>{error}</ErrorBox></div> : null}

        <div className="stat-strip mb-16">
          <div className="stat">
            <div className="stat-label">Students</div>
            <div className="stat-value" data-testid="kpi-students">{members.filter((m) => !m.isProfessor).length}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Funds</div>
            <div className="stat-value" data-testid="kpi-funds">{funds.length}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Models locked</div>
            <div className="stat-value" data-testid="kpi-models">{modelsLocked} / {funds.length}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Practice submitted</div>
            <div className="stat-value" data-testid="kpi-practice">{practiceSubmitted} / {funds.length}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Phase</div>
            <div className="stat-value dim" style={{ fontSize: 16 }}>{phaseLabel(phase)}</div>
          </div>
        </div>

        <Panel label="Funds">
          <table className="table" data-testid="fund-grid">
            <thead>
              <tr>
                <th>Fund</th>
                <th className="num">Members</th>
                <th>Model</th>
                <th>Practice</th>
                <th className="num">Policy overrides</th>
              </tr>
            </thead>
            <tbody>
              {rowsFor(grid, funds).map((row) => (
                <tr key={row.fundId} data-testid={`grid-row-${row.fundName}`}>
                  <td style={{ fontWeight: 600 }}>{row.fundName}</td>
                  <td className="num">{row.members}</td>
                  <td><ModelCell status={row.modelStatus} /></td>
                  <td><SubmitCell submitted={row.submitted} /></td>
                  <td className="num">
                    {row.submitted ? (
                      <span title="Submissions that deviated from the fund's own locked policy — counted whether or not the bid won">
                        {row.bidsAboveOwnCeiling} price · {row.ltvAboveOwnTarget} LTV
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="help mt-8">
            Bid amounts stay sealed until the reveal — this screen is projected for the room.
          </p>
        </Panel>

        <div className="mt-20 locked-banner" style={{ justifyContent: "space-between" }}>
          <div>
            <span className="panel-label">Session control</span>
            <div className="l-sub">{session.nextStep}</div>
          </div>
          <div className="row">
            <button
              className="btn btn-primary"
              disabled={!canBeginCheckIn || busy}
              onClick={() => run("begin_checkin")}
              data-testid="open-practice-checkin"
            >
              Open model check-in
            </button>
            <button
              className="btn btn-primary"
              disabled={!canStartGame || busy}
              onClick={() => run("start_game")}
              data-testid="open-practice"
              title={canStartGame ? "" : "Every fund must lock a model first"}
            >
              Open practice
            </button>
            <button
              className="btn btn-danger"
              disabled={!canClose || busy}
              onClick={() => run("close_round")}
              data-testid="close-practice"
            >
              {phase === "practice" ? "Close practice" : "Close round"}
            </button>
            <button
              className="btn btn-secondary"
              disabled={!canReveal}
              onClick={() => navigate("/professor")}
              data-testid="reveal-results"
              title={canReveal ? "Results are already revealed to the room" : "Revealed automatically on close"}
            >
              Reveal results
            </button>
          </div>
        </div>
        <p className="help mt-8">
          Closing the market resolves it with the engine and reveals the reserve, the realized
          year and results to every fund at once. Invalid controls are disabled by the phase
          machine, not hidden.
        </p>
      </main>
    </div>
  );
}

function ProfessorSignIn() {
  const [passcode, setPasscode] = useState("");
  const [name, setName] = useState("Professor Frenzel");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sessions, setSessions] = useState<{ id: string; name: string; joinCode: string }[]>([]);

  async function signIn(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const listRes = await fetch("/v1/sessions", { headers: { "x-professor-passcode": passcode } });
      if (!listRes.ok) throw new ApiError(listRes.status, "forbidden", "That passcode is not correct.");
      const list = (await listRes.json()) as { sessions: { id: string; name: string; joinCode: string }[] };
      setSessions(list.sessions);
      if (list.sessions.length === 0) {
        setError("No sessions exist yet — create one from the engine's admin flow or ask your administrator.");
        setBusy(false);
        return;
      }
      const latest = list.sessions[0]!;
      await api.rejoinProfessor(latest.id, passcode, name);
      window.location.assign("/professor");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
      setBusy(false);
    }
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-inner">
          <span className="brand-mark">CRE Investment Committee</span>
          <div className="topbar-spacer" />
        </div>
      </header>
      <main className="shell-main narrow">
        <div className="page-head">
          <span className="panel-label">Professor</span>
          <h2>Host a session</h2>
        </div>
        {error ? <div className="mb-16"><ErrorBox>{error}</ErrorBox></div> : null}
        <Panel>
          <form onSubmit={signIn}>
            <div className="field">
              <label htmlFor="passcode">Professor passcode</label>
              <input
                id="passcode"
                className="input"
                type="password"
                value={passcode}
                onChange={(e) => setPasscode(e.target.value)}
                required
                data-testid="professor-signin-input"
              />
            </div>
            <div className="field">
              <label htmlFor="profName">Display name</label>
              <input id="profName" className="input" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <button className="btn btn-primary btn-block" disabled={busy} data-testid="professor-signin">
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </Panel>
        {sessions.length > 0 ? (
          <p className="help mt-12">Signing in attaches this browser to the most recent class: {sessions[0]!.name}.</p>
        ) : null}
      </main>
    </div>
  );
}

function ModelCell({ status }: { status: ModelStatus }) {
  if (status === "locked") return <Badge tone="ok">✓ locked</Badge>;
  if (status === "validated") return <Badge tone="warn">validated</Badge>;
  return <Badge tone="neutral">…</Badge>;
}

function SubmitCell({ submitted }: { submitted: boolean }) {
  if (submitted) return <Badge tone="ok">✓ submitted</Badge>;
  return <Badge tone="neutral">…</Badge>;
}

function phaseLabel(phase: string): string {
  switch (phase) {
    case "lobby": return "Lobby";
    case "model_checkin": return "Model check-in";
    case "practice": return "Practice";
    case "practice_results": return "Practice results";
    case "round": return "Scored round";
    case "round_results": return "Round results";
    case "finale": return "Finale";
    default: return phase;
  }
}

interface GridRow {
  fundId: string;
  fundName: string;
  members: number;
  modelStatus: ModelStatus;
  submitted: boolean;
  bidsAboveOwnCeiling: number;
  ltvAboveOwnTarget: number;
}

function rowsFor(grid: SubmissionGridRow[] | null, funds: FundView[]): GridRow[] {
  if (grid && grid.length > 0) {
    return grid.map((row) => ({
      fundId: row.fundId,
      fundName: row.fundName,
      members: funds.find((f) => f.id === row.fundId)?.memberCount ?? 0,
      modelStatus: funds.find((f) => f.id === row.fundId)?.modelStatus ?? "none",
      submitted: row.submitted,
      bidsAboveOwnCeiling: row.bidsAboveOwnCeiling,
      ltvAboveOwnTarget: row.ltvAboveOwnTarget,
    }));
  }
  return funds.map((f) => ({
    fundId: f.id,
    fundName: f.name,
    members: f.memberCount,
    modelStatus: f.modelStatus,
    submitted: false,
    bidsAboveOwnCeiling: 0,
    ltvAboveOwnTarget: 0,
  }));
}
