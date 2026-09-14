/**
 * The lobby. Everything a fund needs to orient before check-in: which class, which
 * code, who is in the room, and the one action that matters — check in the model.
 * Live through the SSE doorbell; the roster and fund table re-render on revision.
 */

import { Navigate } from "react-router-dom";

import { SessionTopbar } from "../chrome";
import { Badge, Panel } from "../components";
import { useSession } from "../session";

export function Lobby() {
  const { state } = useSession();
  if (!state) return null;
  const { session, funds, members, you, yourFund } = state;

  // Check-in has not opened: the CTA is the only thing that is disabled, not the room.
  if (session.phase !== "lobby") {
    return <Navigate to={session.phase === "model_checkin" ? "/model" : "/game/practice"} replace />;
  }

  const students = members.filter((m) => !m.isProfessor);
  const modelLocked = funds.filter((f) => f.modelStatus === "locked").length;

  return (
    <div className="shell">
      <SessionTopbar state={state} />
      <main className="shell-main">
        <div className="page-head">
          <span className="panel-label">Class lobby</span>
          <h2>{session.name}</h2>
          <p className="sub">{session.bundleDisplayName} · {session.poolCount} candidate properties</p>
        </div>

        <div className="stat-strip mb-16">
          <div className="stat">
            <div className="stat-label">Class code</div>
            <div className="stat-value" data-testid="lobby-join-code">{session.name === "" ? "—" : joinCodeOrDash(you.fundId)}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Your fund</div>
            <div className="stat-value dim" data-testid="lobby-fund-name">{yourFund?.name ?? "—"}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Funds joined</div>
            <div className="stat-value" data-testid="lobby-fund-count">{funds.length}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Students</div>
            <div className="stat-value">{students.length}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Models locked</div>
            <div className="stat-value">{modelLocked} / {funds.length}</div>
          </div>
        </div>

        <div className="grid-2">
          <Panel label="Your fund">
            {yourFund ? (
              <>
                <div className="spread">
                  <div>
                    <div style={{ fontWeight: 650, fontSize: 16 }}>{yourFund.name}</div>
                    <div className="deal-sub">
                      {yourFund.memberCount} of {session.maxTeamSize} members
                    </div>
                  </div>
                  <ModelBadge status={yourFund.modelStatus} />
                </div>
                <div className="mt-16">
                  <span className="panel-label">Members</span>
                  <div className="mt-8">
                    {members
                      .filter((m) => m.fundId === yourFund.id)
                      .map((m) => (
                        <div key={m.id} className="kv">
                          <span className="k">{m.displayName}</span>
                          <span className="v small">
                            {m.id === you.memberId ? <Badge tone="navy">you</Badge> : <Badge>teammate</Badge>}
                          </span>
                        </div>
                      ))}
                  </div>
                </div>
              </>
            ) : (
              <p className="help">You are not in a fund yet.</p>
            )}
          </Panel>

          <Panel label="All funds">
            <table className="table" data-testid="lobby-fund-table">
              <thead>
                <tr>
                  <th>Fund</th>
                  <th className="num">Members</th>
                  <th>Model</th>
                </tr>
              </thead>
              <tbody>
                {funds.map((f) => (
                  <tr key={f.id}>
                    <td>{f.name}</td>
                    <td className="num">{f.memberCount} / {session.maxTeamSize}</td>
                    <td><ModelBadge status={f.modelStatus} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        </div>

        <div className="mt-20 locked-banner" style={{ justifyContent: "space-between" }}>
          <div>
            <span className="panel-label">{session.nextStep}</span>
            <div className="l-sub">
              Upload the predictions your team produced before class, then lock them. The game
              freezes those outputs and uses them during play.
            </div>
          </div>
          <button className="btn btn-primary btn-lg" disabled data-testid="checkin-cta">
            Check in model — waiting for professor
          </button>
        </div>
      </main>
    </div>
  );
}

function ModelBadge({ status }: { status: "none" | "validated" | "locked" }) {
  if (status === "locked") return <Badge tone="ok">locked</Badge>;
  if (status === "validated") return <Badge tone="warn">validated</Badge>;
  return <Badge tone="neutral">not uploaded</Badge>;
}

/**
 * The join code is only in the professor's view in Phase 1's API — students receive
 * the code out loud. Shown here as the session id fragment would be noise, so the
 * student lobby shows a dash and the real code comes from the professor's screen.
 */
function joinCodeOrDash(_fundId: string | null): string {
  return "—";
}
