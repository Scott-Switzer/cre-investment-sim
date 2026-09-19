/**
 * Join: name + class code → fund picker → in.
 *
 * Two flows live here. A fresh browser previews the class, picks CREATE or JOIN, and
 * signs in; a browser that lost its cookies mid-class reclaims its seat by name. The
 * signed HttpOnly cookie issued on success is what makes a refresh preserve the
 * player — nothing is stored client-side.
 */

import { useEffect, useState } from "react";

import { api, ApiError, type JoinPreview } from "../api";
import { ErrorBox, Panel } from "../components";
import { PublicTopbar } from "../chrome";
import { useSession } from "../session";

type Mode = "create" | "join";

export function Join() {
  const [step, setStep] = useState<"identity" | "fund">("identity");
  const [displayName, setName] = useState("");
  const [code, setCode] = useState("");
  const [preview, setPreview] = useState<JoinPreview | null>(null);
  const [mode, setMode] = useState<Mode>("create");
  const [newFundName, setNewFundName] = useState("");
  const [fundId, setFundId] = useState<string | null>(null);
  const [reclaimName, setReclaimName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [seatNames, setSeatNames] = useState<Record<string, string>>({});

  // A browser can hold several seats at once. Rather than guessing which class this is
  // — which is how a student who joined a second session used to land in the first —
  // the held seats are named and the player says which one they mean.
  const { sessions = [], ambiguous = false, chooseSession } = useSession();

  useEffect(() => {
    if (!ambiguous || sessions.length < 2) return;
    let cancelled = false;
    void (async () => {
      const named = await Promise.all(
        sessions.map(async (seat) => {
          try {
            const view = await api.stateOrThrow(seat.sessionId);
            return [seat.sessionId, view.session.name] as const;
          } catch {
            // A seat we hold but cannot read is still listed, by id. Better an opaque
            // choice than a hidden one.
            return [seat.sessionId, null] as const;
          }
        }),
      );
      if (cancelled) return;
      setSeatNames(
        Object.fromEntries(
          named.filter((entry): entry is readonly [string, string] => entry[1] !== null),
        ),
      );
    })();
    return () => {
      cancelled = true;
    };
  }, [ambiguous, sessions]);

  async function lookup(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const p = await api.joinPreview(code);
      setPreview(p);
      setNewFundName("");
      setFundId(null);
      setMode(p.funds.length === 0 ? "create" : "join");
      setStep("fund");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the game service.");
    } finally {
      setBusy(false);
    }
  }

  function pickFund(e: React.MouseEvent<HTMLButtonElement>, id: string) {
    e.preventDefault();
    setFundId(id);
    setMode("join");
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await api.join({
        joinCode: code,
        displayName,
        ...(mode === "join" && fundId ? { fundId } : { newFundName }),
      });
      // Full page load, not a client-side navigate: the session provider discovers
      // the seat once at mount, and the HttpOnly cookie this response just set is
      // only visible to a fresh discovery pass.
      window.location.assign(`/lobby?s=${result.sessionId}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the game service.");
      setBusy(false);
    }
  }

  async function reclaim(e: React.FormEvent) {
    e.preventDefault();
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      await api.reclaim(preview.session.id, reclaimName);
      // Name the session being reclaimed into: a browser that has joined more than one
      // class would otherwise be free to land in a different one.
      window.location.assign(`/lobby?s=${encodeURIComponent(preview.session.id)}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the game service.");
      setBusy(false);
    }
  }

  const teamMode = preview?.session.mode === "team";

  return (
    <div className="shell">
      <PublicTopbar />
      <main className="shell-main narrow">
        <div className="page-head">
          <span className="panel-label">Join a class</span>
          <h2>{step === "identity" ? "Enter the committee" : preview?.session.name}</h2>
          {step === "fund" && preview ? (
            <p className="sub">
              {preview.session.bundleDisplayName} ·{" "}
              {teamMode ? `funds of up to ${preview.session.maxTeamSize}` : "individual play"}
            </p>
          ) : null}
        </div>

        {error ? <div className="mb-16"><ErrorBox>{error}</ErrorBox></div> : null}

        {ambiguous && sessions.length > 1 ? (
          <div className="mb-16">
            <Panel label="You have more than one seat">
              <p className="help" style={{ marginTop: 0 }}>
                This browser is signed in to {sessions.length} sessions. Choose the one
                you want; each tab keeps its own.
              </p>
              {sessions.map((seat) => (
                <button
                  key={seat.sessionId}
                  type="button"
                  className="fund-option"
                  onClick={() => void chooseSession?.(seat.sessionId)}
                  data-testid={`pick-session-${seat.sessionId}`}
                >
                  <span className="f-name">{seatNames[seat.sessionId] ?? seat.sessionId}</span>
                  <span className="f-count">
                    {seat.role === "professor" ? "Hosting" : "Playing"}
                  </span>
                </button>
              ))}
            </Panel>
          </div>
        ) : null}

        {step === "identity" ? (
          <Panel>
            <form onSubmit={lookup}>
              <div className="field">
                <label htmlFor="displayName">Your name</label>
                <input
                  id="displayName"
                  className="input"
                  value={displayName}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Jordan Alvarez"
                  autoComplete="name"
                  required
                  minLength={2}
                  maxLength={40}
                />
              </div>
              <div className="field">
                <label htmlFor="joinCode">Class code</label>
                <input
                  id="joinCode"
                  className="input mono"
                  value={code}
                  onChange={(e) => setCode(e.target.value.toUpperCase())}
                  placeholder="6 characters"
                  autoComplete="off"
                  required
                  minLength={6}
                  maxLength={8}
                />
                <p className="help">Your professor reads this out. It is case-insensitive.</p>
              </div>
              <button className="btn btn-primary btn-block" disabled={busy} data-testid="join-continue">
                {busy ? "Checking…" : "Continue"}
              </button>
            </form>
          </Panel>
        ) : (
          <>
            <Panel label={teamMode ? "Your fund" : "Individual play"}>
              {teamMode ? (
                <>
                  <div className="seg" role="tablist" aria-label="Fund mode">
                    <button
                      type="button"
                      role="tab"
                      aria-selected={mode === "create"}
                      className={mode === "create" ? "active" : ""}
                      onClick={() => setMode("create")}
                      data-testid="mode-create"
                    >
                      Create a fund
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={mode === "join"}
                      className={mode === "join" ? "active" : ""}
                      onClick={() => setMode("join")}
                      data-testid="mode-join"
                    >
                      Join existing fund
                    </button>
                  </div>

                  {mode === "create" ? (
                    <form onSubmit={submit}>
                      <div className="field">
                        <label htmlFor="fundName">Fund name</label>
                        <input
                          id="fundName"
                          className="input"
                          value={newFundName}
                          onChange={(e) => setNewFundName(e.target.value)}
                          placeholder="Pacific CRE Partners"
                          required
                          minLength={3}
                          maxLength={40}
                          data-testid="fund-name"
                        />
                        <p className="help">Naming an existing fund joins it instead of creating a duplicate.</p>
                      </div>
                      <button className="btn btn-primary btn-block" disabled={busy} data-testid="fund-submit">
                        {busy ? "Joining…" : "Join"}
                      </button>
                    </form>
                  ) : (
                    <form onSubmit={submit}>
                      <div style={{ marginBottom: 12 }}>
                        {preview!.funds.map((f) => {
                          const full = teamMode && f.memberCount >= preview!.session.maxTeamSize;
                          const selected = fundId === f.id;
                          return (
                            <button
                              key={f.id}
                              type="button"
                              className="fund-option"
                              disabled={full}
                              aria-pressed={selected}
                              style={selected ? { borderColor: "var(--navy-600)", boxShadow: "0 0 0 1px var(--navy-600)" } : undefined}
                              onClick={(e) => pickFund(e, f.id)}
                              data-testid={`fund-option-${f.name}`}
                            >
                              <span className="f-name">{f.name}</span>
                              <span className="f-count">
                                {f.memberCount} / {preview!.session.maxTeamSize}
                                {full ? " · full" : ""}
                              </span>
                            </button>
                          );
                        })}
                        {preview!.funds.length === 0 ? (
                          <p className="help">No funds yet — create the first one.</p>
                        ) : null}
                      </div>
                      <button className="btn btn-primary btn-block" disabled={busy || !fundId} data-testid="fund-submit">
                        {busy ? "Joining…" : "Join fund"}
                      </button>
                    </form>
                  )}
                </>
              ) : (
                <form onSubmit={submit}>
                  <button className="btn btn-primary btn-block" disabled={busy} data-testid="fund-submit">
                    {busy ? "Joining…" : "Join"}
                  </button>
                </form>
              )}
            </Panel>

            <div className="mt-16">
              <Panel label="Lost your seat?">
                <p className="help" style={{ marginTop: 0 }}>
                  Cookies cleared or switched devices? Reclaim your seat by the exact name you
                  joined with.
                </p>
                <form onSubmit={reclaim} className="row">
                  <input
                    className="input"
                    style={{ flex: 1 }}
                    value={reclaimName}
                    onChange={(e) => setReclaimName(e.target.value)}
                    placeholder="Your name as you joined"
                    aria-label="Name you joined with"
                  />
                  <button className="btn btn-secondary" disabled={busy || reclaimName.trim().length < 2}>
                    Reclaim
                  </button>
                </form>
              </Panel>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
