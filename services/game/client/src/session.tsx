/**
 * The one store.
 *
 * The server owns the phase; this provider only mirrors it. On mount it reads the
 * state once, opens the SSE doorbell, and refetches whenever the revision moves.
 * Every screen renders from this single view, so a professor's "open practice" and a
 * student's board cannot disagree for more than one round-trip.
 *
 * ## Which session is this?
 *
 * A browser can hold more than one seat: a student in two sections, a professor
 * running two, anyone who clicked a second class link. Cookies are per session
 * (`cre_game_<id>`), so both seats are real and neither is "the" one. Asking
 * `/v1/whoami` without saying which is meant therefore has no correct answer — and
 * taking the cookie the browser happened to send first meant a student who joined a
 * second class landed in the first, silently.
 *
 * So the client states which session it means and pins the answer per tab:
 *
 *   1. `?s=<id>` — the one moment the session is known for certain, because join,
 *      reclaim and demo all just handed back an id.
 *   2. the tab's pin — what this tab resolved to last, so a refresh stays put.
 *   3. nothing — the server answers only if it is unambiguous; otherwise it lists
 *      the seats held and the player chooses.
 *
 * `/v1/whoami?session=<id>` never replies with a different session, so a stale or
 * shared link cannot open someone else's class. The pin lives in `sessionStorage`,
 * not `localStorage`: it is per tab, which is what lets one browser run two sections
 * in two tabs.
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

/** A seat this browser actually holds, as the server confirms it. */
export interface HeldSession {
  sessionId: string;
  role: "student" | "professor";
  memberId: string;
}

export interface WhoamiAnswer {
  sessionId: string | null;
  sessions: HeldSession[];
  ambiguous: boolean;
}

interface SessionContextValue {
  state: StateView | null;
  /** Null while loading; "none" when this browser has no seat for any session. */
  status: "loading" | "ready" | "none";
  error: string | null;
  live: boolean;
  refresh: () => Promise<void>;
  /** Every seat this browser holds. More than one means the player must pick. */
  sessions: HeldSession[];
  /** True when the browser holds several seats and none has been chosen. */
  ambiguous: boolean;
  /** Enter one of the held seats, on this tab only. */
  chooseSession: (sessionId: string) => Promise<void>;
}

const SessionContext = createContext<SessionContextValue>({
  state: null,
  status: "loading",
  error: null,
  live: false,
  refresh: async () => {},
  sessions: [],
  ambiguous: false,
  chooseSession: async () => {},
});

const PIN_KEY = "cre_session";

export function readPin(): string | null {
  try {
    return window.sessionStorage.getItem(PIN_KEY);
  } catch {
    // Private mode, or storage disabled. Discovery still works; it just re-asks.
    return null;
  }
}

export function writePin(sessionId: string | null): void {
  try {
    if (sessionId) window.sessionStorage.setItem(PIN_KEY, sessionId);
    else window.sessionStorage.removeItem(PIN_KEY);
  } catch {
    /* nothing to do — the pin is an optimization, never the source of truth */
  }
}

/**
 * `?s=<id>`, as set by join, reclaim and demo. It only ever *names* a session: the
 * signed cookie is still what proves the seat, so a link with someone else's id is
 * answered with a refusal rather than their screen.
 */
export function sessionHintFromUrl(search: string): string | null {
  const value = new URLSearchParams(search).get("s");
  const trimmed = value?.trim();
  return trimmed ? trimmed : null;
}

export async function askWhoami(sessionId: string | null): Promise<WhoamiAnswer> {
  const query = sessionId ? `?session=${encodeURIComponent(sessionId)}` : "";
  try {
    const res = await fetch(`/v1/whoami${query}`);
    if (!res.ok) return { sessionId: null, sessions: [], ambiguous: false };
    const body = (await res.json()) as Partial<WhoamiAnswer>;
    return {
      sessionId: typeof body.sessionId === "string" ? body.sessionId : null,
      sessions: Array.isArray(body.sessions) ? body.sessions : [],
      ambiguous: Boolean(body.ambiguous),
    };
  } catch {
    return { sessionId: null, sessions: [], ambiguous: false };
  }
}

/**
 * The seats to name before falling back to ambiguity, in priority order. Each is tried
 * in turn and the first that the server confirms wins; a hint this browser holds no
 * grant for is simply skipped, so a stale pin or a borrowed link is inert.
 */
export async function resolveSession(
  ask: (sessionId: string | null) => Promise<WhoamiAnswer>,
  hints: readonly (string | null)[],
): Promise<WhoamiAnswer> {
  for (const hint of hints) {
    if (!hint) continue;
    const answer = await ask(hint);
    if (answer.sessionId) return answer;
  }
  return ask(null);
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<StateView | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "none">("loading");
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(false);
  const [sessions, setSessions] = useState<HeldSession[]>([]);
  const [ambiguous, setAmbiguous] = useState(false);
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
        writePin(null);
      } else {
        setError(err instanceof Error ? err.message : "Could not reach the game service.");
      }
    }
  }, []);

  const chooseSession = useCallback(
    async (sessionId: string) => {
      writePin(sessionId);
      sessionIdRef.current = sessionId;
      setStatus("loading");
      await refresh();
    },
    [refresh],
  );

  // Discover + initial load.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const answer = await resolveSession(askWhoami, [
        sessionHintFromUrl(window.location.search),
        readPin(),
      ]);
      if (cancelled) return;
      setSessions(answer.sessions);
      setAmbiguous(answer.ambiguous);
      if (!answer.sessionId) {
        setStatus("none");
        return;
      }
      writePin(answer.sessionId);
      sessionIdRef.current = answer.sessionId;
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
    () => ({ state, status, error, live, refresh, sessions, ambiguous, chooseSession }),
    [state, status, error, live, refresh, sessions, ambiguous, chooseSession],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

/**
 * Force a re-discovery, keeping the session this browser just joined.
 *
 * A remount of the provider re-runs discovery; a full navigation achieves that, and
 * passing the id through `?s=` is what stops the fresh mount from picking a seat the
 * player did not ask for.
 */
export function rediscover(sessionId?: string | null): void {
  window.location.assign(sessionId ? `/?s=${encodeURIComponent(sessionId)}` : "/");
}

export function useSession(): SessionContextValue {
  return useContext(SessionContext);
}
