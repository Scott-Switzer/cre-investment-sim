/**
 * Client for the private Python engine.
 *
 * The browser must never reach the engine, and nothing in this service may
 * re-implement it. So this module is deliberately thin and deliberately dumb: it
 * forwards a request, returns the parsed body, and maps the engine's error
 * vocabulary onto this service's. No economics, no arithmetic, no defaults.
 *
 * Two things it does own:
 *
 * **Transport of the game state.** The engine is a pure function of its request, so
 * every round operation does *state in, state out*. That snapshot is the entire
 * hidden game — every reserve price and every future outcome — and it lives in this
 * process and in the server-side database, never in a response body.
 *
 * **The auth seam.** On Cloud Run the engine is a private service: callers present
 * an identity token and IAM decides access. Locally there is no token and the call
 * is plain HTTP to loopback. The seam is one function so that difference never
 * leaks into game logic.
 */

import { GoogleAuth } from "google-auth-library";

import { AppError } from "./errors.js";

export interface EngineConfig {
  readonly baseUrl: string;
  /** Static bearer token: local development, or a service-account key if ever used. */
  readonly token?: string;
  /** If set, mint a Google-signed ID token for this audience instead. Cloud Run. */
  readonly audience?: string;
  readonly timeoutMs?: number;
}

export interface EngineHealth {
  status: string;
  game: string;
  engine_version: string;
  economics_version: string;
  economics_digest: string;
  schema_version: number;
  serde_schema_version: number;
}

/**
 * A dataset as a professor may choose it.
 *
 * This is the engine's `/v1/bundles` shape, and it deliberately has **no seed**: the
 * seed is engine metadata, and a field that cannot be sent is a field that cannot be
 * abused. `EngineBundle` below is the operator/diagnostic view, which does carry the
 * seed and stays server-side.
 */
export interface BundleSummary {
  bundle_id: string;
  display_name: string;
  packet_version: string;
  economics_version: string;
  description: string;
}

export interface EngineBundle {
  bundle_id: string;
  display_name: string;
  engine_version: string;
  economics_version: string;
  economics_digest: string;
  packet_version: string;
  seed: number;
  candidate_pool_hash: string;
  schema_version: number;
  description: string;
}

export interface PoolProperty {
  property_id: string;
  property_name: string;
  property_type: string;
  submarket: string;
  asking_price: number | null;
  max_ltv: number | null;
  [key: string]: unknown;
}

export interface PoolResponse {
  bundle: EngineBundle;
  candidate_pool_hash: string;
  pool_count: number;
  properties: PoolProperty[];
}

export interface EngineDecision {
  team_id: string;
  property_id: string;
  action: "PASS" | "BID";
  bid?: number | null;
  ltv?: number | null;
  model_max_bid?: number | null;
  model_target_ltv?: number | null;
}

export interface EngineTeamSpec {
  team_id: string;
  team_name: string;
  submissions: {
    property_id: string;
    forecast: {
      model_name: string;
      predicted_fair_value: number;
      predicted_noi_growth: number;
      probability_of_downside: number | null;
      confidence: number | null;
    };
    policy: { max_bid: number; target_ltv: number };
  }[];
}

export interface CreateGameResponse {
  bundle: EngineBundle;
  state: unknown;
  public: Record<string, unknown>;
}

export interface OpenRoundResponse {
  state: unknown;
  public: Record<string, unknown>;
  game_complete: boolean;
}

export interface ResolveRoundResponse {
  state: unknown;
  public_results: Record<string, unknown>;
  analytics_updates: Record<string, unknown>[];
  rejected_decisions: { team_id: string; property_id: string; reason: string }[];
  game_complete: boolean;
}

/** UTF-8 JSON bytes, which is how the snapshot is carried and persisted. */
export function encodeState(state: unknown): Uint8Array {
  return new TextEncoder().encode(JSON.stringify(state));
}

export function decodeState(bytes: Uint8Array | null): unknown {
  if (!bytes || bytes.byteLength === 0) return null;
  return JSON.parse(new TextDecoder().decode(bytes));
}

export function stateByteLength(bytes: Uint8Array | null): number {
  return bytes ? bytes.byteLength : 0;
}

/**
 * The engine, as this service uses it.
 *
 * Declared as an interface so the correctness suite can drive the game service with
 * a contract-shaped fake and stay fast, while the milestone suite drives the real
 * Python engine and stays honest. Both satisfy the same port, so neither is a
 * "reduced" version of the other from the perspective of game logic.
 */
export interface Engine {
  health(): Promise<EngineHealth>;
  listBundles(): Promise<{ bundles: BundleSummary[] }>;
  bundlePool(bundleId: string): Promise<PoolResponse>;
  createGameState(
    bundleId: string,
    teams: EngineTeamSpec[],
    scenario?: string,
  ): Promise<CreateGameResponse>;
  openRound(state: unknown): Promise<OpenRoundResponse>;
  resolveRound(state: unknown, decisions: EngineDecision[]): Promise<ResolveRoundResponse>;
  teamView(state: unknown, teamId: string): Promise<Record<string, unknown>>;
}

export class EngineClient implements Engine {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;
  private readonly audience: string | null;
  /** Resolved once, lazily: fetching an identity token per round would add latency
   *  to the one call a class is waiting on. */
  private idTokenClient: Promise<{ getRequestHeaders: () => Promise<unknown> }> | null = null;
  private readonly staticToken: string;

  constructor(config: EngineConfig) {
    this.baseUrl = config.baseUrl.replace(/\/+$/, "");
    this.timeoutMs = config.timeoutMs ?? 30_000;
    this.staticToken = config.token ?? "";
    this.audience = config.audience ?? null;
  }

  private async authHeader(): Promise<Record<string, string>> {
    if (this.audience) {
      try {
        this.idTokenClient ??= new GoogleAuth().getIdTokenClient(this.audience);
        const headers = (await (await this.idTokenClient).getRequestHeaders()) as Record<
          string,
          string
        >;
        const found = Object.entries(headers).find(
          ([name]) => name.toLowerCase() === "authorization",
        );
        if (found) return { authorization: found[1] };
      } catch (err) {
        throw new AppError(
          "engine_unavailable",
          `could not obtain an identity token for the engine: ${
            err instanceof Error ? err.message : String(err)
          }`,
        );
      }
    }
    return this.staticToken ? { authorization: `Bearer ${this.staticToken}` } : {};
  }

  private async request<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    let response: Response;
    try {
      response = await fetch(url, {
        method,
        headers: {
          "content-type": "application/json",
          ...(await this.authHeader()),
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        signal: AbortSignal.timeout(this.timeoutMs),
      });
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err);
      throw new AppError("engine_unavailable", `engine request to ${path} failed: ${detail}`);
    }

    const text = await response.text();
    let parsed: unknown = null;
    if (text) {
      try {
        parsed = JSON.parse(text);
      } catch {
        throw new AppError(
          "engine_unavailable",
          `engine returned non-JSON for ${path} (HTTP ${response.status})`,
        );
      }
    }

    if (!response.ok) {
      const detail = (parsed as { detail?: string } | null)?.detail ?? text ?? "";
      throw new AppError(
        // A 5xx from the engine is an engine problem; a 4xx is a bad call from us.
        response.status >= 500 ? "engine_unavailable" : "bad_request",
        `engine refused ${method} ${path} (HTTP ${response.status}): ${detail}`,
        parsed,
      );
    }
    return parsed as T;
  }

  health(): Promise<EngineHealth> {
    return this.request<EngineHealth>("GET", "/v1/health");
  }

  listBundles(): Promise<{ bundles: BundleSummary[] }> {
    return this.request<{ bundles: BundleSummary[] }>("GET", "/v1/bundles");
  }

  bundlePool(bundleId: string): Promise<PoolResponse> {
    return this.request<PoolResponse>(
      "GET",
      `/v1/bundles/${encodeURIComponent(bundleId)}/pool`,
    );
  }

  createGameState(
    bundleId: string,
    teams: EngineTeamSpec[],
    scenario = "Base Case",
  ): Promise<CreateGameResponse> {
    return this.request<CreateGameResponse>("POST", "/v1/create-game-state", {
      bundle_id: bundleId,
      teams,
      scenario,
    });
  }

  openRound(state: unknown): Promise<OpenRoundResponse> {
    return this.request<OpenRoundResponse>("POST", "/v1/open-round", { state });
  }

  resolveRound(state: unknown, decisions: EngineDecision[]): Promise<ResolveRoundResponse> {
    return this.request<ResolveRoundResponse>("POST", "/v1/resolve-round", {
      state,
      decisions,
    });
  }

  teamView(state: unknown, teamId: string): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>("POST", "/v1/team-view", {
      state,
      team_id: teamId,
    });
  }
}
