/**
 * Presentation formatting, and the two places the UI is allowed arithmetic.
 *
 * The engine owns every game number. What lives here is how a *chosen* bid is
 * displayed: the deal-cost and loan lines of the capital-impact panel are the
 * published rates multiplied by the price the player has already entered, so the
 * player can see the cash a decision requires before committing it. The authoritative
 * charges at resolution are the engine's and are rendered verbatim from results.
 */

export function money(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  const sign = value < 0 ? "−" : "";
  if (abs >= 1000) return `${sign}$${(abs / 1000).toFixed(1)}B`;
  return `${sign}$${abs.toFixed(digits)}M`;
}

export function moneySigned(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return value >= 0 ? `+$${value.toFixed(digits)}M` : `−$${Math.abs(value).toFixed(digits)}M`;
}

export function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

/**
 * A signed percentage (a rate expressed as a fraction of 1): +3.3%.
 * For predicted upside, NOI growth, valuation error and returns — all of which
 * are rates, not differences between rates.
 */
export function signedPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const v = value * 100;
  return `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(digits)}%`;
}

/**
 * A signed difference between two percentage rates: +3.0 pp.
 * Reserved for *differences* (e.g. "your LTV was 3 pp over your target"),
 * never for a rate itself.
 */
export function signedPoints(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const v = value * 100;
  return `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(digits)} pp`;
}

/**
 * Legacy alias — migrated to `signedPercent`. Kept only so stale imports fail
 * loudly in code review rather than silently changing what a screen shows.
 */
export function pctSigned(value: number | null | undefined, digits = 1): string {
  return signedPercent(value, digits);
}

export function num(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return value.toLocaleString("en-US", { maximumFractionDigits: digits });
}

export function mm(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${value.toFixed(digits)}M`;
}

export function sqft(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${Math.round(value).toLocaleString("en-US")} SF`;
}

export function qualityLabel(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  if (value >= 0.75) return "A";
  if (value >= 0.55) return "B+";
  if (value >= 0.35) return "B";
  if (value >= 0.2) return "C+";
  return "C";
}

/**
 * The cash a bid requires, from the engine's own published rules
 * (`equity_required_for` in `src/game/adjudicator.py`):
 * equity = price × (1 − LTV); deal costs = price × 2%; the loan is the lender's.
 */
export function capitalImpact(bid: number, ltv: number, acquisitionCostRate: number) {
  const loan = bid * ltv;
  const equity = bid - loan;
  const dealCosts = bid * acquisitionCostRate;
  return { price: bid, loan, equity, dealCosts, total: equity + dealCosts };
}

/**
 * Debt yield: NOI ÷ loan amount. At ask and max LTV the loan is ask × max LTV,
 * so debt yield = NOI ÷ (ask × max LTV) — a lender's measure of the income
 * cushion, independent of leverage.
 */
export function debtYieldAt(noi: number | null, price: number | null, ltv: number | null): number | null {
  if (noi === null || price === null || ltv === null) return null;
  const loan = price * ltv;
  if (!Number.isFinite(loan) || loan <= 0) return null;
  return noi / loan;
}
