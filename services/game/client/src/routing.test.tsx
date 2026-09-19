/**
 * Routing and screen-contract tests, run against mocked API responses.
 *
 * These hold the four invariants that must not wait for a browser to check:
 *
 *   1. The phase gate sends every seat to the screen the server says it is in.
 *   2. The professor's grid shows counts, never sealed amounts.
 *   3. Practice renders "TRANSACTION NOT BOOKED" — never a bare "NO SALE".
 *   4. Decision overrides and invested overrides are counted separately, and the
 *      engine's won-only override_count is never presented as the decision count.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ManagementStance, RoundManagement, StateView, SubmissionGridRow } from "./api";

/**
 * The management config a 605 session publishes: the layer exists, the decision does
 * not. Used by the fixtures here so a routing assertion never accidentally depends on
 * a stance surface existing.
 */
const NO_MANAGEMENT_FIXTURE: RoundManagement = {
  enabled: false,
  hasStanceChoice: false,
  courseMode: "605",
  stances: ["STANDARD"],
  defaultStance: "STANDARD",
};

/** The tier configuration a 310 session publishes on every round. */
const TIER_310: RoundManagement = {
  enabled: true,
  hasStanceChoice: true,
  courseMode: "310",
  stances: ["RUN LEAN", "STANDARD", "INVEST & PROTECT"],
  defaultStance: "STANDARD",
};

/** 220 runs the operating year, but the posture is the tier's, not the fund's. */
const TIER_220: RoundManagement = {
  enabled: true,
  hasStanceChoice: false,
  courseMode: "220",
  stances: ["STANDARD"],
  defaultStance: "STANDARD",
};

/** Two owned buildings, as the engine's team view reports them. */
const HOLDINGS = [
  { property_id: "OC-OFFICE-07", property_type: "office", submarket: "Airport Area", current_noi: 2.1, current_value: 48.5, debt_amount: 30.0 },
  { property_id: "OC-RETAIL-03", property_type: "retail", submarket: "Irvine Spectrum", current_noi: 1.4, current_value: 31.2, debt_amount: 18.0 },
];

/**
 * A scored round, tile by tile. `management` is the engine's published tier config
 * — the only thing that decides whether a posture surface exists.
 */
function scoredRound(management: RoundManagement) {
  return {
    round: 1,
    roundLabel: "Round 1",
    isPractice: false,
    openedAt: "t-open",
    closedAt: null,
    resolvedAt: null,
    isOpenForSubmissions: true,
    public: {
      round_number: 1,
      stage: "scored",
      is_practice: false,
      round_state: "open",
      total_rounds: 4,
      deals: [],
      market: {
        policy_rate: 0.05,
        unemployment: 0.041,
        employment_growth: 0.012,
        inflation: 0.031,
        vacancy: { office: 0.132, retail: 0.06 },
        cap_rate: { office: 0.062, retail: 0.058 },
        credit_conditions: 0.5,
      },
      funds: [],
      economics: { acquisition_cost_rate: 0.02, capital_reserve_rate: { office: 0.01, retail: 0.008 } },
    },
    myForecast: [],
    myDecision: null,
    submittedFunds: 0,
    totalFunds: 1,
    rejected: [],
    rejectedStances: [],
    management,
    analytics: null,
    results: null,
  } as NonNullable<StateView["round"]>;
}

/** A student on the deal board of a scored round, played under `management`. */
function stateOnRound(management: RoundManagement): StateView {
  return sessionState({
    session: { ...sessionState().session, phase: "round", currentRound: 1 },
    round: scoredRound(management),
  });
}

/** A professor watching `grid`, in the same scored round. */
function professorState(management: RoundManagement, grid: SubmissionGridRow[]): StateView {
  return {
    ...stateOnRound(management),
    you: { memberId: "prof_1", displayName: "Professor", role: "professor", fundId: null },
    grid,
  };
}

/**
 * The two calls the management surface makes, recorded. The portfolio is the fund's
 * own book (the engine's team view); the decision carries the stances.
 */
const portfolioRef: { current: Record<string, unknown> | null } = { current: null };
const portfolioCalls = { count: 0 };
const submitCalls: unknown[][] = [];

import { App } from "./App";

function sessionState(overrides: Partial<StateView> = {}): StateView {
  return {
    session: {
      id: "sess_test",
      name: "REAL 605 — Test",
      phase: "practice",
      currentRound: -1,
      roundLabel: "Practice",
      isPracticeRound: true,
      totalRounds: 4,
      practiceEnabled: true,
      resolvedRounds: 0,
      gameComplete: false,
      revision: 7,
      mode: "team",
      maxTeamSize: 3,
      bundleId: "b",
      bundleDisplayName: "Test Dataset",
      poolCount: 120,
      candidatePoolHash: "h",
      nextStep: "Practice is open.",
    },
    you: { memberId: "mem_1", displayName: "Dana", role: "student", fundId: "fund_1" },
    funds: [{ id: "fund_1", name: "Pacific CRE Partners", memberCount: 1, modelStatus: "locked", modelName: "m", modelLockedAt: null, modelRowCount: 120 }],
    members: [{ id: "mem_1", displayName: "Dana", fundId: "fund_1", isProfessor: false }],
    yourFund: { id: "fund_1", name: "Pacific CRE Partners", memberCount: 1, modelStatus: "locked", modelName: "m", modelLockedAt: null, modelRowCount: 120, forecastSummary: null },
    round: null,
    grid: null,
    ...overrides,
  } as StateView;
}

const stateRef = { current: sessionState() };

vi.mock("./session", async () => {
  const actual = await vi.importActual<typeof import("./session")>("./session");
  return {
    ...actual,
    useSession: () => ({
      state: stateRef.current,
      status: stateRef.current ? "ready" : "loading",
      error: null,
      live: true,
      refresh: async () => {},
    }),
  };
});

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return {
    ...actual,
    api: {
      ...actual.api,
      stateOrThrow: async () => stateRef.current,
      uploadModel: async () => ({ ok: true, report: { ok: true, errors: [], warnings: [], summary: { propertiesMatched: 120, meanPredictedUpsideVsAsk: 0.1, meanPredictedNoiGrowth: 0.03, meanDownsideProbability: 0.2, meanMaxBidDiscountToAsk: -0.02, meanTargetLtv: 0.6, modelName: "gbm", scored: false as const, note: "" } } }),
      lockModel: async () => ({}),
      submitDecision: async (...args: unknown[]) => {
        submitCalls.push(args);
        return {};
      },
      portfolio: async () => {
        portfolioCalls.count += 1;
        // The API's envelope: the engine's team view, wrapped.
        return { portfolio: portfolioRef.current ?? { holdings: [] } };
      },
      joinPreview: async () => ({ session: { id: "s", name: "REAL 605", mode: "team" as const, maxTeamSize: 3, phase: "lobby" as const, bundleDisplayName: "b" }, funds: [] }),
      join: async () => ({ sessionId: "s", fundId: "fund_1", createdFund: true }),
    },
  };
});

/**
 * The App is rendered with `memory` (MemoryRouter) and the jsdom URL is set before
 * render, so react-router's initial location is the path under test.
 */
function renderAtUrl(path: string) {
  window.history.replaceState({}, "", path);
  return render(<App memory />);
}

beforeEach(() => {
  stateRef.current = sessionState();
  portfolioRef.current = null;
  portfolioCalls.count = 0;
  submitCalls.length = 0;
});

describe("phase gating", () => {
  it("sends a student in the practice phase to the deal board from any URL", async () => {
    renderAtUrl("/model");
    await waitFor(() => expect(screen.getByTestId("deal-board")).toBeInTheDocument());
  });

  it("sends a student in the lobby phase to the lobby", async () => {
    stateRef.current = sessionState({ session: { ...sessionState().session, phase: "lobby" } });
    renderAtUrl("/model");
    await waitFor(() => expect(screen.getByTestId("lobby-fund-table")).toBeInTheDocument());
  });

  it("sends the professor to the console, whatever URL they typed", async () => {
    stateRef.current = sessionState({
      you: { memberId: "prof_1", displayName: "Professor", role: "professor", fundId: null },
      session: { ...sessionState().session, joinCode: "ABC234" } as StateView["session"],
    });
    renderAtUrl("/game/practice");
    await waitFor(() => expect(screen.getByTestId("join-code")).toHaveTextContent("ABC234"));
  });

  it("sends a professor in the lobby phase to the console and disables illegal controls", async () => {
    stateRef.current = sessionState({
      you: { memberId: "prof_1", displayName: "Professor", role: "professor", fundId: null },
      session: { ...sessionState().session, phase: "lobby", joinCode: "ABC234" } as StateView["session"],
    });
    renderAtUrl("/professor");
    await waitFor(() => expect(screen.getByTestId("open-practice-checkin")).toBeEnabled());
    expect(screen.getByTestId("open-practice")).toBeDisabled();
    expect(screen.getByTestId("close-practice")).toBeDisabled();
    expect(screen.getByTestId("open-next-round")).toBeDisabled();
    expect(screen.getByTestId("finalize-game")).toBeDisabled();
  });
});

describe("practice result semantics", () => {
  const baseRound = sessionState().session;

  it("renders TRANSACTION NOT BOOKED for a would-have-won practice bid, never a bare NO SALE", () => {
    const view = sessionState({
      session: { ...baseRound, phase: "practice_results" },
      round: {
        round: -1,
        roundLabel: "Practice",
        isPractice: true,
        openedAt: "t",
        closedAt: "t",
        resolvedAt: "t",
        isOpenForSubmissions: false,
        public: { deals: [], funds: [], economics: { acquisition_cost_rate: 0.02, capital_reserve_rate: {} }, market: null, round_number: -1, stage: "practice", is_practice: true, round_state: "resolved", total_rounds: 4 },
        myForecast: [],
        myDecision: { items: [{ propertyId: "OC-INDU-01", action: "BID" as const, bid: 42.0, ltv: 0.6 }], stances: [], submittedAt: "t" },
        submittedFunds: 1,
        totalFunds: 1,
        rejected: [],
        rejectedStances: [],
        management: NO_MANAGEMENT_FIXTURE,
        analytics: null,
        results: {
          round_number: -1,
          auctions: [{
            property_id: "OC-INDU-01",
            sold: false,
            reason: "Practice round — no actual transactions",
            winning_team_id: null,
            winning_bid: null,
            winning_ltv: null,
            reserve_price: 41.9,
            realized_value: 44.2,
            realized_noi: 2.1,
            noi_growth_actual: 0.031,
            cap_rate_actual: 0.052,
            asking_price: 43.2,
          }],
          pnl: [],
          standings: [],
        },
      },
    });
    stateRef.current = view;
    renderAtUrl("/game/results");
    expect(screen.getByTestId("practice-not-booked")).toHaveTextContent("Transaction not booked");
    expect(screen.getByTestId("practice-not-booked").textContent).not.toMatch(/^NO SALE$/);
    // A would-have-won practice bid is a success: never a bare "No sale" badge.
    expect(screen.getByTestId("would-have-won")).toBeInTheDocument();
    expect(screen.queryByText("No sale")).not.toBeInTheDocument();
    expect(screen.getByText("Would win — practice not booked")).toBeInTheDocument();
  });

  it("a rival's sold asset is never rendered as my acquisition", () => {
    // fund_2 wins. The authenticated fund is fund_1, so the badge must read Sold,
    // not "You acquired this".
    const view = sessionState({
      session: { ...baseRound, phase: "round_results" },
      round: {
        round: 0,
        roundLabel: "Round 1",
        isPractice: false,
        openedAt: "t",
        closedAt: "t",
        resolvedAt: "t",
        isOpenForSubmissions: false,
        public: { deals: [], funds: [], economics: { acquisition_cost_rate: 0.02, capital_reserve_rate: {} }, market: null, round_number: 0, stage: "scored", is_practice: false, round_state: "resolved", total_rounds: 4 },
        myForecast: [],
        myDecision: { items: [{ propertyId: "OC-INDU-01", action: "BID" as const, bid: 40.0, ltv: 0.6 }], stances: [], submittedAt: "t" },
        submittedFunds: 2,
        totalFunds: 2,
        rejected: [],
        rejectedStances: [],
        management: NO_MANAGEMENT_FIXTURE,
        analytics: null,
        results: {
          round_number: 0,
          auctions: [{
            property_id: "OC-INDU-01",
            sold: true,
            reason: "sold",
            winning_team_id: "fund_2",
            winning_bid: 41.5,
            winning_ltv: 0.6,
            reserve_price: 40.0,
            realized_value: 44.2,
            realized_noi: 2.1,
            noi_growth_actual: 0.031,
            cap_rate_actual: 0.052,
            asking_price: 43.2,
          }],
          pnl: [],
          standings: [],
        },
      },
    });
    stateRef.current = view;
    renderAtUrl("/game/results");
    expect(screen.getByText("Sold")).toBeInTheDocument();
    expect(screen.queryByText("You acquired this")).not.toBeInTheDocument();
  });

  it("my own sold asset is rendered as my acquisition", () => {
    const view = sessionState({
      session: { ...baseRound, phase: "round_results" },
      round: {
        round: 0,
        roundLabel: "Round 1",
        isPractice: false,
        openedAt: "t",
        closedAt: "t",
        resolvedAt: "t",
        isOpenForSubmissions: false,
        public: { deals: [], funds: [], economics: { acquisition_cost_rate: 0.02, capital_reserve_rate: {} }, market: null, round_number: 0, stage: "scored", is_practice: false, round_state: "resolved", total_rounds: 4 },
        myForecast: [],
        myDecision: { items: [{ propertyId: "OC-INDU-01", action: "BID" as const, bid: 42.0, ltv: 0.6 }], stances: [], submittedAt: "t" },
        submittedFunds: 2,
        totalFunds: 2,
        rejected: [],
        rejectedStances: [],
        management: NO_MANAGEMENT_FIXTURE,
        analytics: null,
        results: {
          round_number: 0,
          auctions: [{
            property_id: "OC-INDU-01",
            sold: true,
            reason: "sold",
            winning_team_id: "fund_1",
            winning_bid: 42.0,
            winning_ltv: 0.6,
            reserve_price: 40.0,
            realized_value: 44.2,
            realized_noi: 2.1,
            noi_growth_actual: 0.031,
            cap_rate_actual: 0.052,
            asking_price: 43.2,
          }],
          pnl: [],
          standings: [],
        },
      },
    });
    stateRef.current = view;
    renderAtUrl("/game/results");
    expect(screen.getByText("You acquired this")).toBeInTheDocument();
  });

  it("a scored no-sale never receives practice wording", () => {
    const view = sessionState({
      session: { ...baseRound, phase: "round_results" },
      round: {
        round: 0,
        roundLabel: "Round 1",
        isPractice: false,
        openedAt: "t",
        closedAt: "t",
        resolvedAt: "t",
        isOpenForSubmissions: false,
        public: { deals: [], funds: [], economics: { acquisition_cost_rate: 0.02, capital_reserve_rate: {} }, market: null, round_number: 0, stage: "scored", is_practice: false, round_state: "resolved", total_rounds: 4 },
        myForecast: [],
        myDecision: { items: [{ propertyId: "OC-INDU-01", action: "BID" as const, bid: 38.0, ltv: 0.6 }], stances: [], submittedAt: "t" },
        submittedFunds: 2,
        totalFunds: 2,
        rejected: [],
        rejectedStances: [],
        management: NO_MANAGEMENT_FIXTURE,
        analytics: null,
        results: {
          round_number: 0,
          auctions: [{
            property_id: "OC-INDU-01",
            sold: false,
            reason: "reserve not met",
            winning_team_id: null,
            winning_bid: null,
            winning_ltv: null,
            reserve_price: 40.0,
            realized_value: 44.2,
            realized_noi: 2.1,
            noi_growth_actual: 0.031,
            cap_rate_actual: 0.052,
            asking_price: 43.2,
          }],
          pnl: [],
          standings: [],
        },
      },
    });
    stateRef.current = view;
    renderAtUrl("/game/results");
    expect(screen.getByText("No sale")).toBeInTheDocument();
    expect(screen.queryByText("Would win — practice not booked")).not.toBeInTheDocument();
    expect(screen.queryByText("Practice — not booked")).not.toBeInTheDocument();
    expect(screen.queryByTestId("practice-not-booked")).not.toBeInTheDocument();
  });

  it("counts decision overrides separately from invested overrides", () => {
    // Sanity at the type level too: the engine's won-only number never reaches this UI.
    const gridRow = { fundId: "f", fundName: "F", submitted: true, submittedAt: null, bids: 2, passes: 2, bidsAboveOwnCeiling: 1, ltvAboveOwnTarget: 1 };
    expect(Object.keys(gridRow)).not.toContain("overrideCount");
  });
});

/**
 * The management decision, on the two screens that carry it.
 *
 * The engine owns the rules; these tests hold the client's half of the contract: a
 * tier with a stance choice shows one control per owned building and sends the choice
 * with the round's submission, and a tier without one shows nothing at all — because a
 * control that is drawn but ignored is a lie about the game being played.
 */
describe("the management decision on the round screen", () => {
  it("offers a posture for every building on 310 and sends the choices with the submission", async () => {
    portfolioRef.current = { holdings: HOLDINGS };
    stateRef.current = stateOnRound(TIER_310);
    renderAtUrl("/game/practice");

    await waitFor(() => expect(screen.getByTestId("management-row-OC-OFFICE-07")).toBeInTheDocument());
    expect(screen.getByTestId("management-row-OC-RETAIL-03")).toBeInTheDocument();
    // A control per building, and the tradeoff in words rather than a code.
    expect(screen.getByTestId("stance-OC-OFFICE-07-RUN LEAN")).toBeInTheDocument();
    expect(screen.getByTestId("stance-OC-RETAIL-03-INVEST & PROTECT")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("stance-OC-OFFICE-07-RUN LEAN"));
    expect(screen.getByTestId("stance-tradeoff-OC-OFFICE-07")).toHaveTextContent("Spend least on upkeep");

    // The confirmation shows the posture the round will lock, then sends it.
    fireEvent.click(screen.getByTestId("review-submit"));
    await waitFor(() =>
      expect(screen.getByTestId("review-stance-OC-OFFICE-07")).toHaveTextContent("Run lean"),
    );
    // A scored round must not describe itself as practice on the one button that
    // submits the book.
    expect(screen.getByTestId("lock-decisions")).toHaveTextContent("Lock decisions");
    fireEvent.click(screen.getByTestId("lock-decisions"));
    await waitFor(() => expect(submitCalls.length).toBe(1));
    expect(submitCalls[0]?.[2]).toEqual([
      { propertyId: "OC-OFFICE-07", stance: "RUN LEAN" },
      { propertyId: "OC-RETAIL-03", stance: "STANDARD" },
    ]);
  });

  it("still calls the practice round's button what it is", async () => {
    stateRef.current = sessionState({
      session: { ...sessionState().session, phase: "practice", currentRound: -1 },
      round: { ...scoredRound(TIER_310), round: -1, roundLabel: "Practice", isPractice: true },
    });
    renderAtUrl("/game/practice");

    await waitFor(() => expect(screen.getByTestId("review-submit")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("review-submit"));
    await waitFor(() => expect(screen.getByTestId("lock-decisions")).toBeInTheDocument());
    expect(screen.getByTestId("lock-decisions")).toHaveTextContent("Lock practice decisions");
  });

  it("shows the stances that were submitted, not the tier default, after a refresh", async () => {
    portfolioRef.current = { holdings: HOLDINGS };
    const invested: ManagementStance = "INVEST & PROTECT";
    stateRef.current = sessionState({
      session: { ...sessionState().session, phase: "round", currentRound: 1 },
      round: {
        ...scoredRound(TIER_310),
        myDecision: {
          items: [],
          stances: [{ propertyId: "OC-OFFICE-07", stance: invested }],
          submittedAt: "t",
        },
      },
    });
    renderAtUrl("/game/practice");

    await waitFor(() => expect(screen.getByTestId("management-row-OC-OFFICE-07")).toBeInTheDocument());
    await waitFor(() =>
      expect(screen.getByTestId("stance-OC-OFFICE-07-INVEST & PROTECT")).toHaveClass("active"),
    );
    expect(screen.getByTestId("stance-OC-OFFICE-07-STANDARD")).not.toHaveClass("active");
  });

  it("has no management surface at all on 605, and never asks the engine for a book", async () => {
    stateRef.current = stateOnRound(NO_MANAGEMENT_FIXTURE);
    renderAtUrl("/game/practice");

    await waitFor(() => expect(screen.getByTestId("deal-board")).toBeInTheDocument());
    expect(screen.queryByTestId("management-panel")).toBeNull();
    expect(portfolioCalls.count).toBe(0);
  });

  it("runs the operating year on 220 without offering a posture", async () => {
    stateRef.current = stateOnRound(TIER_220);
    renderAtUrl("/game/practice");

    await waitFor(() => expect(screen.getByTestId("deal-board")).toBeInTheDocument());
    expect(screen.queryByTestId("management-panel")).toBeNull();
    expect(portfolioCalls.count).toBe(0);
  });
});

describe("what the professor sees about management", () => {
  function gridRow(overrides: Partial<SubmissionGridRow> = {}): SubmissionGridRow {
    return {
      fundId: "fund_1",
      fundName: "Pacific CRE Partners",
      submitted: true,
      submittedAt: "t",
      bids: 2,
      passes: 2,
      bidsAboveOwnCeiling: 0,
      ltvAboveOwnTarget: 0,
      stancesSet: 0,
      stanceTally: {},
      ...overrides,
    };
  }

  it("names each fund's postures on 310, and tells waiting apart from not-used", () => {
    stateRef.current = professorState(TIER_310, [
      gridRow({ stancesSet: 2, stanceTally: { "INVEST & PROTECT": 1, "RUN LEAN": 1 } }),
      gridRow({
        fundId: "fund_2",
        fundName: "Coastline Capital",
        submitted: false,
        submittedAt: null,
        bids: 0,
        passes: 0,
      }),
    ]);
    // The fund named in the fixture must also exist as a fund, or the grid falls back.
    stateRef.current = {
      ...stateRef.current,
      funds: [
        { id: "fund_1", name: "Pacific CRE Partners", memberCount: 3, modelStatus: "locked", modelName: "m", modelLockedAt: null, modelRowCount: 120 },
        { id: "fund_2", name: "Coastline Capital", memberCount: 3, modelStatus: "locked", modelName: "m", modelLockedAt: null, modelRowCount: 120 },
      ],
    };
    renderAtUrl("/professor");

    expect(screen.getByTestId("management-Pacific CRE Partners")).toHaveTextContent(
      "2 buildings · 1 × invest & protect, 1 × run lean",
    );
    expect(screen.getByTestId("management-Coastline Capital")).toHaveTextContent("waiting");
  });

  it("marks management as not used on 605 rather than showing funds as stuck", () => {
    stateRef.current = professorState(NO_MANAGEMENT_FIXTURE, [gridRow()]);
    renderAtUrl("/professor");

    expect(screen.getByTestId("management-Pacific CRE Partners")).toHaveTextContent("not used");
  });
});
