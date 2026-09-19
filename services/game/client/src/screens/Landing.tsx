/**
 * The landing. First viewport is the product: three sentences, two actions, and the
 * data-honesty note. Everything else would be a wall of text this product does not
 * need. TRY DEMO mints a real demo session (one human fund against three
 * deterministic bots) and hands the browser its seat — no professor, no uploads.
 */

import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";

import { api } from "../api";
import { PublicTopbar } from "../chrome";
import { useSession } from "../session";

export function Landing() {
  const { status, state } = useSession();
  const [demoBusy, setDemoBusy] = useState(false);
  const [demoError, setDemoError] = useState<string | null>(null);
  const [buildSha, setBuildSha] = useState<string | null>(null);

  // The commit this deployment was built from. It is public metadata about *this*
  // build, not about the game, and it is what turns "I deployed after merging" into
  // something the page itself can be checked against.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch("/v1/health");
        if (!res.ok) return;
        const body = (await res.json()) as { build?: { sha?: string | null } };
        const sha = body.build?.sha;
        if (!cancelled && typeof sha === "string" && sha.trim() !== "") setBuildSha(sha.trim());
      } catch {
        // A footer detail. Losing it must never make the landing page fail.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // A browser with a live seat goes where the session is, not to marketing.
  if (status === "ready" && state) {
    const phase = state.session.phase;
    if (phase === "finale") return <Navigate to="/game/finale" replace />;
    if (phase === "model_checkin") return <Navigate to="/model" replace />;
    if (phase === "practice" || phase === "practice_results")
      return <Navigate to="/game/practice" replace />;
    if (phase === "round" || phase === "round_results")
      return <Navigate to="/game/results" replace />;
    // lobby, model_lock, practice_lock → lobby
    return <Navigate to="/lobby" replace />;
  }
  if (status === "loading") return null;

  async function tryDemo() {
    setDemoBusy(true);
    setDemoError(null);
    try {
      const demo = await api.createDemoSession("Demo Player");
      await api.demoAdvance(demo.sessionId);
      // The cookie now holds the demo seat; the session provider will route. The id is
      // named explicitly because a browser that has played before holds other seats
      // too, and the fresh mount must not wander into one of them.
      // Demo sessions are provisioned with locked models and an open practice
      // round; enter the actual playable board immediately.
      window.location.assign(`/game/practice?s=${encodeURIComponent(demo.sessionId)}`);
    } catch (err) {
      setDemoError(err instanceof Error ? err.message : "The demo could not be created.");
      setDemoBusy(false);
    }
  }

  return (
    <div className="shell">
      <PublicTopbar />
      <main className="hero" style={{ flex: 1 }}>
        <div className="hero-inner">
          <div className="hero-body">
            <span className="eyebrow">REAL 605 · Chapman University</span>
            <h1>
              Turn your pre-class model into live acquisition decisions.
            </h1>
            <p className="hero-sub">
              Build the model before class. In class, your fund bids against the room in a
              sealed auction — and lives with what the year does to the price you paid.
            </p>
            <div className="hero-actions">
              <Link to="/join" className="btn btn-primary btn-lg" data-testid="join-class">
                Join class
              </Link>
              <button
                type="button"
                className="btn btn-ghost btn-lg"
                onClick={tryDemo}
                disabled={demoBusy}
                data-testid="try-demo"
              >
                {demoBusy ? "Preparing…" : "Try demo"}
              </button>
            </div>
            {demoError ? <p className="help mt-8" role="alert">{demoError}</p> : null}
            <div className="hero-note">
              <p className="data-note">
                Semi-synthetic CRE cases calibrated to Orange County market conditions.
                Public market and geographic context is real; property financials and
                future outcomes are simulated for teaching.
              </p>
            </div>
          </div>
        </div>
      </main>
      <footer className="hero-foot">
        <div className="hero-foot-inner">
          <span className="hero-prof">
            Professor?{" "}
            <Link to="/professor" style={{ color: "var(--slate-300)" }}>
              Host a session
            </Link>
          </span>
          <span className="hero-prof">Engine adjudicated · sealed-bid auctions · deterministic</span>
          {buildSha ? (
            <span className="hero-prof" data-testid="build-sha">
              build {buildSha.slice(0, 7)}
            </span>
          ) : null}
        </div>
      </footer>
    </div>
  );
}
