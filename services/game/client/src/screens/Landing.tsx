/**
 * The landing. First viewport is the product: three sentences, two actions, and the
 * data-honesty note. Everything else would be a wall of text this product does not
 * need.
 */

import { Link, Navigate } from "react-router-dom";

import { PublicTopbar } from "../chrome";
import { useSession } from "../session";

export function Landing() {
  const { status, state } = useSession();

  // A browser with a live seat goes where the session is, not to marketing.
  if (status === "ready" && state) return <Navigate to="/lobby" replace />;
  if (status === "loading") return null;

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
              <button type="button" className="btn btn-ghost btn-lg" disabled title="Available in a later phase">
                Try demo — coming soon
              </button>
            </div>
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
        </div>
      </footer>
    </div>
  );
}
