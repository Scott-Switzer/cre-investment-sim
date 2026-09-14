/**
 * The deal board — the central teaching UI.
 *
 * Board → drawer → decision → review → locked. The drawer never navigates away from
 * the board. Every number shown is either the engine's (deal data, forecasts,
 * results) or presentation arithmetic on a bid the player has typed (capital impact),
 * from the engine's own published rates.
 */

import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { api, ApiError, type DecisionItem, type Deal, type ForecastRow, type RoundView } from "../api";
import { Badge, Drawer, ErrorBox, Kv, Modal, Section } from "../components";
import { capitalImpact, money, num, pct, pctSigned, qualityLabel, sqft } from "../format";
import { SessionTopbar } from "../chrome";
import { imageForProperty } from "../propertyImages";
import { useSession } from "../session";

type Draft = { action: "PASS" | "BID"; bid: string; ltv: string };

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
            {submitted ? (
              <Badge tone="ok">decisions locked</Badge>
            ) : (
              <Badge tone={round?.isOpenForSubmissions ? "ok" : "warn"}>
                {round?.isOpenForSubmissions ? "open for decisions" : "market closed"}
              </Badge>
            )}
          </div>
        </div>

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

        <div className="board" data-testid="deal-board">
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
}: {
  deal: Deal;
  draft: Draft;
  onDraft: (d: Draft) => void;
  onOpen: () => void;
  forecast: ForecastRow | undefined;
  acqRate: number;
  disabled: boolean;
}) {
  const image = imageForProperty(deal.property_type);
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
      className={`deal-card ${decided ? "decided-bid" : bidding ? "decided-pass" : ""}`}
      data-testid={`deal-card-${deal.property_id}`}
    >
      <div className="deal-img">
        <img src={image.url} alt="" aria-hidden="true" />
        <span className="type-chip">{deal.property_type}</span>
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
      <div className="deal-body">
        <div>
          <div className="deal-name" data-testid={`deal-name-${deal.property_id}`}>{deal.property_name}</div>
          <div className="deal-sub">{deal.submarket} · {deal.property_type}</div>
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
            <div className="m-label">Predicted upside</div>
            <div className="m-value">{upside === null ? "—" : pctSigned(upside)}</div>
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

        <div className="bid-inputs">
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
        </div>

        {impact && ltvValue !== null ? (
          <div className="capital" aria-label="Capital impact of this bid">
            <div className="capital-rows">
              <Kv k="Purchase price" v={money(impact.price)} />
              <Kv k="Loan" v={money(impact.loan)} />
              <Kv k="Equity required" v={money(impact.equity)} />
              <Kv k={`Deal costs (${pct(acqRate, 1)})`} v={money(impact.dealCosts, 2)} />
            </div>
            <div className="capital-total">
              <span className="t-label">Total cash required</span>
              <span className="t-value" data-testid={`total-cash-${deal.property_id}`}>
                {money(impact.total)}
              </span>
            </div>
          </div>
        ) : null}

        <div className="deal-actions">
          <button className="btn btn-secondary" onClick={onOpen} data-testid={`underwrite-${deal.property_id}`}>
            Underwrite
          </button>
        </div>
      </div>
    </article>
  );
}

function UnderwritingDrawer({
  deal,
  forecast,
  onClose,
}: {
  deal: Deal;
  forecast: ForecastRow | undefined;
  onClose: () => void;
}) {
  return (
    <Drawer
      title={deal.property_name}
      subtitle={`${deal.property_type} · ${deal.submarket}${deal.units ? ` · ${num(deal.units)} units` : ""}`}
      onClose={onClose}
    >
      <Section label="Property">
        <Kv k="Building" v={sqft(deal.building_sf)} />
        {deal.units ? <Kv k="Units" v={num(deal.units)} /> : null}
        <Kv k="Year built" v={deal.year_built ?? "—"} />
        <Kv k="Occupancy" v={pct(deal.occupancy, 1)} />
        <Kv k="WALT" v={deal.walt === null ? "—" : `${deal.walt.toFixed(1)} yrs`} />
        <Kv k="Tenant concentration" v={pct(deal.tenant_concentration, 0)} />
        <Kv k="Lease rollover" v={deal.lease_expiry_profile ?? "—"} />
      </Section>

      <Section label="Operations">
        <Kv k="Current NOI" v={money(deal.current_noi, 2)} />
        <Kv k="Market rent" v={deal.market_rent === null ? "—" : `$${deal.market_rent.toFixed(2)}/SF/mo`} />
        <Kv k="In-place rent" v={deal.in_place_rent === null ? "—" : `$${deal.in_place_rent.toFixed(2)}/SF/mo`} />
        <Kv k="Opex ratio" v={pct(deal.opex_ratio, 1)} />
        <Kv k="Property quality" v={`${qualityLabel(deal.property_quality)} · ${pct(deal.property_quality, 0)}`} />
        <Kv k="Primary risk" v={<span className="v small">{deal.primary_risk ?? "—"}</span>} />
        {deal.indicative_capex_exposure !== null && deal.indicative_capex_exposure !== undefined ? (
          <div className="mt-12">
            <Kv k="Indicative Capex Exposure" v={money(deal.indicative_capex_exposure, 2)} />
            <div className="capex-note mt-8" data-testid="capex-note">
              {deal.indicative_capex_note ??
                "Analytical property-condition feature. Not directly deducted from NAV."}
            </div>
          </div>
        ) : null}
      </Section>

      <Section label="Capital markets">
        <Kv k="Asking price" v={money(deal.asking_price)} strong />
        <Kv k="Going-in cap" v={pct(deal.going_in_cap, 2)} />
        <Kv k="Debt rate" v={pct(deal.debt_rate, 2)} />
        <Kv k="Max LTV" v={pct(deal.max_ltv, 0)} />
        <Kv k="Amortization" v={deal.amortization_years ? `${deal.amortization_years} yrs` : "—"} />
        {deal.asking_price && deal.current_noi ? (
          <Kv
            k="Debt yield at ask"
            v={pct(deal.current_noi / deal.asking_price, 1)}
            title="NOI ÷ price — a lender's measure of the income cushion, independent of leverage"
          />
        ) : null}
        {deal.asking_price && deal.current_noi && deal.debt_rate && deal.max_ltv ? (
          <Kv
            k="DSCR at ask, max LTV"
            v={`${(deal.current_noi / (deal.asking_price * deal.max_ltv * deal.debt_rate)).toFixed(2)}×`}
            title="NOI ÷ annual interest at the property's maximum loan-to-value"
          />
        ) : null}
      </Section>

      <Section label="Game ownership costs">
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
          The reserve above is an actual annual cash charge in the game. The capex figure under
          Operations is not — it is an analytical condition feature.
        </p>
      </Section>

      {forecast ? (
        <Section label="Your team's pre-class forecast">
          <Kv k="Predicted fair value" v={money(forecast.forecast.predictedFairValue)} strong />
          <Kv
            k="Upside vs ask"
            v={deal.asking_price ? pctSigned(forecast.forecast.predictedFairValue / deal.asking_price - 1) : "—"}
          />
          <Kv k="Predicted NOI growth" v={pctSigned(forecast.forecast.predictedNoiGrowth)} />
          <Kv k="Downside probability" v={pct(forecast.forecast.probabilityOfDownside, 0)} />
          <Kv k="Confidence" v={pct(forecast.forecast.confidence, 0)} />
          <Kv k="Model" v={<span className="v small">{forecast.forecast.modelName}</span>} />
          <hr className="divider" />
          <span className="panel-label">Your investment policy</span>
          <div style={{ height: 6 }} />
          <Kv k="Maximum price" v={money(forecast.policy.maxBid)} />
          <Kv k="Target LTV" v={pct(forecast.policy.targetLtv, 0)} />
        </Section>
      ) : null}
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
  const priceOver = bid > forecast.policy.maxBid + 1e-9;
  const ltvOver = ltv !== null && ltv > forecast.policy.targetLtv + 1e-9;
  if (!priceOver && !ltvOver) return <Badge tone="ok">within policy</Badge>;
  return <Badge tone="warn">override</Badge>;
}
