/**
 * Results, with the practice semantics kept honest.
 *
 * Practice never books a property: the outcome is rendered as PRACTICE OUTCOME —
 * TRANSACTION NOT BOOKED, never as a bare "no sale", and the would-have-won case says
 * exactly that. After reveal the seller's reserve, the realized year and the would-be
 * winner are shown, because that is the teaching payoff of the rehearsal.
 *
 * Ownership is decided by the authenticated student's fund id, never by comparing an
 * auction field to itself. The round's practice flag arrives from the session view —
 * the round mode is real, not inferred from the auction.
 *
 * Feedback states are FORECAST / POLICY / OUTCOME. Override terminology is explicit:
 * a *decision* override is any submitted choice that deviated from the locked policy,
 * whether or not the bid won; an *invested* override is one that became an acquired
 * property. The engine's own `override_count` is won-only, so it is never presented
 * as the decision count.
 */

import { Navigate } from "react-router-dom";
import { useState } from "react";

import { SessionTopbar } from "../chrome";
import { Badge, Kv, Panel } from "../components";
import { money, moneySigned, pct, signedPercent } from "../format";
import { imageForProperty } from "../propertyImages";
import { useSession } from "../session";
import type { Auction, Deal, ForecastRow, RoundResults, StateView } from "../api";

interface DecisionRecord {
  action: "PASS" | "BID";
  bid: number | null;
  ltv: number | null;
}

/**
 * The NAV bridge. Every line is an engine-published channel: the starting NAV is
 * derived as ending NAV minus the channels, and the bridge must reconcile exactly —
 * that identity is what the round "charged" the fund. Nothing here is a client-side
 * economic calculation; it is a rearrangement of the engine's own numbers.
 */
export function navBridge(pnl: RoundResults["pnl"][number] | null): {
  startingNav: number;
  endingNav: number;
  lines: { label: string; amount: number; positive?: boolean }[];
  residual: number;
} | null {
  if (!pnl) return null;
  const channels =
    pnl.value_channel + pnl.noi_income - pnl.interest_paid - pnl.acquisition_costs - pnl.reserves;
  const startingNav = pnl.nav - channels;
  return {
    startingNav,
    endingNav: pnl.nav,
    lines: [
      { label: "Value change", amount: pnl.value_channel },
      { label: "NOI", amount: pnl.noi_income },
      { label: "Interest", amount: -pnl.interest_paid },
      { label: "Acquisition costs", amount: -pnl.acquisition_costs },
      { label: "Capital reserves", amount: -pnl.reserves },
    ],
    residual: pnl.nav - startingNav - channels,
  };
}

function NavBridgePanel({ pnl }: { pnl: RoundResults["pnl"][number] | null }) {
  const bridge = navBridge(pnl);
  if (!bridge) return null;
  return (
    <Panel label="NAV bridge" data-testid="nav-bridge">
      <div className="bridge">
        <div className="bridge-row" data-testid="bridge-starting">
          <span>Starting NAV</span>
          <span className="mono">{money(bridge.startingNav)}</span>
        </div>
        {bridge.lines.map((line) => (
          <div className="bridge-row" key={line.label}>
            <span className={line.amount >= 0 ? "bridge-plus" : "bridge-minus"}>
              {line.amount >= 0 ? "+" : "−"} {line.label}
            </span>
            <span className="mono">{moneySigned(line.amount, 2)}</span>
          </div>
        ))}
        <div className="bridge-row bridge-total" data-testid="bridge-ending">
          <span>= Ending NAV</span>
          <span className="mono">{money(bridge.endingNav)}</span>
        </div>
      </div>
      <p className="help mt-8">
        Every line is the engine's published channel for this year. The bridge reconciles to
        the cent: no unexplained residual.
      </p>
    </Panel>
  );
}

export function Results() {
  const { state } = useSession();
  if (!state) return null;

  const { session } = state;
  if (session.phase === "practice" || session.phase === "round") {
    return <Navigate to="/game/practice" replace />;
  }
  if (session.phase === "lobby") return <Navigate to="/lobby" replace />;
  if (session.phase === "model_checkin") return <Navigate to="/model" replace />;

  const round = state.round;
  const results = round?.results;
  if (!results) {
    return (
      <div className="shell">
        <SessionTopbar state={state} />
        <main className="shell-main narrow">
          <Panel>
            <p className="help" style={{ margin: 0 }}>
              The market is closing. Results appear the moment the professor resolves the
              round — this page updates itself.
            </p>
          </Panel>
        </main>
      </div>
    );
  }

  const deals = round?.public.deals ?? [];
  const forecasts = new Map((round?.myForecast ?? []).map((f) => [f.propertyId, f]));
  const myItems = new Map(
    (round?.myDecision?.items ?? []).map((i) => [i.propertyId, i as DecisionRecord]),
  );
  const pnl = results.pnl.find((p) => p.team_id === state.you.fundId) ?? null;
  const isPractice = Boolean(round?.isPractice);
  const myFundId = state.you.fundId;

  return (
    <div className="shell">
      <SessionTopbar state={state} />
      <main className="shell-main">
        <div className="page-head">
          <span className="panel-label">{isPractice ? "Practice outcome" : "Market result"}</span>
          <h2>{round?.roundLabel ?? session.roundLabel} — resolved</h2>
          <p className="sub">
            {isPractice
              ? "Practice does not add properties to your portfolio or change NAV."
              : "The reserve is published, the year is realized, and holdings are marked."}
          </p>
        </div>

        <div className="stack">
          {isPractice ? <PracticeNotBooked /> : null}

          {results.auctions.map((auction) => (
            <AuctionBlock
              key={auction.property_id}
              auction={auction}
              deal={deals.find((d) => d.property_id === auction.property_id) ?? null}
              forecast={forecasts.get(auction.property_id)}
              myItem={myItems.get(auction.property_id) ?? null}
              myFundId={myFundId}
              isPractice={isPractice}
              rejectedReason={
                round?.rejected.find(
                  (r) => r.propertyId === auction.property_id && r.fundId === state.you.fundId,
                )?.reason ?? null
              }
            />
          ))}

          <FeedbackPanel
            state={state}
            forecasts={forecasts}
            results={results}
            myItems={myItems}
            isPractice={isPractice}
          />

          {pnl ? (
            <Panel label={isPractice ? "Practice leaves your books unchanged" : "Your fund after this year"}>
              <div className="grid-2">
                <div>
                  <Kv k="NAV" v={money(pnl.nav)} strong />
                  <Kv k="Properties" v={String(pnl.assets)} />
                </div>
                <div>
                  <Kv k="Cumulative return" v={pct(pnl.cumulative_return, 1)} />
                  {round && !isPractice ? (
                    <>
                      <Kv k="NOI income" v={moneySigned(pnl.noi_income, 2)} />
                      <Kv k="Interest paid" v={moneySigned(-Math.abs(pnl.interest_paid), 2)} />
                      <Kv k="Acquisition costs" v={moneySigned(-Math.abs(pnl.acquisition_costs), 2)} />
                      <Kv k="Capital reserves" v={moneySigned(-Math.abs(pnl.reserves), 2)} />
                      <Kv k="Value change" v={moneySigned(pnl.value_channel, 2)} />
                    </>
                  ) : (
                    <Kv k="Channels" v={<span className="v small">unchanged by design</span>} />
                  )}
                </div>
              </div>
            </Panel>
          ) : null}

          {!isPractice ? <NavBridgePanel pnl={pnl} /> : null}

          {!isPractice ? <Leaderboard results={results} state={state} /> : null}
        </div>
      </main>
    </div>
  );
}

// ── leaderboard ───────────────────────────────────────────────────────────

function Leaderboard({ results, state }: { results: RoundResults; state: StateView }) {
  const [tab, setTab] = useState<"game" | "analytics">("game");
  const rows = [...results.standings].sort((a, b) => a.rank - b.rank);
  const analytics = state.round?.analytics ?? [];
  const analyticsRows = analytics
    .map((row) => {
      const a = row as Record<string, unknown>;
      const teamId = String(a.team_id ?? a.fund_id ?? "");
      const teamName = String(a.team_name ?? a.fund_name ?? teamId);
      const standing = results.standings.find((s) => s.team_id === teamId);
      return {
        teamId,
        teamName,
        valuationMae: typeof a.valuation_mae === "number" ? a.valuation_mae : null,
        noiGrowthMae: typeof a.noi_growth_mae === "number" ? a.noi_growth_mae : null,
        downsideCalibration:
          typeof a.downside_calibration === "number" ? a.downside_calibration : null,
        nav: standing?.nav ?? null,
      };
    })
    .filter((row) => row.valuationMae !== null || row.noiGrowthMae !== null);

  return (
    <Panel label="Standings">
      <div className="tabs" role="tablist">
        <button
          role="tab"
          aria-selected={tab === "game"}
          className={tab === "game" ? "tab active" : "tab"}
          onClick={() => setTab("game")}
        >
          Game
        </button>
        <button
          role="tab"
          aria-selected={tab === "analytics"}
          className={tab === "analytics" ? "tab active" : "tab"}
          onClick={() => setTab("analytics")}
        >
          Analytics
        </button>
      </div>

      {tab === "game" ? (
        <table className="board" data-testid="game-leaderboard">
          <thead>
            <tr>
              <th>Rank</th>
              <th>Fund</th>
              <th className="num">NAV</th>
              <th className="num">Return</th>
              <th className="num">Cash</th>
              <th className="num">Assets</th>
              <th className="num">LTV</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const isMine = row.team_id === state.you.fundId;
              const pnlRow = results.pnl.find((p) => p.team_id === row.team_id);
              return (
                <tr key={row.team_id} className={isMine ? "mine" : undefined} data-testid={`standing-${row.rank}`}>
                  <td>{row.rank}</td>
                  <td>{row.team_name}</td>
                  <td className="num mono">{money(row.nav, 0)}</td>
                  <td className="num mono">{pct(row.cumulative_return, 1)}</td>
                  <td className="num mono">{money(row.cash, 0)}</td>
                  <td className="num">{row.assets}</td>
                  <td className="num mono">{pnlRow ? pct(pnlRow.gross_ltv, 0) : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : (
        <>
          {analyticsRows.length > 0 ? (
            <table className="board" data-testid="analytics-leaderboard">
              <thead>
                <tr>
                  <th>Fund</th>
                  <th className="num">Valuation MAE</th>
                  <th className="num">NOI-growth MAE</th>
                  <th className="num">Downside calibration</th>
                </tr>
              </thead>
              <tbody>
                {analyticsRows.map((row) => (
                  <tr key={row.teamId}>
                    <td>{row.teamName}</td>
                    <td className="num mono">{row.valuationMae === null ? "—" : money(row.valuationMae, 0)}</td>
                    <td className="num mono">{row.noiGrowthMae === null ? "—" : pct(row.noiGrowthMae, 1)}</td>
                    <td className="num mono">{row.downsideCalibration === null ? "—" : pct(row.downsideCalibration, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="help">
              Model-quality metrics appear once the round resolves. They measure the model —
              separately from game performance, which measures the fund.
            </p>
          )}
          <p className="help mt-8">
            Model quality and NAV are never combined into one score: a good model can run a
            losing fund and a weak model can run a lucky one. Both matter, separately.
          </p>
        </>
      )}
    </Panel>
  );
}

/** The one place the practice semantics get their headline. */
function PracticeNotBooked() {
  return (
    <div className="locked-banner" data-testid="practice-not-booked">
      <div>
        <span className="panel-label">Practice outcome</span>
        <div className="l-sub" style={{ fontSize: 15, fontWeight: 600, color: "var(--white)" }}>
          Transaction not booked
        </div>
        <div className="l-sub">
          Practice does not add this property to your portfolio or change NAV. The market
          mechanics were real; the books are not touched.
        </div>
      </div>
    </div>
  );
}

function AuctionBlock({
  auction,
  deal,
  forecast,
  myItem,
  myFundId,
  isPractice,
  rejectedReason,
}: {
  auction: Auction;
  deal: Deal | null;
  forecast: ForecastRow | undefined;
  myItem: DecisionRecord | null;
  myFundId: string | null;
  isPractice: boolean;
  rejectedReason: string | null;
}) {
  const image = imageForProperty(deal?.property_type ?? "Office", auction.property_id);
  const won = auction.sold && auction.winning_team_id !== null;
  // Ownership is the authenticated fund id, not the auction echoing itself.
  const iWon = won && myFundId !== null && auction.winning_team_id === myFundId;
  const myBid = myItem?.action === "BID" ? myItem.bid : null;
  const wouldHaveWon = !won && myBid !== null && auction.reserve_price !== null && myBid >= auction.reserve_price;
  const belowReserve = !won && myBid !== null && !wouldHaveWon;
  const override =
    myBid !== null && forecast
      ? {
          price: myBid > forecast.policy.maxBid + 1e-9,
          ltv: (myItem?.ltv ?? 0) > forecast.policy.targetLtv + 1e-9,
          priceDelta: myBid - forecast.policy.maxBid,
          ltvDelta: (myItem?.ltv ?? 0) - forecast.policy.targetLtv,
        }
      : null;

  const decisionBadges = decisionBadgesFor({
    auction,
    forecast,
    myItem,
    myFundId,
    isPractice,
  });

  // The badge must never contradict the teaching outcome. In practice a would-have-won
  // bid is a success — "No sale" would read as an auction failure.
  let outcomeBadge: React.ReactNode;
  if (iWon) {
    outcomeBadge = <Badge tone="ok">You acquired this</Badge>;
  } else if (won) {
    outcomeBadge = <Badge tone="neutral">Sold</Badge>;
  } else if (isPractice && wouldHaveWon) {
    outcomeBadge = <Badge tone="navy">Would win — practice not booked</Badge>;
  } else if (isPractice) {
    outcomeBadge = <Badge tone="neutral">Practice — not booked</Badge>;
  } else {
    outcomeBadge = <Badge tone="neutral">No sale</Badge>;
  }

  return (
    <div className="card" data-testid={`auction-${auction.property_id}`}>
      <div className="spread" style={{ padding: "14px 20px 0" }}>
        <div className="row">
          <div className="deal-img" style={{ width: 108, borderRadius: 8, flex: "0 0 auto", aspectRatio: "16/10" }}>
            <img src={image.url} alt="" aria-hidden="true" style={{ borderRadius: 8 }} title={`${image.credit} — illustrative, not this address`} />
          </div>
          <div>
            <div className="deal-name">{deal?.property_name ?? auction.property_id}</div>
            <div className="deal-sub">
              {deal ? `${deal.property_type} · ${deal.submarket}` : ""} · asked {money(auction.asking_price)}
            </div>
          </div>
        </div>
        <div>{outcomeBadge}</div>
      </div>

      {decisionBadges.length > 0 ? (
        <div className="card-pad fb-strip" data-testid={`decision-badges-${auction.property_id}`} style={{ paddingTop: 10, paddingBottom: 0 }}>
          {decisionBadges.map((b) => (
            <span key={b.label} className="fb-cell">
              <span className="fb-label">{b.label}</span>
              <Badge tone={b.tone}>{b.value}</Badge>
            </span>
          ))}
        </div>
      ) : null}

      <div className="card-pad" style={{ paddingTop: 10 }}>
        {iWon ? (
          <div className="grid-2">
            <div>
              <Kv k="Your winning bid" v={money(auction.winning_bid)} strong />
              <Kv k="Your LTV" v={pct(auction.winning_ltv, 0)} />
              <Kv k="Seller reserve" v={money(auction.reserve_price)} />
            </div>
            <div>
              <Kv k="Realized Yr-1 value" v={money(auction.realized_value)} />
              <Kv k="Realized NOI growth" v={signedPercent(auction.noi_growth_actual)} />
              <Kv k="Year-end cap rate" v={pct(auction.cap_rate_actual, 2)} />
            </div>
          </div>
        ) : isPractice && wouldHaveWon ? (
          <div data-testid="would-have-won">
            <div className="spread mb-12">
              <span className="panel-label">Your bid would have won</span>
              {override?.price || override?.ltv ? <Badge tone="warn">policy override</Badge> : null}
            </div>
            <div className="grid-2">
              <div>
                <Kv k="Your bid" v={money(myBid)} strong />
                <Kv k="Seller reserve" v={money(auction.reserve_price)} />
              </div>
              <div>
                <Kv k="Realized Yr-1 value" v={money(auction.realized_value)} />
                <Kv k="Realized NOI growth" v={signedPercent(auction.noi_growth_actual)} />
              </div>
            </div>
            <div className="note-box mt-12">
              Practice does not add this property to your portfolio or change NAV. In a scored
              round this bid would have been awarded.
            </div>
          </div>
        ) : won && !iWon ? (
          <div>
            <Kv k="Winning fund" v={<span className="v small">{auction.winning_team_id}</span>} />
            <Kv k="Winning bid" v={money(auction.winning_bid)} />
            <Kv k="Seller reserve" v={money(auction.reserve_price)} />
            <Kv k="Realized Yr-1 value" v={money(auction.realized_value)} />
            <Kv k="Realized NOI growth" v={signedPercent(auction.noi_growth_actual)} />
            {myBid !== null ? (
              <Kv k="Your bid" v={`${money(myBid)} — ${belowReserve ? "below the reserve" : "not the highest valid bid"}`} />
            ) : (
              <Kv k="Your decision" v={<span className="v small">You passed on this deal.</span>} />
            )}
          </div>
        ) : !won ? (
          <div>
            <Kv k="Seller reserve" v={money(auction.reserve_price)} />
            <Kv k="Realized Yr-1 value" v={money(auction.realized_value)} />
            <Kv k="Realized NOI growth" v={signedPercent(auction.noi_growth_actual)} />
            {myBid !== null && belowReserve ? (
              <div className="mt-8">
                <Kv
                  k="Why your bid did not win"
                  v={<span className="v small">{money(myBid)} was below the {money(auction.reserve_price)} reserve.</span>}
                />
              </div>
            ) : myBid !== null && rejectedReason ? (
              <div className="mt-8">
                <Kv k="Bid not accepted" v={<span className="v small">{rejectedReason}</span>} />
              </div>
            ) : myItem?.action === "PASS" ? (
              <Kv k="Your decision" v={<span className="v small">You passed on this deal.</span>} />
            ) : null}
          </div>
        ) : null}

        {forecast ? (
          <div className="mt-12">
            <span className="panel-label">Your pre-class forecast, against what happened</span>
            <div className="grid-2 mt-8">
              <div>
                <Kv k="Predicted value" v={money(forecast.forecast.predictedFairValue)} />
                <Kv
                  k="Valuation error"
                  v={
                    auction.realized_value
                      ? signedPercent(forecast.forecast.predictedFairValue / auction.realized_value - 1)
                      : "—"
                  }
                />
              </div>
              <div>
                <Kv k="Predicted NOI growth" v={signedPercent(forecast.forecast.predictedNoiGrowth)} />
                <Kv k="Actual NOI growth" v={signedPercent(auction.noi_growth_actual)} />
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

// ── feedback: forecast / policy / outcome ─────────────────────────────────

function FeedbackPanel({
  state,
  forecasts,
  results,
  myItems,
  isPractice,
}: {
  state: StateView;
  forecasts: Map<string, ForecastRow>;
  results: RoundResults;
  myItems: Map<string, DecisionRecord>;
  isPractice: boolean;
}) {
  const rows: { label: string; value: "Accurate" | "Missed" | "Followed" | "Overridden" | "Favorable" | "Unfavorable" | "—"; tone: "ok" | "warn" | "bad" | "neutral" }[] = [];

  // FORECAST: how close was the team's predicted value, on the properties offered.
  const errors: number[] = [];
  for (const auction of results.auctions) {
    const f = forecasts.get(auction.property_id);
    if (f && auction.realized_value && auction.realized_value > 0) {
      errors.push(Math.abs(f.forecast.predictedFairValue / auction.realized_value - 1));
    }
  }
  const meanError = errors.length ? errors.reduce((a, b) => a + b, 0) / errors.length : null;
  rows.push({
    label: "Forecast",
    value: meanError === null ? "—" : meanError <= 0.1 ? "Accurate" : "Missed",
    tone: meanError === null ? "neutral" : meanError <= 0.1 ? "ok" : "warn",
  });

  // POLICY: decision overrides = every submitted choice that deviated from the locked
  // policy, won or lost. Deliberately NOT the engine's override_count, which only
  // counts overrides on properties the fund actually acquired.
  let decisionOverrides = 0;
  let investedOverrides = 0;
  let followed = 0;
  let decided = 0;
  for (const auction of results.auctions) {
    const item = myItems.get(auction.property_id);
    const f = forecasts.get(auction.property_id);
    if (!item || !f) continue;
    decided += 1;
    const priceOver = item.action === "BID" && item.bid !== null && item.bid > f.policy.maxBid + 1e-9;
    const ltvOver = item.action === "BID" && item.ltv !== null && item.ltv > f.policy.targetLtv + 1e-9;
    if (priceOver || ltvOver) {
      decisionOverrides += 1;
      if (auction.sold && auction.winning_team_id === state.you.fundId) investedOverrides += 1;
    } else if (item.action === "BID") {
      followed += 1;
    }
  }
  rows.push({
    label: "Policy",
    value: decided === 0 ? "—" : decisionOverrides > 0 ? "Overridden" : "Followed",
    tone: decided === 0 ? "neutral" : decisionOverrides > 0 ? "warn" : "ok",
  });

  // OUTCOME: realized-vs-predicted on what the fund would have or did acquire.
  const outcomeErrs: number[] = [];
  for (const auction of results.auctions) {
    const f = forecasts.get(auction.property_id);
    const item = myItems.get(auction.property_id);
    if (!f || !item || item.action !== "BID" || !auction.realized_value) continue;
    outcomeErrs.push(Math.abs(f.forecast.predictedFairValue / auction.realized_value - 1));
  }
  const outcomeMean = outcomeErrs.length ? outcomeErrs.reduce((a, b) => a + b, 0) / outcomeErrs.length : null;
  rows.push({
    label: "Outcome",
    value: outcomeMean === null ? "—" : outcomeMean <= 0.1 ? "Favorable" : "Unfavorable",
    tone: outcomeMean === null ? "neutral" : outcomeMean <= 0.1 ? "ok" : "bad",
  });

  const observations = observationsFor({
    isPractice,
    decisionOverrides,
    investedOverrides,
    meanError,
    outcomeMean,
    auctions: results.auctions,
    myItems,
    forecasts,
  });

  return (
    <Panel label="Feedback">
      <div>
        {rows.map((r) => (
          <div className="fb-row" key={r.label} data-testid={`feedback-${r.label.toLowerCase()}`}>
            <span className="fb-label">{r.label}</span>
            <span>
              <Badge tone={r.tone}>{r.value}</Badge>
            </span>
          </div>
        ))}
      </div>
      {decisionOverrides > 0 ? (
        <p className="help mt-8">
          {decisionOverrides} decision{decisionOverrides === 1 ? "" : "s"} deviated from your
          locked policy{investedOverrides > 0 ? `; ${investedOverrides} became acquired ${investedOverrides === 1 ? "property" : "properties"}` : " (none were acquired)"}. Overriding is
          recorded, not penalized.
        </p>
      ) : null}
      {observations.length > 0 ? (
        <>
          <hr className="divider" />
          <span className="panel-label">Observations</span>
          <ul className="observations mt-8" data-testid="observations">
            {observations.slice(0, 3).map((o, i) => (
              <li key={i}>{o}</li>
            ))}
          </ul>
        </>
      ) : null}
    </Panel>
  );
}

/**
 * Deterministic observations, from data the round already carries. No model, no
 * narration beyond the template, capped at three.
 */
function observationsFor(args: {
  isPractice: boolean;
  decisionOverrides: number;
  investedOverrides: number;
  meanError: number | null;
  outcomeMean: number | null;
  auctions: Auction[];
  myItems: Map<string, DecisionRecord>;
  forecasts: Map<string, ForecastRow>;
}): string[] {
  const out: string[] = [];
  const { auctions, myItems, forecasts } = args;

  const overrides = [...myItems.entries()].filter(([pid, item]) => {
    const f = forecasts.get(pid);
    return f && item.action === "BID" && item.bid !== null && item.bid > f.policy.maxBid + 1e-9;
  });
  if (overrides.length > 0) {
    out.push(
      `You exceeded your own price ceiling on ${overrides.length} of ${myItems.size} deals.`,
    );
  }

  const upsideRows = [...forecasts.entries()]
    .map(([pid, f]) => ({ pid, type: typeOf(pid, args.auctions), upside: f.forecast.predictedFairValue }))
    .sort((a, b) => b.upside - a.upside);
  if (upsideRows.length > 0 && upsideRows[0]!.type) {
    out.push(`Your largest predicted opportunity was ${upsideRows[0]!.type}.`);
  }

  const disciplinedButUnfavorable = auctions.some((a) => {
    const item = myItems.get(a.property_id);
    const f = forecasts.get(a.property_id);
    if (!item || item.action !== "BID" || !f || !a.realized_value) return false;
    const withinPolicy = item.bid !== null && item.bid <= f.policy.maxBid + 1e-9;
    const missed = Math.abs(f.forecast.predictedFairValue / a.realized_value - 1) > 0.1;
    return withinPolicy && missed;
  });
  if (disciplinedButUnfavorable) {
    out.push("A defensible decision received an unfavorable outcome.");
  }

  if (out.length === 0 && args.meanError !== null) {
    out.push(
      args.meanError <= 0.1
        ? "Your valuations tracked the realized year closely."
        : "Your valuations ran ahead of the realized year — check your growth assumptions.",
    );
  }
  return out;
}

function typeOf(propertyId: string, auctions: Auction[]): string | null {
  return auctions.find((a) => a.property_id === propertyId)?.property_id ? propertyTypeOf(propertyId) : null;
}

/** Property ids embed their type: OC-INDU-01 → Industrial. */
function propertyTypeOf(propertyId: string): string | null {
  if (propertyId.includes("INDU")) return "Industrial";
  if (propertyId.includes("OFFI")) return "Office";
  if (propertyId.includes("MULT")) return "Multifamily";
  if (propertyId.includes("RETA")) return "Retail";
  return null;
}

// ── per-property decision badges: forecast / policy / decision / outcome ──

interface DecisionBadge {
  label: "FORECAST" | "POLICY" | "DECISION" | "OUTCOME";
  value: string;
  tone: "ok" | "warn" | "bad" | "neutral";
}

/**
 * The compact per-property verdict strip. Neutral by construction:
 * an override is recorded, never scored, and an outcome is never presented as
 * proof that the decision was right or wrong.
 */
function decisionBadgesFor(args: {
  auction: Auction;
  forecast: ForecastRow | undefined;
  myItem: DecisionRecord | null;
  myFundId: string | null;
  isPractice: boolean;
}): DecisionBadge[] {
  const { auction, forecast, myItem, myFundId } = args;
  const out: DecisionBadge[] = [];

  // FORECAST — valuation accuracy on this property.
  if (forecast && auction.realized_value && auction.realized_value > 0) {
    const err = Math.abs(forecast.forecast.predictedFairValue / auction.realized_value - 1);
    out.push({
      label: "FORECAST",
      value: err <= 0.1 ? "Accurate" : "Missed",
      tone: err <= 0.1 ? "ok" : "warn",
    });
  }

  // POLICY — deviation from the frozen policy, price or LTV.
  if (myItem && forecast) {
    const priceOver = myItem.action === "BID" && myItem.bid !== null && myItem.bid > forecast.policy.maxBid + 1e-9;
    const ltvOver = myItem.action === "BID" && myItem.ltv !== null && myItem.ltv > forecast.policy.targetLtv + 1e-9;
    out.push({
      label: "POLICY",
      value: priceOver || ltvOver ? "Overridden" : "Followed",
      tone: priceOver || ltvOver ? "warn" : "ok",
    });
  }

  // DECISION — what this fund did.
  if (myItem) {
    out.push({
      label: "DECISION",
      value: myItem.action === "BID" ? "Bid" : "Pass",
      tone: "neutral",
    });
  }

  // OUTCOME — what happened to this fund's decision. A lost bid is a lost bid;
  // nothing about it is called good or bad.
  if (myItem) {
    const won = auction.sold && auction.winning_team_id !== null;
    const iWon = won && myFundId !== null && auction.winning_team_id === myFundId;
    const bid = myItem.action === "BID" && myItem.bid !== null;
    const wouldHaveWon =
      !won && bid && auction.reserve_price !== null && myItem.bid !== null && myItem.bid >= auction.reserve_price;
    if (iWon) {
      out.push({ label: "OUTCOME", value: "Won", tone: "ok" });
    } else if (myItem.action === "BID" && wouldHaveWon && args.isPractice) {
      out.push({ label: "OUTCOME", value: "Would win (practice)", tone: "ok" });
    } else if (myItem.action === "BID") {
      out.push({ label: "OUTCOME", value: "Lost", tone: "neutral" });
    } else {
      out.push({ label: "OUTCOME", value: won ? "Skipped" : "No sale", tone: "neutral" });
    }
  }

  return out;
}
