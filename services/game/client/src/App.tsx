/**
 * Routing.
 *
 * The phase is server-owned, so the router exists for *deep-linkable screens*
 * (landing, join, professor sign-in) and for stable URLs — not for deciding what a
 * student may see. Every session-scoped screen renders from the server's state view
 * and redirects itself to where the session actually is, so no manual URL navigation
 * is ever required: enter anywhere, land where the game is.
 */

import { BrowserRouter, MemoryRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { Landing } from "./screens/Landing";
import { Join } from "./screens/Join";
import { Lobby } from "./screens/Lobby";
import { ModelCheckIn } from "./screens/ModelCheckIn";
import { Practice } from "./screens/Practice";
import { Results } from "./screens/Results";
import { Waiting } from "./screens/Waiting";
import { Professor } from "./screens/Professor";
import { SessionProvider, useSession } from "./session";
import { Loading } from "./components";

/** Wraps every session-scoped screen: loads state, guards, and stays phase-honest. */
function SessionGate({ children }: { children: React.ReactNode }) {
  const { status, state } = useSession();
  const location = useLocation();

  if (status === "loading") return <Loading />;
  if (status === "none") {
    return <Navigate to="/join" replace state={{ from: location.pathname }} />;
  }
  if (!state) return <Loading />;

  // Phase routing: where the session is decides which screen is real.
  const phase = state.session.phase;
  if (state.you.role === "professor") {
    if (location.pathname !== "/professor") return <Navigate to="/professor" replace />;
    return <>{children}</>;
  }
  void location;
  if (phase === "lobby" && location.pathname !== "/lobby") {
    return <Navigate to="/lobby" replace />;
  }
  if (phase === "model_checkin" && location.pathname !== "/model") {
    return <Navigate to="/model" replace />;
  }
  if ((phase === "practice" || phase === "round") &&
      !location.pathname.startsWith("/game/practice") &&
      !location.pathname.startsWith("/game/waiting")) {
    // /game/waiting is allowed during play only when the fund has already submitted;
    // the Waiting screen itself bounces anyone without a submission back to the board.
    const submitted = Boolean(state.round?.myDecision);
    if (!(location.pathname.startsWith("/game/waiting") && submitted)) {
      return <Navigate to="/game/practice" replace />;
    }
    return <>{children}</>;
  }
  if ((phase === "practice_results" || phase === "round_results" || phase === "finale") && !location.pathname.startsWith("/game/results")) {
    return <Navigate to="/game/results" replace />;
  }
  return <>{children}</>;
}

/**
 * `memory` exists for tests: same routes, no history side effects.
 */
export function App({
  memory = false,
}: {
  memory?: boolean;
}) {
  const Router = memory ? MemoryRouter : BrowserRouter;
  return (
    <SessionProvider>
      <Router>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/join" element={<Join />} />
          <Route
            path="/lobby"
            element={
              <SessionGate>
                <Lobby />
              </SessionGate>
            }
          />
          <Route
            path="/model"
            element={
              <SessionGate>
                <ModelCheckIn />
              </SessionGate>
            }
          />
          <Route
            path="/game/practice"
            element={
              <SessionGate>
                <Practice />
              </SessionGate>
            }
          />
          <Route
            path="/game/waiting"
            element={
              <SessionGate>
                <Waiting />
              </SessionGate>
            }
          />
          <Route
            path="/game/results"
            element={
              <SessionGate>
                <Results />
              </SessionGate>
            }
          />
          {/* The console is its own gate: a seatless browser gets the passcode form,
              not a bounce to /join — the professor's cookie is minted by that form. */}
          <Route path="/professor" element={<Professor />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Router>
    </SessionProvider>
  );
}
