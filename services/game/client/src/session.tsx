/**
 * The one store.
 *
 * The server owns the phase; this provider only mirrors it. On mount it reads the
 * state once, opens the SSE doorbell, and refetches whenever the revision moves.
 * Every screen renders from this single view, so a professor's "open practice" and a
 * student's board cannot disagree for more than one round-trip.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { api, type StateView } from "./api";

interface SessionContextValue {
  state: StateView | null;
  /** Null while loading; "none" when this browser has no seat for any session. */
  status: "loading" | "ready" | "none";
  error: string | null;
  live: boolean;
  refresh: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue>({
  state: null,
  status: "loading",
  error: null,
  live: false,
  refresh: async () => {},
});

/**
 * The session id is NOT read from the URL on purpose. The signed HttpOnly cookie is
 * per session (`cre_game_<id>`), and only the server knows which one this browser
 * belongs to. A URL parameter would let one browser's screen be mistaken for
 * another's seat.
 */
async function discoverSession(): Promise<string | null> {
  try {
    const res = await fetch("/v1/whoami");
    if (!res.ok) return null;
    const body = (await res.json()) as { sessionId?: string };
    return typeof body.sessionId === "string" ? body.sessionId : null;
  } catch {
    return null;
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<StateView | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "none">("loading");
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(false);
  const revisionRef = useRef<number | null>(null);
  const sessionIdRef = useRef<string | null>(null);

  const refresh = useCallback(async () => {
    const sessionId = sessionIdRef.current;
    if (!sessionId) return;
    try {
      const view = await api.stateOrThrow(sessionId);
      revisionRef.current = view.session.revision;
      setState(view);
      setStatus("ready");
      setError(null);
    } catch (err) {
      if (err instanceof Error && /401|unauthenticated/i.test(`${err.message}`)) {
        setStatus("none");
        setState(null);
        sessionIdRef.current = null;
      } else {
        setError(err instanceof Error ? err.message : "Could not reach the game service.");
      }
    }
  }, []);

  // Discover + initial load.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const sessionId = await discoverSession();
      if (cancelled) return;
      if (!sessionId) {
        setStatus("none");
        return;
      }
      sessionIdRef.current = sessionId;
      await refresh();
    })();
    return () => {
      cancelled = true;
    };
  }, [refresh]);

  // The SSE doorbell: a revision number and nothing else. Any movement triggers one
  // authoritative refetch; the event payload itself carries no game state.
  useEffect(() => {
    const sessionId = sessionIdRef.current;
    if (!sessionId || status !== "ready") return;
    const source = new EventSource(`/v1/sessions/${sessionId}/events`);
    source.addEventListener("revision", (event) => {
      setLive(true);
      try {
        const data = JSON.parse((event as MessageEvent<string>).data) as { revision: number };
        if (revisionRef.current === null || data.revision !== revisionRef.current) {
          void refresh();
        }
      } catch {
        void refresh();
      }
    });
    source.onerror = () => setLive(false);
    source.onopen = () => setLive(true);
    return () => source.close();
  }, [status, refresh, state?.session.id]);

  const value = useMemo<SessionContextValue>(
    () => ({ state, status, error, live, refresh }),
    [state, status, error, live, refresh],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

/** Force a re-discovery (used right after join/create hands back a session cookie). */
export function rediscover(): void {
  // A remount of the provider re-runs discovery; navigation achieves that.
  window.location.assign("/");
}

export function useSession(): SessionContextValue {
  return useContext(SessionContext);
}
