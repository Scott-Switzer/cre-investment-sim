/**
 * Model check-in.
 *
 * One screen, one job: get the team's pre-class outputs into the game and frozen.
 * The forecast panel renders the uploaded CSV's own summary; the game does not train
 * or run anything. After lock the screen becomes a receipt — forecasts and policy
 * cannot change during the game — and never hints at accuracy, because no outcome is
 * known yet.
 */

import { useRef, useState } from "react";
import { Navigate } from "react-router-dom";

import { api, ApiError, type UploadReport } from "../api";
import { Badge, ErrorBox, Panel } from "../components";
import { money, pct } from "../format";
import { SessionTopbar } from "../chrome";
import { useSession } from "../session";

export function ModelCheckIn() {
  const { state, refresh } = useSession();
  const fileRef = useRef<HTMLInputElement>(null);
  const [report, setReport] = useState<UploadReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);

  if (!state) return null;
  const { session, yourFund } = state;

  if (session.phase === "lobby") return <Navigate to="/lobby" replace />;
  if (session.phase === "practice") return <Navigate to="/game/practice" replace />;
  if (session.phase === "practice_results") return <Navigate to="/game/results" replace />;

  const fund = yourFund;
  if (!fund) {
    return (
      <div className="shell">
        <SessionTopbar state={state} />
        <main className="shell-main narrow">
          <ErrorBox>You are not in a fund. Go back to /join and join one.</ErrorBox>
        </main>
      </div>
    );
  }

  const locked = fund.modelStatus === "locked";
  const validated = fund.modelStatus === "validated";
  const summary = fund.forecastSummary;

  async function onUpload(file: File) {
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      const csv = await file.text();
      const outcome = await api.uploadModel(session.id, fund!.id, csv);
      setReport(outcome.report);
      if (outcome.ok) {
        setFileName(file.name);
        await refresh();
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  async function onLock() {
    setBusy(true);
    setError(null);
    try {
      await api.lockModel(session.id, fund!.id);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not lock the model.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="shell">
      <SessionTopbar state={state} />
      <main className="shell-main">
        <div className="page-head">
          <span className="panel-label">Model check-in</span>
          <h2>{locked ? "Model locked" : "Your team's pre-class forecast"}</h2>
          <p className="sub">
            Upload the predictions your team produced before class. The game freezes those
            outputs and uses them during play.
          </p>
        </div>

        {error ? <div className="mb-16"><ErrorBox>{error}</ErrorBox></div> : null}

        {locked ? (
          <div className="locked-banner" data-testid="model-locked-banner">
            <div>
              <span className="panel-label">Model locked</span>
              <div className="l-sub">Forecasts and policy cannot change during the game.</div>
            </div>
            <div className="topbar-spacer" />
            <Badge tone="ok">{fund.modelName ?? "model"} · {fund.modelRowCount} rows</Badge>
          </div>
        ) : (
          <div className="grid-2">
            <Panel label="Your investment policy">
              {summary ? (
                <>
                  <div className="kv"><span className="k">Model name</span><span className="v small">{summary.modelName}</span></div>
                  <div className="kv"><span className="k">Mean target LTV</span><span className="v" data-testid="mean-target-ltv">{pct(summary.meanTargetLtv, 0)}</span></div>
                  <div className="kv"><span className="k">Mean max-bid vs ask</span><span className="v">{pctSignedFormat(summary.meanMaxBidDiscountToAsk)}</span></div>
                </>
              ) : (
                <p className="help" style={{ marginTop: 0 }}>
                  Upload a prediction file to see your policy summary here.
                </p>
              )}
              <hr className="divider" />
              <p className="help" style={{ marginTop: 0 }}>
                The policy is yours. It sets the ceiling your bids are measured against during
                play; deviating is allowed and recorded.
              </p>
            </Panel>

            <Panel label="Upload predictions">
              <p className="help" style={{ marginTop: 0 }}>
                One row per candidate property, from the packet's submission template.
              </p>
              <input
                ref={fileRef}
                type="file"
                accept=".csv,text/csv"
                style={{ display: "none" }}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void onUpload(f);
                }}
              />
              <button
                className="btn btn-secondary btn-block"
                onClick={() => fileRef.current?.click()}
                disabled={busy}
                data-testid="upload-model"
              >
                {busy ? "Validating…" : "Upload prediction CSV"}
              </button>
              {fileName && validated ? (
                <p className="mt-8 help" data-testid="upload-success">
                  {fileName} — {summary?.propertiesMatched ?? 0} / {session.poolCount} properties matched
                </p>
              ) : null}

              {report && !report.ok ? (
                <div className="mt-12" data-testid="upload-errors">
                  <ErrorBox>
                    <strong>The file was not accepted.</strong>
                    <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>
                      {report.errors.slice(0, 6).map((e, i) => (
                        <li key={i}>{e}</li>
                      ))}
                    </ul>
                  </ErrorBox>
                </div>
              ) : null}

              {report && report.ok && report.warnings.length > 0 ? (
                <div className="note-box mt-12" data-testid="upload-warnings">
                  {report.warnings.map((w, i) => (
                    <div key={i}>{w}</div>
                  ))}
                </div>
              ) : null}
            </Panel>
          </div>
        )}

        <div className="mt-16">
          <Panel label="Your team's pre-class forecast">
            {summary && (validated || locked) ? (
              <>
                <div className="grid-2">
                  <div>
                    <div className="kv"><span className="k">Properties matched</span><span className="v" data-testid="matched-count">{summary.propertiesMatched} / {session.poolCount}</span></div>
                    <div className="kv"><span className="k">Mean predicted upside vs ask</span><span className="v">{pctSignedFormat(summary.meanPredictedUpsideVsAsk)}</span></div>
                    <div className="kv"><span className="k">Mean predicted NOI growth</span><span className="v">{pctSignedFormat(summary.meanPredictedNoiGrowth)}</span></div>
                  </div>
                  <div>
                    <div className="kv"><span className="k">Mean downside probability</span><span className="v">{pct(summary.meanDownsideProbability, 0)}</span></div>
                    <div className="kv"><span className="k">Model</span><span className="v small">{summary.modelName}</span></div>
                  </div>
                </div>
                <div className="note-box mt-12">{summary.note}</div>
              </>
            ) : (
              <p className="help" style={{ margin: 0 }}>
                Your forecast summary appears here once a valid file is uploaded. Descriptive
                only — the game never scores a pre-class forecast.
              </p>
            )}
          </Panel>
        </div>

        {validated && !locked ? (
          <div className="mt-20 locked-banner" style={{ justifyContent: "space-between" }}>
            <div>
              <span className="panel-label">Ready to lock</span>
              <div className="l-sub">
                Locking freezes forecasts and policy. {fund.modelRowCount} rows validated.
              </div>
            </div>
            <button className="btn btn-primary btn-lg" onClick={onLock} disabled={busy} data-testid="lock-model">
              Lock model
            </button>
          </div>
        ) : null}

        {locked ? (
          <p className="mt-16 help">
            Waiting for the other funds to lock. Your professor opens Practice when every fund
            has checked in.
          </p>
        ) : null}
      </main>
    </div>
  );
}

function pctSignedFormat(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  const v = value * 100;
  return `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(1)}%`;
}

// Re-exported so the import above stays meaningful if this file grows.
export { money };
