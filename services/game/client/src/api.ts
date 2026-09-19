/**
 * The wire shapes this client consumes.
 *
 * Mirrored from `src/views.ts` and the engine's `public_deal` projection. The client
 * renders these verbatim — it never computes a game number except where the task
 * explicitly assigns presentation arithmetic to the UI (deal-cost and capital-impact
 * line items, which are pure multiplication of published rates by a bid the player
 * has already chosen).
 */

export type Phase =
  | "lobby"
  | "model_checkin"
  | "practice"
  | "practice_results"
  | "round"
  | "round_results"
  | "finale";

export type ModelStatus = "none" | "validated" | "locked";

export interface SessionView {
  id: string;
  name: string;
  phase: Phase;
  currentRound: number;
  roundLabel: string;
  isPracticeRound: boolean;
  totalRounds: number;
  practiceEnabled: boolean;
  resolvedRounds: number;
  gameComplete: boolean;
  revision: number;
  mode: "team" | "individual";
  maxTeamSize: number;
  bundleId: string;
  bundleDisplayName: string;
  poolCount: number;
  candidatePoolHash: string;
  nextStep: string;
  demo: boolean;
  /** The course tier recorded at creation, or null when the engine did not say. */
  courseMode: string | null;
  roundDeadlineAt: number | null;
  timerPausedAt: number | null;
  roundDurationSeconds: number;
}

export interface FundView {
  id: string;
  name: string;
  memberCount: number;
  modelStatus: ModelStatus;
  modelName: string | null;
  modelLockedAt: string | null;
  modelRowCount: number;
}

export interface ForecastSummary {
  propertiesMatched: number;
  meanPredictedUpsideVsAsk: number | null;
  meanPredictedNoiGrowth: number | null;
  meanDownsideProbability: number | null;
  meanMaxBidDiscountToAsk: number | null;
  meanTargetLtv: number | null;
  modelName: string;
  scored: false;
  note: string;
}

export interface MemberView {
  id: string;
  displayName: string;
  fundId: string | null;
  isProfessor: boolean;
}

export interface ForecastRow {
  propertyId: string;
  forecast: {
    modelName: string;
    predictedFairValue: number;
    predictedNoiGrowth: number;
    probabilityOfDownside: number | null;
    confidence: number | null;
  };
  policy: { maxBid: number; targetLtv: number };
}

export interface DecisionItem {
  propertyId: string;
  action: "PASS" | "BID";
  bid: number | null;
  ltv: number | null;
}

/**
 * The engine's own management postures. Mirrored here so the UI cannot invent a
 * fourth one; which of them a session accepts comes from the engine's published
 * course-tier config on every round (`RoundManagement.stances`).
 */
export type ManagementStance = "RUN LEAN" | "STANDARD" | "INVEST & PROTECT";

export interface StanceItem {
  propertyId: string;
  stance: ManagementStance;
}

/** The management rules this round is played under, as the engine published them. */
export interface RoundManagement {
  enabled: boolean;
  hasStanceChoice: boolean;
  courseMode: string | null;
  stances: string[];
  defaultStance: string;
}

export interface RoundView {
  round: number;
  roundLabel: string;
  isPractice: boolean;
  openedAt: string;
  closedAt: string | null;
  resolvedAt: string | null;
  isOpenForSubmissions: boolean;
  public: RoundPublic;
  myForecast: ForecastRow[];
  myDecision: { items: DecisionItem[]; stances: StanceItem[]; submittedAt: string } | null;
  submittedFunds: number;
  totalFunds: number;
  results: RoundResults | null;
  analytics: unknown[] | null;
  rejected: { fundId: string; propertyId: string; reason: string }[];
  /** Management stances the engine refused at resolution, for the fund that sent them. */
  rejectedStances: { fundId: string; propertyId: string; reason: string }[];
  management: RoundManagement;
}

export interface Deal {
  property_id: string;
  property_name: string;
  property_type: "Office" | "Industrial" | "Multifamily" | "Retail" | string;
  submarket: string;
  building_sf: number | null;
  units: number | null;
  year_built: number | null;
  current_noi: number | null;
  occupancy: number | null;
  market_rent: number | null;
  in_place_rent: number | null;
  walt: number | null;
  tenant_concentration: number | null;
  opex_ratio: number | null;
  lease_expiry_profile: string | null;
  property_quality: number | null;
  primary_risk: string | null;
  asking_price: number | null;
  going_in_cap: number | null;
  debt_rate: number | null;
  max_ltv: number | null;
  amortization_years: number | null;
  acquisition_cost_rate: number | null;
  capital_reserve_rate: number | null;
  indicative_capex_exposure: number | null;
  indicative_capex_note: string | null;
}

export interface RoundPublic {
  round_number: number;
  stage: string;
  is_practice: boolean;
  round_state: string;
  total_rounds: number;
  deals: Deal[];
  market: {
    policy_rate: number | null;
    unemployment: number | null;
    employment_growth: number | null;
    inflation: number | null;
    vacancy: Record<string, number | null>;
    cap_rate: Record<string, number | null>;
    credit_conditions: number | null;
  } | null;
  funds: {
    team_id: string;
    team_name: string;
    nav: number;
    cash: number;
    debt: number;
    assets: number;
    cumulative_return: number;
  }[];
  economics: {
    acquisition_cost_rate: number;
    capital_reserve_rate: Record<string, number>;
    /** Present once the engine publishes course tiers; absent on an older engine. */
    management?: {
      enabled: boolean;
      course_mode: string | null;
      has_stance_choice: boolean;
      stances: string[];
      default_stance: string;
    };
  };
}

export interface Auction {
  property_id: string;
  sold: boolean;
  reason: string;
  winning_team_id: string | null;
  winning_bid: number | null;
  winning_ltv: number | null;
  reserve_price: number | null;
  realized_value: number | null;
  realized_noi: number | null;
  noi_growth_actual: number | null;
  cap_rate_actual: number | null;
  asking_price: number | null;
}

export interface RoundResults {
  round_number: number;
  auctions: Auction[];
  pnl: {
    team_id: string;
    team_name: string;
    nav: number;
    cumulative_return: number;
    value_channel: number;
    noi_income: number;
    interest_paid: number;
    acquisition_costs: number;
    reserves: number;
    net_carry: number;
    gross_ltv: number;
    weighted_debt_rate: number;
    return_on_cost: number;
    assets: number;
  }[];
  standings: {
    rank: number;
    team_id: string;
    team_name: string;
    nav: number;
    cash: number;
    debt: number;
    assets: number;
    cumulative_return: number;
  }[];
}

export interface SubmissionGridRow {
  fundId: string;
  fundName: string;
  submitted: boolean;
  submittedAt: string | null;
  bids: number;
  passes: number;
  bidsAboveOwnCeiling: number;
  ltvAboveOwnTarget: number;
  /** How many buildings this fund set a stance for this round. */
  stancesSet: number;
  /** Counts of postures chosen, by the engine's stance names. Never an amount. */
  stanceTally: Record<string, number>;
}

export interface StateView {
  session: SessionView;
  you: {
    memberId: string;
    displayName: string;
    role: "student" | "professor";
    fundId: string | null;
  };
  funds: FundView[];
  members: MemberView[];
  yourFund: (FundView & { forecastSummary: ForecastSummary | null }) | null;
  round: RoundView | null;
  /** Professor only. Counts and override tallies, never sealed amounts. */
  grid: SubmissionGridRow[] | null;
  /** Present only after the professor finalizes — same for every audience. */
  finale: Finale | null;
}

export interface FinaleStandingRow {
  rank: number;
  fund_id: string;
  fund_name: string;
  nav: number;
  cash: number;
  debt: number;
  assets: number;
  cumulative_return: number;
  portfolio_ltv: number | null;
}

export interface Finale {
  standings: FinaleStandingRow[];
  analytics: Record<string, unknown>[];
  debrief: Record<string, unknown>;
}

export interface JoinPreviewFund {
  id: string;
  name: string;
  memberCount: number;
  modelStatus: ModelStatus;
}

export interface JoinPreview {
  session: {
    id: string;
    name: string;
    mode: "team" | "individual";
    maxTeamSize: number;
    phase: Phase;
    bundleDisplayName: string;
  };
  funds: JoinPreviewFund[];
}

export interface ModelRead {
  model: {
    fundId: string;
    modelName: string;
    rowCount: number;
    validatedAt: string;
    lockedAt: string | null;
    rows: ForecastRow[];
  };
}

export interface UploadReport {
  ok: boolean;
  errors: string[];
  warnings: string[];
  summary: ForecastSummary;
}

// ── errors ────────────────────────────────────────────────────────────────

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  constructor(status: number, code: string, detail: string) {
    super(detail);
    this.status = status;
    this.code = code;
  }
}

function detailOf(body: unknown): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail?: unknown }).detail;
    if (typeof d === "string") return d;
  }
  return "Something went wrong. Try again.";
}

async function handle(res: Response): Promise<unknown> {
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = { detail: text };
  }
  if (!res.ok) {
    const code =
      body && typeof body === "object" && "error" in body
        ? String((body as { error?: unknown }).error)
        : `http_${res.status}`;
    throw new ApiError(res.status, code, detailOf(body));
  }
  return body;
}

// ── calls ─────────────────────────────────────────────────────────────────

async function post(path: string, body: unknown, headers: Record<string, string> = {}): Promise<unknown> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return handle(res);
}

export const api = {
  joinPreview(code: string): Promise<JoinPreview> {
    return fetch(`/v1/join/preview?code=${encodeURIComponent(code)}`).then(handle) as Promise<JoinPreview>;
  },

  join(input: { joinCode: string; displayName: string; fundId?: string | null; newFundName?: string | null }) {
    return post("/v1/join", input) as Promise<{ sessionId: string; fundId: string; createdFund: boolean }>;
  },

  reclaim(sessionId: string, displayName: string) {
    return post(`/v1/sessions/${sessionId}/reclaim`, { displayName }) as Promise<{ sessionId: string }>;
  },

  state(sessionId: string, since?: number | null): Promise<StateView | { unchanged: true; revision: number }> {
    const q = since === undefined || since === null ? "" : `?since=${since}`;
    return fetch(`/v1/sessions/${sessionId}/state${q}`).then(handle) as Promise<
      StateView | { unchanged: true; revision: number }
    >;
  },

  stateOrThrow(sessionId: string): Promise<StateView> {
    return api.state(sessionId) as Promise<StateView>;
  },

  uploadModel(sessionId: string, fundId: string, csv: string): Promise<{ ok: boolean; report: UploadReport }> {
    return fetch(`/v1/sessions/${sessionId}/funds/${fundId}/model`, {
      method: "POST",
      headers: { "content-type": "text/csv" },
      body: csv,
    }).then(handle) as Promise<{ ok: boolean; report: UploadReport }>;
  },

  lockModel(sessionId: string, fundId: string) {
    return post(`/v1/sessions/${sessionId}/funds/${fundId}/model/lock`, {}) as Promise<{
      fund: FundView;
    }>;
  },

  lockManualModel(sessionId: string, fundId: string) {
    return post(`/v1/sessions/${sessionId}/funds/${fundId}/model/manual`, {}) as Promise<{
      fund: FundView;
    }>;
  },

  readModel(sessionId: string, fundId: string): Promise<ModelRead> {
    return fetch(`/v1/sessions/${sessionId}/funds/${fundId}/model`).then(handle) as Promise<ModelRead>;
  },

  submitDecision(sessionId: string, items: DecisionItem[], stances: StanceItem[] = []) {
    return post(`/v1/sessions/${sessionId}/rounds/decision`, { items, stances }) as Promise<{
      decision: unknown;
    }>;
  },

  // Professor actions. `expectedRevision` becomes If-Match: acting on the version
  // the console actually saw is what makes a double-click refuse instead of fire.
  beginCheckIn(sessionId: string, expectedRevision: number) {
    return post(`/v1/sessions/${sessionId}/checkin/begin`, {}, { "if-match": String(expectedRevision) });
  },
  startGame(sessionId: string, expectedRevision: number) {
    return post(`/v1/sessions/${sessionId}/game/start`, {}, { "if-match": String(expectedRevision) });
  },
  closeRound(sessionId: string, expectedRevision: number) {
    return post(`/v1/sessions/${sessionId}/rounds/close`, {}, { "if-match": String(expectedRevision) });
  },

  /** Re-issue a professor cookie for a session this passcode owns. */
  rejoinProfessor(sessionId: string, passcode: string, displayName: string) {
    return post(`/v1/sessions/${sessionId}/professor`, { passcode, displayName });
  },

  createSession(input: {
    name: string;
    professorPasscode: string;
    professorName: string;
    mode: "team" | "individual";
    maxTeamSize: number;
    totalRounds: number;
    practiceEnabled: boolean;
    roundTimerSeconds: number;
    /** 605 (default) / 310 / 220. The engine validates and records it. */
    courseMode: string;
  }) {
    return post("/v1/sessions", input) as Promise<{
      sessionId: string;
      joinCode: string;
      session: Record<string, unknown>;
    }>;
  },

  openRound(sessionId: string, expectedRevision: number) {
    return post(`/v1/sessions/${sessionId}/rounds/open`, {}, { "if-match": String(expectedRevision) });
  },

  finalize(sessionId: string, expectedRevision: number) {
    return post(
      `/v1/sessions/${sessionId}/game/finalize`,
      {},
      { "if-match": String(expectedRevision) },
    );
  },

  setTimer(sessionId: string, durationSeconds: number, expectedRevision: number) {
    return post(
      `/v1/sessions/${sessionId}/timer`,
      { durationSeconds },
      { "if-match": String(expectedRevision) },
    );
  },

  pauseTimer(sessionId: string, expectedRevision: number) {
    return post(`/v1/sessions/${sessionId}/timer/pause`, {}, { "if-match": String(expectedRevision) });
  },

  resumeTimer(sessionId: string, expectedRevision: number) {
    return post(
      `/v1/sessions/${sessionId}/timer/resume`,
      {},
      { "if-match": String(expectedRevision) },
    );
  },

  portfolio(sessionId: string, fundId: string): Promise<{ portfolio: Record<string, unknown> }> {
    return fetch(`/v1/sessions/${sessionId}/funds/${fundId}/portfolio`).then(handle) as Promise<{
      portfolio: Record<string, unknown>;
    }>;
  },

  exportUrl(sessionId: string): string {
    return `/v1/sessions/${sessionId}/export`;
  },

  createDemoSession(displayName: string) {
    return post("/v1/demo/session", { displayName }) as Promise<{
      sessionId: string;
      fundId: string;
      joinCode: string;
      name: string;
    }>;
  },

  demoAdvance(sessionId: string) {
    return post(`/v1/sessions/${sessionId}/demo/advance`, {});
  },
};
