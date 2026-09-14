/**
 * Service context and the invariants every operation shares.
 *
 * The helpers here exist to make three mistakes impossible to make twice:
 *
 *   `requireFund` / `requireMembership`  — a caller may only act as their own fund.
 *   `assertRevision`                     — a caller acting on a view of the session
 *                                          that has since moved is refused.
 *   `offeredPropertyIds`                 — which properties a round is about is read
 *                                          from the engine's own broadcast, never
 *                                          recomputed here.
 */

import type { Engine, PoolResponse } from "./engineClient.js";
import { forbidden, notFound, staleRevision } from "./errors.js";
import type { Aggregate, Store, Transaction } from "./store/types.js";
import type { FundState, MemberState, SessionState } from "./domain.js";
import type { ServiceConfig } from "./config.js";

export interface AppContext {
  readonly store: Store;
  readonly engine: Engine;
  readonly config: ServiceConfig;
  /** Bundle pools are immutable, so one fetch per bundle per process is enough. */
  readonly pools: Map<string, Promise<PoolResponse>>;
  readonly now: () => Date;
}

export function createContext(args: {
  store: Store;
  engine: Engine;
  config: ServiceConfig;
  now?: () => Date;
}): AppContext {
  return {
    store: args.store,
    engine: args.engine,
    config: args.config,
    pools: new Map(),
    now: args.now ?? (() => new Date()),
  };
}

export function pool(ctx: AppContext, bundleId: string): Promise<PoolResponse> {
  let cached = ctx.pools.get(bundleId);
  if (!cached) {
    cached = ctx.engine.bundlePool(bundleId);
    // Cache the promise, not the value: two concurrent uploads at check-in should
    // cause one fetch, and a failed fetch must not be cached forever.
    ctx.pools.set(bundleId, cached);
    cached.catch(() => ctx.pools.delete(bundleId));
  }
  return cached;
}

export function requireFund(tx: { aggregate: Aggregate }, fundId: string): FundState {
  const fund = tx.aggregate.funds.get(fundId);
  if (!fund) throw notFound(`unknown fund '${fundId}'`);
  return fund;
}

export function requireMember(tx: { aggregate: Aggregate }, memberId: string): MemberState {
  const member = tx.aggregate.members.get(memberId);
  if (!member) throw notFound(`unknown member '${memberId}'`);
  return member;
}

/**
 * A caller may act on a fund only if they belong to it, or they are the professor.
 *
 * The professor is allowed because they must be able to fix a seat mid-class — a
 * student who clears their cookies is otherwise stranded with no way back in.
 */
export function assertMayActForFund(member: MemberState, fund: FundState): void {
  if (member.isProfessor) return;
  if (member.fundId !== fund.id) {
    throw forbidden(
      `you are not a member of fund '${fund.id}'; you are in '${member.fundId ?? "no fund"}'`,
    );
  }
}

/**
 * Optimistic concurrency.
 *
 * `If-Match` is optional so an ordinary student click never fails on a race it did
 * not cause, but professor actions that change shared state send it, and the round
 * operations *require* it. Without that, a double-clicked "close round" is a
 * plausible way to resolve a round twice.
 */
export function assertRevision(session: SessionState, expected: number | null): void {
  if (expected === null) return;
  if (session.revision !== expected) {
    throw staleRevision(expected, session.revision);
  }
}

/** Whether a round is accepting submissions. The single definition. */
export function roundAcceptsSubmissions(
  session: SessionState,
  round: { round: number; closedAt: string | null; resolvedAt: string | null } | null,
): boolean {
  if (!round) return false;
  if (round.resolvedAt !== null || round.closedAt !== null) return false;
  if (session.phase === "practice" || session.phase === "round") {
    return session.currentRound === round.round;
  }
  return false;
}

/**
 * The property ids a round is about, read from the engine's own broadcast.
 *
 * Not recomputed from the pool or from `properties_per_round`: if this service ever
 * disagreed with the engine about which buildings are on the table, students would
 * submit decisions for the wrong ones and the auction would silently ignore them.
 */
export function offeredPropertyIds(broadcast: unknown): string[] {
  const deals = (broadcast as { deals?: unknown } | null)?.deals;
  if (!Array.isArray(deals)) return [];
  return deals
    .map((deal) => (deal as { property_id?: unknown }).property_id)
    .filter((id): id is string => typeof id === "string")
    .sort();
}

export function transactionSession(tx: Transaction): SessionState {
  return tx.aggregate.session;
}
