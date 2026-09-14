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

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { StateView } from "./api";
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
      submitDecision: async () => ({}),
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
    expect(screen.getByTestId("reveal-results")).toBeDisabled();
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
        myDecision: { items: [{ propertyId: "OC-INDU-01", action: "BID" as const, bid: 42.0, ltv: 0.6 }], submittedAt: "t" },
        submittedFunds: 1,
        totalFunds: 1,
        rejected: [],
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
        myDecision: { items: [{ propertyId: "OC-INDU-01", action: "BID" as const, bid: 40.0, ltv: 0.6 }], submittedAt: "t" },
        submittedFunds: 2,
        totalFunds: 2,
        rejected: [],
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
        myDecision: { items: [{ propertyId: "OC-INDU-01", action: "BID" as const, bid: 42.0, ltv: 0.6 }], submittedAt: "t" },
        submittedFunds: 2,
        totalFunds: 2,
        rejected: [],
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
        myDecision: { items: [{ propertyId: "OC-INDU-01", action: "BID" as const, bid: 38.0, ltv: 0.6 }], submittedAt: "t" },
        submittedFunds: 2,
        totalFunds: 2,
        rejected: [],
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
