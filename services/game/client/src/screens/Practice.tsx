/**
 * The deal board — the central teaching UI.
 *
 * Board → drawer → decision → review → locked. The drawer never navigates away from
 * the board. Every number shown is either the engine's (deal data, forecasts,
 * results) or presentation arithmetic on a bid the player has typed (capital impact),
 * from the engine's own published rates.
 *
 * The underwriting drawer is a two-column surface: asset facts scroll on the left,
 * while YOUR ANALYSIS (pre-class forecast → investment policy → your decision →
 * capital impact → policy override) stays sticky on the right, so the central
 * teaching chain — market facts → model forecast → policy → decision — is visible
 * at all times.
 */

import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { api, ApiError, type DecisionItem, type Deal, type ForecastRow, type RoundView } from "../api";
import { Badge, Drawer, ErrorBox, Kv, Modal, Section } from "../components";
import {
  capitalImpact,
  debtYieldAt,
  money,
  moneySigned,
  num,
  pct,
  qualityLabel,
  signedPercent,
  signedPoints,
  sqft,
} from "../format";
import { SessionTopbar } from "../chrome";
import { imageForProperty } from "../propertyImages";
import { useSession } from "../session";

type Draft = { action: "PASS" | "BID"; bid: string; ltv: string };

/** The scored-round header: fund NAV, cash, assets, and portfolio LTV — all engine data. */
function RoundHeader({ fund }: { fund: RoundView["public"]["funds"][number] | undefined }) {
  const { state } = useSession();
  if (!fund) return null;
  const session = state?.session;
  const deadline = session?.roundDeadlineAt ?? null;
  const paused = session?.timerPausedAt !== null;
  const debt = fund.debt;
  const portfolioLtv = fund.assets > 0 ? debt / (debt + Math.max(0, fund.nav - fund.cash)) : null;
  return (
    <div className="round-header" data-testid="round-header">
      <div className="rh-brand">PACIFIC CRE PARTNERS</div>
      <div className="rh-title">{session?.roundLabel}</div>
      <div className="rh-metrics">
        <div className="rh-metric">
          <span className="rh-label">NAV</span>
          <span className="rh-value" data-testid="rh-nav">{money(fund.nav)}</span>
        </div>
        <div className="rh-metric">
          <span className="rh-label">Cash</span>
          <span className="rh-value" data-testid="rh-cash">{money(fund.cash)}</span>
        </div>
        <div className="rh-metric">
          <span className="rh-label">Assets</span>
          <span className="rh-value" data-testid="rh-assets">{fund.assets}</span>
        </div>
        <div className="rh-metric">
          <span className="rh-label">Portfolio LTV</span>
          <span className="rh-value" data-testid="rh-ltv">{portfolioLtv === null ? "—" : pct(portfolioLtv, 0)}</span>
        </div>
        <div className="rh-metric">
          <span className="rh-label">Time</span>
          <span className="rh-value" data-testid="rh-time">
            {deadline !== null && !paused ? <Countdown deadline={deadline} /> : paused ? "paused" : "—"}
          </span>
        </div>
      </div>
    </div>
  );
}

/** One-second countdown against the server-persisted deadline. */
function Countdown({ deadline }: { deadline: number }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const remaining = Math.max(0, deadline - now);
  const m = Math.floor(remaining / 60000);
  const s = Math.floor((remaining % 60000) / 1000);
  return (
    <span>
      {String(m).padStart(2, "0")}:{String(s).padStart(2, "0")}
    </span>
  );
}

/** The portfolio drawer: the engine's team view for the student's own fund. */
function PortfolioDrawer({
  sessionId,
  fundId,
  onClose,
}: {
  sessionId: string;
  fundId: string;
  onClose: () => void;
}) {
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .portfolio(sessionId, fundId)
      .then((res) => {
        if (alive) setData(res.portfolio);
      })
      .catch((err) => {
        if (alive) setError(err instanceof Error ? err.message : "Portfolio unavailable.");
      });
    return () => {
      alive = false;
    };
  }, [sessionId, fundId]);

  const portfolio = (data ?? {}) as Record<string, unknown>;
  const holdings = Array.isArray(portfolio.holdings) ? (portfolio.holdings as Record<string, unknown>[]) : [];
  const channels = Array.isArray(portfolio.channels) ? (portfolio.channels as Record<string, unknown>[]) : [];
  const overrides = Array.isArray(portfolio.overrides)
    ? (portfolio.overrides as Record<string, unknown>[])
    : [];
  const summary = (portfolio.summary ?? {}) as Record<string, unknown>;

  return (
    <Drawer onClose={onClose} title="Portfolio">
      {error ? <ErrorBox>{error}</ErrorBox> : null}

      <div className="stat-strip mb-16">
        <div className="stat">
          <div className="stat-label">NAV</div>
          <div className="stat-value">{money(asNumber(summary.nav))}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Cash</div>
          <div className="stat-value">{money(asNumber(summary.cash))}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Gross value</div>
          <div className="stat-value">{money(asNumber(summary.gross_asset_value ?? summary.assets))}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Debt</div>
          <div className="stat-value">{money(asNumber(summary.debt))}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Cumulative return</div>
          <div className="stat-value">{pct(asNumber(summary.cumulative_return), 1)}</div>
        </div>
      </div>

      {holdings.length > 0 ? (
        <table className="table" data-testid="portfolio-holdings">
          <thead>
            <tr>
              <th>Property</th>
              <th>Type</th>
              <th className="num">Acquisition</th>
              <th className="num">Current value</th>
              <th className="num">Debt</th>
              <th className="num">LTV</th>
              <th className="num">NOI</th>
              <th className="num">Value change</th>
            </tr>
          </thead>
          <tbody>
            {holdings.map((h, i) => (
              <tr key={i}>
                <td>{String(h.property_id ?? h.property_name ?? "")}</td>
                <td>{String(h.property_type ?? "—")}</td>
                <td className="num mono">{money(asNumber(h.acquisition_price))}</td>
                <td className="num mono">{money(asNumber(h.current_value ?? h.marked_value))}</td>
                <td className="num mono">{money(asNumber(h.debt))}</td>
                <td className="num mono">{pct(asNumber(h.ltv), 0)}</td>
                <td className="num mono">{money(asNumber(h.current_noi ?? h.noi))}</td>
                <td className="num mono">{moneySigned(asNumber(h.unrealized_value_change), 2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="help">No holdings yet — acquisitions appear here after each scored round.</p>
      )}

      {channels.length > 0 ? (
        <Section label="Cash-flow channels">
          <table className="table">
            <thead>
              <tr>
                <th>Round</th>
                <th className="num">NOI</th>
                <th className="num">Interest</th>
                <th className="num">Acquisition costs</th>
                <th className="num">Reserves</th>
                <th className="num">Value</th>
              </tr>
            </thead>
            <tbody>
              {channels.map((c, i) => (
                <tr key={i}>
                  <td>{String(c.round ?? i + 1)}</td>
                  <td className="num mono">{moneySigned(asNumber(c.noi_income) ?? 0, 2)}</td>
                  <td className="num mono">{moneySigned(-Math.abs(asNumber(c.interest_paid) ?? 0), 2)}</td>
                  <td className="num mono">{moneySigned(-Math.abs(asNumber(c.acquisition_costs) ?? 0), 2)}</td>
                  <td className="num mono">{moneySigned(-Math.abs(asNumber(c.reserves) ?? 0), 2)}</td>
                  <td className="num mono">{moneySigned(asNumber(c.value_channel) ?? 0, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      ) : null}

      {overrides.length > 0 ? (
        <Section label="Decision overrides">
          <p className="help">
            Decisions that deviated from your locked policy — recorded, never penalized.
            An override is not a verdict.
          </p>
          <table className="table">
            <thead>
              <tr>
                <th>Property</th>
                <th>Price deviation</th>
                <th>LTV deviation</th>
                <th>Acquired</th>
              </tr>
            </thead>
            <tbody>
              {overrides.map((o, i) => (
                <tr key={i}>
                  <td>{String(o.property_id ?? "")}</td>
                  <td className="num mono">{moneySigned(asNumber(o.price_delta) ?? 0, 2)}</td>
                  <td className="num mono">{signedPoints(asNumber(o.ltv_delta) ?? 0, 1)}</td>
                  <td>{o.invested ? "yes" : "no"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      ) : null}

      <p className="help mt-12">
        Values are the engine's marks at the most recent resolution, not live pricing.
      </p>
    </Drawer>
  );
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function draftsFromRound(round: RoundView | null): Record<string, Draft> {
  const out: Record<string, Draft> = {};
  for (const deal of round?.public.deals ?? []) {
    const forecast = round?.myForecast.find((f) => f.propertyId === deal.property_id);
    const submitted = round?.myDecision?.items.find((i) => i.propertyId === deal.property_id);
    out[deal.property_id] = submitted
      ? {
          action: submitted.action,
          bid: submitted.bid === null ? "" : String(submitted.bid),
          ltv: submitted.ltv === null ? "" : String(Math.round(submitted.ltv * 1000) / 10),
        }
      : {
          action: "PASS",
          bid: forecast ? String(forecast.policy.maxBid) : "",
          ltv: forecast ? String(Math.round(forecast.policy.targetLtv * 100)) : "",
        };
  }
  return out;
}

interface ReviewItem {
  deal: Deal;
  item: DecisionItem;
  total: number;
  reviewed: boolean;
}

function buildItems(deals: Deal[], drafts: Record<string, Draft>): ReviewItem[] {
  return deals.map((deal) => {
    const d = drafts[deal.property_id] ?? { action: "PASS" as const, bid: "", ltv: "" };
    const bid = d.action === "BID" && d.bid.trim() !== "" ? Number(d.bid) : null;
    const ltvRaw = d.action === "BID" && d.ltv.trim() !== "" ? Number(d.ltv) : null;
    const ltv = ltvRaw !== null && Number.isFinite(ltvRaw) ? ltvRaw / 100 : null;
    const valid =
      d.action === "PASS" ||
      (bid !== null && Number.isFinite(bid) && bid > 0 && ltv !== null && ltv > 0 && ltv <= 1);
    const total =
      bid !== null && ltv !== null
        ? capitalImpact(bid, ltv, deal.acquisition_cost_rate ?? 0.02).total
        : 0;
    return {
      deal,
      item: {
        propertyId: deal.property_id,
        action: d.action,
        bid: d.action === "BID" ? bid : null,
        ltv: d.action === "BID" ? ltv : null,
      },
      total,
      reviewed: valid,
    };
  });
}

export function Practice() {
  const { state, refresh } = useSession();
  const navigate = useNavigate();
  const [drawerFor, setDrawerFor] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});

  const round = state?.round ?? null;
  const roundKey = round ? `${round.round}:${round.openedAt}` : "";
  const seededKey = `${roundKey}`;

  // Seed (and re-seed) local drafts whenever the round itself changes. A submitted
  // decision wins over the policy defaults so a refresh shows what was locked in.
  useEffect(() => {
    setDrafts(draftsFromRound(round));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seededKey]);

  if (!state) return null;
  const { session, you } = state;

  if (session.phase === "lobby") return <Navigate to="/lobby" replace />;
  if (session.phase === "model_checkin") return <Navigate to="/model" replace />;
  if (
    session.phase === "practice_results" ||
    session.phase === "round_results" ||
    session.phase === "finale"
  ) {
    return <Navigate to="/game/results" replace />;
  }

  const deals = round?.public.deals ?? [];
  const forecasts = new Map(round?.myForecast.map((f) => [f.propertyId, f]) ?? []);
  const economics = round?.public.economics;
  const acqRate = economics?.acquisition_cost_rate ?? 0.02;

  const myFundSummary = round?.public.funds.find((f) => f.team_id === you.fundId);
  const cash = myFundSummary?.cash ?? null;

  const items = buildItems(deals, drafts);
  const reviewedCount = items.filter((i) => i.reviewed).length;
  const cashIfAllWin = items.reduce((acc, i) => acc + (i.item.action === "BID" ? i.total : 0), 0);
  const cashRemaining = cash === null ? null : cash - cashIfAllWin;

  const drawerDeal = deals.find((d) => d.property_id === drawerFor) ?? null;
  const submitted = round?.myDecision !== null && round?.myDecision !== undefined;
  const singleDeal = deals.length === 1;
  const [portfolioOpen, setPortfolioOpen] = useState(false);
  const isScored = !round?.isPractice;

  async function demoAdvance() {
    setBusy(true);
    setError(null);
    try {
      await api.demoAdvance(session.id);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Advance failed.");
      setBusy(false);
    }
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api.submitDecision(
        session.id,
        items.map((i) => i.item),
      );
      await refresh();
      navigate("/game/waiting");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Submit failed.");
      setBusy(false);
    }
  }

  return (
    <div className="shell" style={{ paddingBottom: 84 }}>
      <SessionTopbar state={state} />
      <main className="shell-main wide">
        <div className="page-head spread">
          <div>
            <span className="panel-label">{round?.isPractice ? "Practice deal board" : "Deal board"}</span>
            <h2>{round?.roundLabel ?? session.roundLabel}</h2>
            <p className="sub">
              {round?.isPractice
                ? "Practice uses the real auction and market mechanics but does not book acquisitions or change NAV."
                : "Sealed-bid auctions. The highest valid bid above the seller's reserve wins; the winner pays its own price."}
            </p>
          </div>
          <div className="row" style={{ gap: 8 }}>
            {session.demo ? (
              <button className="btn btn-primary" onClick={demoAdvance} disabled={busy} data-testid="demo-advance">
                {busy ? "Advancing…" : round?.isOpenForSubmissions ? "Submit & close" : "Continue"}
              </button>
            ) : null}
            <button className="btn btn-secondary" onClick={() => setPortfolioOpen(true)} data-testid="open-portfolio">
              Portfolio
            </button>
            {submitted ? (
              <Badge tone="ok">decisions locked</Badge>
            ) : (
              <Badge tone={round?.isOpenForSubmissions ? "ok" : "warn"}>
                {round?.isOpenForSubmissions ? "open for decisions" : "market closed"}
              </Badge>
            )}
          </div>
        </div>

        {isScored ? <RoundHeader fund={myFundSummary} /> : null}

        {error ? <div className="mb-16"><ErrorBox>{error}</ErrorBox></div> : null}

        <div className="stat-strip mb-16" data-testid="capital-strip">
          <div className="stat">
            <div className="stat-label">Cash available</div>
            <div className="stat-value" data-testid="cash-available">{money(cash)}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Cash if all current bids win</div>
            <div className="stat-value dim" data-testid="cash-if-win">{money(cashIfAllWin)}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Remaining</div>
            <div className="stat-value" data-testid="cash-remaining">{money(cashRemaining)}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Deals reviewed</div>
            <div className="stat-value dim" data-testid="reviewed-count">{reviewedCount} / {deals.length}</div>
          </div>
        </div>

        <div
          className="board"
          data-testid="deal-board"
          style={singleDeal ? { gridTemplateColumns: "minmax(520px, 720px)", justifyContent: "center" } : undefined}
        >
          {deals.map((deal) => (
            <DealCard
              key={deal.property_id}
              deal={deal}
              draft={drafts[deal.property_id] ?? { action: "PASS", bid: "", ltv: "" }}
              onDraft={(d) => setDrafts((prev) => ({ ...prev, [deal.property_id]: d }))}
              onOpen={() => setDrawerFor(deal.property_id)}
              forecast={forecasts.get(deal.property_id)}
              acqRate={acqRate}
              disabled={submitted || !round?.isOpenForSubmissions}
              enlarged={singleDeal}
            />
          ))}
        </div>
      </main>

      <div className="action-bar">
        <div className="action-bar-inner">
          <div className="action-meta">
            <span className="a-title">{reviewedCount} / {deals.length} deals reviewed</span>
            <span className="a-sub">Cash if all bids win: {money(cashIfAllWin)}</span>
          </div>
          <div className="action-bar-spacer" />
          {submitted ? (
            <button className="btn btn-ghost btn-lg" onClick={() => navigate("/game/waiting")} data-testid="go-waiting">
              View submission status
            </button>
          ) : (
            <button
              className="btn btn-primary btn-lg"
              onClick={() => setReviewing(true)}
              disabled={reviewedCount < deals.length || !round?.isOpenForSubmissions}
              data-testid="review-submit"
            >
              Review &amp; submit
            </button>
          )}
        </div>
      </div>

      {drawerDeal ? (
        <UnderwritingDrawer
          deal={drawerDeal}
          forecast={forecasts.get(drawerDeal.property_id)}
          draft={drafts[drawerDeal.property_id] ?? { action: "PASS", bid: "", ltv: "" }}
          onDraft={(d) => setDrafts((prev) => ({ ...prev, [drawerDeal.property_id]: d }))}
          acqRate={acqRate}
          disabled={submitted || !round?.isOpenForSubmissions}
          onClose={() => setDrawerFor(null)}
        />
      ) : null}

      {reviewing && !submitted ? (
        <ReviewModal
          deals={deals}
          items={items}
          onClose={() => setReviewing(false)}
          onSubmit={submit}
          busy={busy}
        />
      ) : null}

      {portfolioOpen && you.fundId ? (
        <PortfolioDrawer
          sessionId={session.id}
          fundId={you.fundId}
          onClose={() => setPortfolioOpen(false)}
        />
      ) : null}
    </div>
  );
}

function DealCard({
  deal,
  draft,
  onDraft,
  onOpen,
  forecast,
  acqRate,
  disabled,
  enlarged,
}: {
  deal: Deal;
  draft: Draft;
  onDraft: (d: Draft) => void;
  onOpen: () => void;
  forecast: ForecastRow | undefined;
  acqRate: number;
  disabled: boolean;
  enlarged: boolean;
}) {
  const image = imageForProperty(deal.property_type, deal.property_id);
  const ask = deal.asking_price;
  const upside = ask && forecast ? forecast.forecast.predictedFairValue / ask - 1 : null;
  const bidding = draft.action === "BID";
  const bidValue = bidding && draft.bid.trim() !== "" ? Number(draft.bid) : null;
  const ltvValue = bidding && draft.ltv.trim() !== "" ? Number(draft.ltv) / 100 : null;
  const decided = bidValue !== null && Number.isFinite(bidValue);
  const impact =
    bidValue !== null && ltvValue !== null ? capitalImpact(bidValue, ltvValue, acqRate) : null;

  return (
    <article
      className={`deal-card ${decided ? "decided-bid" : bidding ? "decided-pass" : ""}${enlarged ? " deal-card-single" : ""}`}
      data-testid={`deal-card-${deal.property_id}`}
    >
      <div className="deal-img">
        <img src={image.url} alt="" aria-hidden="true" title={`${image.credit} — illustrative, not this address`} />
        <span className="type-chip">{deal.property_type}</span>
        <span className="illustrative-chip">illustrative</span>
      </div>
      <div className="deal-body">
        <div className="deal-head">
          <div>
            <div className="deal-name" data-testid={`deal-name-${deal.property_id}`}>{deal.property_name}</div>
            <div className="deal-sub">{deal.submarket} · {deal.property_type}</div>
          </div>
          <span className="status-chip">
            {decided ? (
              <span className="badge badge-navy">BID {money(bidValue)}</span>
            ) : bidding ? (
              <span className="badge badge-neutral">BID — enter price</span>
            ) : (
              <span className="badge badge-neutral">PASS</span>
            )}
          </span>
        </div>

        <div className="deal-metrics">
          <div className="deal-metric">
            <div className="m-label">Asking price</div>
            <div className="m-value">{money(ask)}</div>
          </div>
          <div className="deal-metric">
            <div className="m-label">Going-in cap</div>
            <div className="m-value">{pct(deal.going_in_cap, 2)}</div>
          </div>
          <div className="deal-metric">
            <div className="m-label">Occupancy</div>
            <div className="m-value">{pct(deal.occupancy, 0)}</div>
          </div>
          <div className="deal-metric">
            <div className="m-label">Model upside</div>
            <div className="m-value">{upside === null ? "—" : signedPercent(upside)}</div>
          </div>
          <div className="deal-metric">
            <div className="m-label">Downside prob.</div>
            <div className="m-value">{pct(forecast?.forecast.probabilityOfDownside ?? null, 0)}</div>
          </div>
          <div className="deal-metric">
            <div className="m-label">Cash required</div>
            <div className="m-value">{impact ? money(impact.total) : "—"}</div>
          </div>
        </div>

        <div className="deal-controls">
          <div className="seg" role="group" aria-label="Decision for this deal">
            <button
              type="button"
              className={draft.action === "PASS" ? "active" : ""}
              onClick={() => onDraft({ ...draft, action: "PASS" })}
              disabled={disabled}
              data-testid={`pass-${deal.property_id}`}
            >
              Pass
            </button>
            <button
              type="button"
              className={bidding ? "active" : ""}
              onClick={() => onDraft({ ...draft, action: "BID" })}
              disabled={disabled}
              data-testid={`bid-${deal.property_id}`}
            >
              Bid
            </button>
          </div>
          {bidding ? (
            <>
              <div className="money-input">
                <span className="prefix">$</span>
                <input
                  className="input"
                  inputMode="decimal"
                  value={draft.bid}
                  onChange={(e) => onDraft({ ...draft, bid: e.target.value })}
                  placeholder={forecast ? String(forecast.policy.maxBid) : "0.0"}
                  aria-label={`Bid price in millions for ${deal.property_name}`}
                  disabled={disabled}
                  data-testid={`bid-price-${deal.property_id}`}
                />
              </div>
              <div className="pct-input">
                <input
                  className="input"
                  inputMode="numeric"
                  value={draft.ltv}
                  onChange={(e) => onDraft({ ...draft, ltv: e.target.value })}
                  placeholder={forecast ? String(Math.round(forecast.policy.targetLtv * 100)) : "60"}
                  aria-label={`Loan-to-value percent for ${deal.property_name}`}
                  disabled={disabled}
                  data-testid={`bid-ltv-${deal.property_id}`}
                />
                <span className="suffix">%</span>
              </div>
            </>
          ) : null}
          {impact && ltvValue !== null ? (
            <div className="capital-inline" aria-label="Capital impact of this bid">
              <span className="ci-label">Total cash required</span>
              <span className="ci-value" data-testid={`total-cash-${deal.property_id}`}>
                {money(impact.total)}
              </span>
            </div>
          ) : null}
          <button className="btn btn-secondary" onClick={onOpen} data-testid={`underwrite-${deal.property_id}`}>
            Underwrite
          </button>
        </div>
      </div>
    </article>
  );
}

/**
 * The two-column underwriting surface.
 *
 * Left: asset facts (Property / Operations / Capital markets / Ownership costs).
 * Right (sticky): the analysis chain — pre-class forecast, investment policy,
 * the live decision, capital impact, and any policy override. The right column is
 * what the game is about; it must never be below the fold.
 */
function UnderwritingDrawer({
  deal,
  forecast,
  draft,
  onDraft,
  acqRate,
  disabled,
  onClose,
}: {
  deal: Deal;
  forecast: ForecastRow | undefined;
  draft: Draft;
  onDraft: (d: Draft) => void;
  acqRate: number;
  disabled: boolean;
  onClose: () => void;
}) {
  const bidding = draft.action === "BID";
  const bidValue = bidding && draft.bid.trim() !== "" ? Number(draft.bid) : null;
  const ltvValue = bidding && draft.ltv.trim() !== "" ? Number(draft.ltv) / 100 : null;
  const impact =
    bidValue !== null && ltvValue !== null && Number.isFinite(ltvValue)
      ? capitalImpact(bidValue, ltvValue, acqRate)
      : null;

  const override = forecast && bidValue !== null
    ? {
        priceOver: bidValue > forecast.policy.maxBid + 1e-9,
        ltvOver: ltvValue !== null && ltvValue > forecast.policy.targetLtv + 1e-9,
        priceDelta: bidValue - forecast.policy.maxBid,
        ltvDelta: ltvValue !== null ? ltvValue - forecast.policy.targetLtv : 0,
      }
    : null;

  const dynDebtYield = debtYieldAt(deal.current_noi, bidValue, ltvValue);

  return (
    <Drawer
      title={deal.property_name}
      subtitle={`${deal.property_type} · ${deal.submarket}${deal.units ? ` · ${num(deal.units)} units` : ""}`}
      onClose={onClose}
    >
      <div className="drawer-2col">
        <div className="drawer-facts">
          <Section label="Property">
            <Kv k="Building" v={sqft(deal.building_sf)} />
            {deal.units ? <Kv k="Units" v={num(deal.units)} /> : null}
            <Kv k="Year built" v={deal.year_built ?? "—"} />
            <Kv k="Occupancy" v={pct(deal.occupancy, 1)} />
            <Kv k="WALT" v={deal.walt === null ? "—" : `${deal.walt.toFixed(1)} yrs`} />
            <Kv k="Tenant concentration" v={pct(deal.tenant_concentration, 0)} />
            <Kv k="Lease rollover" v={deal.lease_expiry_profile ?? "—"} />
            <Kv
              k="Property quality"
              v={<span className="v small">{qualityLabel(deal.property_quality)}</span>}
              title="Letter grade derived from the teaching dataset's synthetic condition score. Shown as a grade only; the raw score is an engine-internal teaching feature."
            />
          </Section>

          <Section label="Operations">
            <Kv k="Current NOI" v={money(deal.current_noi, 2)} />
            <Kv k="Market rent" v={deal.market_rent === null ? "—" : `$${deal.market_rent.toFixed(2)}/SF/mo`} />
            <Kv k="In-place rent" v={deal.in_place_rent === null ? "—" : `$${deal.in_place_rent.toFixed(2)}/SF/mo`} />
            <Kv k="Opex ratio" v={pct(deal.opex_ratio, 1)} />
            <Kv k="Primary risk" v={<span className="v small">{deal.primary_risk ?? "—"}</span>} />
            {deal.indicative_capex_exposure !== null && deal.indicative_capex_exposure !== undefined ? (
              <div className="mt-12">
                <Kv k="Indicative Capex Exposure" v={money(deal.indicative_capex_exposure, 2)} />
                <div className="capex-note mt-8" data-testid="capex-note">
                  Condition indicator only. This amount is not deducted directly. The game
                  instead charges the annual capital reserve shown under Ownership costs.
                </div>
              </div>
            ) : null}
          </Section>

          <Section label="Capital markets">
            <Kv k="Asking price" v={money(deal.asking_price)} strong />
            <Kv k="Going-in cap" v={pct(deal.going_in_cap, 2)} />
            <Kv k="Debt rate" v={pct(deal.debt_rate, 2)} />
            <Kv
              k="Max LTV"
              v={pct(deal.max_ltv, 0)}
              title="Maximum loan-to-value the game's lender will fund"
            />
            <Kv
              k="Loan term (descriptive)"
              v={deal.amortization_years ? `${deal.amortization_years} yrs — not amortizing` : "—"}
              title="The game's debt is interest-only; this term is descriptive only and does not affect cash flows."
            />
            {deal.asking_price && deal.current_noi && deal.max_ltv ? (
              <Kv
                k="Debt yield at ask, max LTV"
                v={pct(debtYieldAt(deal.current_noi, deal.asking_price, deal.max_ltv), 1)}
                title="NOI ÷ loan amount (ask × max LTV) — a lender's measure of the income cushion on the largest possible loan"
              />
            ) : null}
            {deal.asking_price && deal.current_noi && deal.debt_rate && deal.max_ltv ? (
              <Kv
                k="IO DSCR at ask, max LTV"
                v={`${(deal.current_noi / (deal.asking_price * deal.max_ltv * deal.debt_rate)).toFixed(2)}×`}
                title="NOI ÷ annual interest at the property's maximum loan-to-value. Game debt is interest-only, so this is an interest-coverage ratio, not an amortizing DSCR."
              />
            ) : null}
          </Section>

          <Section label="Ownership costs">
            <Kv
              k="Acquisition costs"
              v={`${pct(deal.acquisition_cost_rate ?? 0.02, 1)} of price — cash at close`}
            />
            <div className="mt-8">
              <span className="reserve-chip" data-testid="reserve-rate-chip">
                Annual capital reserve {pct(deal.capital_reserve_rate ?? null, 1)} of value — charged
                every year held
              </span>
            </div>
            <p className="help mt-8">
              The capital reserve above is a real annual cash charge in the game. The capex
              figure under Operations is a condition indicator only, not a cash charge.
            </p>
          </Section>
        </div>

        <div className="drawer-analysis">
          <div className="analysis-block">
            <span className="panel-label">Your analysis</span>
            <div style={{ height: 8 }} />
            <div className="analysis-sub">Market facts → model forecast → policy → decision</div>
          </div>

          {forecast ? (
            <div className="analysis-block">
              <span className="analysis-head">Pre-class forecast</span>
              <Kv k="Predicted value" v={money(forecast.forecast.predictedFairValue)} strong />
              <Kv
                k="Upside vs ask"
                v={deal.asking_price ? signedPercent(forecast.forecast.predictedFairValue / deal.asking_price - 1) : "—"}
              />
              <Kv k="Predicted NOI growth" v={signedPercent(forecast.forecast.predictedNoiGrowth)} />
              <Kv k="Downside probability" v={pct(forecast.forecast.probabilityOfDownside, 0)} />
              <Kv k="Confidence" v={pct(forecast.forecast.confidence, 0)} />
              <Kv k="Model" v={<span className="v small">{forecast.forecast.modelName}</span>} />
            </div>
          ) : null}

          {forecast ? (
            <div className="analysis-block">
              <span className="analysis-head">Investment policy</span>
              <Kv k="Maximum price" v={money(forecast.policy.maxBid)} />
              <Kv k="Target LTV" v={pct(forecast.policy.targetLtv, 0)} />
            </div>
          ) : null}

          <div className="analysis-block" data-testid="drawer-decision">
            <span className="analysis-head">Your decision</span>
            <div className="seg" role="group" aria-label="Decision in drawer">
              <button
                type="button"
                className={draft.action === "PASS" ? "active" : ""}
                onClick={() => onDraft({ ...draft, action: "PASS" })}
                disabled={disabled}
                data-testid={`drawer-pass-${deal.property_id}`}
              >
                Pass
              </button>
              <button
                type="button"
                className={bidding ? "active" : ""}
                onClick={() => onDraft({ ...draft, action: "BID" })}
                disabled={disabled}
                data-testid={`drawer-bid-${deal.property_id}`}
              >
                Bid
              </button>
            </div>
            {bidding ? (
              <div className="mt-8" style={{ display: "flex", gap: 8 }}>
                <div className="money-input" style={{ flex: 1 }}>
                  <span className="prefix">$</span>
                  <input
                    className="input"
                    inputMode="decimal"
                    value={draft.bid}
                    onChange={(e) => onDraft({ ...draft, bid: e.target.value })}
                    placeholder={forecast ? String(forecast.policy.maxBid) : "0.0"}
                    aria-label={`Bid price in millions for ${deal.property_name} (drawer)`}
                    disabled={disabled}
                    data-testid={`drawer-bid-price-${deal.property_id}`}
                  />
                </div>
                <div className="pct-input" style={{ width: 110 }}>
                  <input
                    className="input"
                    inputMode="numeric"
                    value={draft.ltv}
                    onChange={(e) => onDraft({ ...draft, ltv: e.target.value })}
                    placeholder={forecast ? String(Math.round(forecast.policy.targetLtv * 100)) : "60"}
                    aria-label={`Loan-to-value percent for ${deal.property_name} (drawer)`}
                    disabled={disabled}
                    data-testid={`drawer-bid-ltv-${deal.property_id}`}
                  />
                  <span className="suffix">%</span>
                </div>
              </div>
            ) : null}
          </div>

          {impact ? (
            <div className="analysis-block">
              <span className="analysis-head">Capital impact</span>
              <Kv k="Equity required" v={money(impact.equity)} />
              <Kv k={`Deal costs (${pct(acqRate, 1)})`} v={money(impact.dealCosts, 2)} />
              <Kv k="Total cash required" v={money(impact.total)} strong />
              {dynDebtYield !== null ? (
                <Kv
                  k="Debt yield at your bid"
                  v={pct(dynDebtYield, 1)}
                  title="NOI ÷ loan at your proposed price and LTV"
                />
              ) : null}
            </div>
          ) : null}

          {override && (override.priceOver || override.ltvOver) ? (
            <div className="analysis-block" data-testid="drawer-override">
              <span className="analysis-head">Policy override</span>
              <p className="help" style={{ marginTop: 0 }}>
                Deviating from your locked policy is allowed and recorded, not penalized.
              </p>
              {override.priceOver ? (
                <div className="kv">
                  <span className="k">Price</span>
                  <span className="v">
                    {money(bidValue)} — {signedPoints(override.priceDelta / (forecast?.policy.maxBid || 1))} vs max
                  </span>
                </div>
              ) : null}
              {override.ltvOver ? (
                <div className="kv">
                  <span className="k">LTV</span>
                  <span className="v">
                    {pct(ltvValue, 0)} — {signedPoints(override.ltvDelta)} vs target
                  </span>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </Drawer>
  );
}

function ReviewModal({
  deals,
  items,
  onClose,
  onSubmit,
  busy,
}: {
  deals: Deal[];
  items: ReviewItem[];
  onClose: () => void;
  onSubmit: () => void;
  busy: boolean;
}) {
  const nameOf = (id: string) => deals.find((d) => d.property_id === id)?.property_name ?? id;
  return (
    <Modal
      title="Review practice decisions"
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-secondary" onClick={onClose} disabled={busy}>
            Back
          </button>
          <button className="btn btn-primary" onClick={onSubmit} disabled={busy} data-testid="lock-decisions">
            {busy ? "Locking…" : "Lock practice decisions"}
          </button>
        </>
      }
    >
      <table className="table" data-testid="review-table">
        <thead>
          <tr>
            <th>Property</th>
            <th>Decision</th>
            <th className="num">Bid</th>
            <th className="num">LTV</th>
            <th>Policy</th>
          </tr>
        </thead>
        <tbody>
          {items.map(({ deal, item }) => (
            <tr key={deal.property_id} data-testid={`review-row-${deal.property_id}`}>
              <td>{nameOf(deal.property_id)}</td>
              <td>{item.action === "BID" ? <Badge tone="navy">BID</Badge> : <Badge>PASS</Badge>}</td>
              <td className="num">{item.bid === null ? "—" : money(item.bid)}</td>
              <td className="num">{item.ltv === null ? "—" : pct(item.ltv, 0)}</td>
              <td>
                <OverrideCell propertyId={item.propertyId} bid={item.bid} ltv={item.ltv} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="help mt-12">
        Locking submits your fund's sealed decisions. They cannot be edited after locking.
      </p>
    </Modal>
  );
}

function OverrideCell({
  propertyId,
  bid,
  ltv,
}: {
  propertyId: string;
  bid: number | null;
  ltv: number | null;
}) {
  const { state } = useSession();
  const forecast = state?.round?.myForecast.find((f) => f.propertyId === propertyId);
  if (!forecast || bid === null) return <span className="deal-sub">—</span>;
  const priceDelta = bid - forecast.policy.maxBid;
  const priceOver = priceDelta > 1e-9;
  const ltvDelta = ltv !== null ? ltv - forecast.policy.targetLtv : 0;
  const ltvOver = ltvDelta > 1e-9;
  if (!priceOver && !ltvOver) return <Badge tone="ok">within policy</Badge>;
  const parts: string[] = [];
  if (priceOver) parts.push(`Price +${money(priceDelta)}`);
  if (ltvOver) parts.push(`LTV ${signedPoints(ltvDelta)}`);
  return <Badge tone="warn">{parts.join(" · ")}</Badge>;
}
