/**
 * Model check-in: upload, validate, lock.
 *
 * Two properties make this safe to run in front of a class.
 *
 * **Locking is write-once, enforced in the transaction.** Not by convention and not
 * by a UI that hides the button: the first commit that sets `modelStatus = 'locked'`
 * wins, and every later attempt is refused with the state machine's own answer. A
 * fund cannot quietly re-upload a better model after seeing Round 1.
 *
 * **A failed validation is a 200 with a report, not an error.** The report is the
 * product here — a student needs to read "these five property ids are missing" and
 * fix their file, and burying that in an HTTP error body would make the check-in
 * screen do string parsing to render it.
 */

import { AppError, conflict, forbidden, notFound } from "./errors.js";
import type { AppContext } from "./context.js";
import { assertMayActForFund, assertRevision, pool, requireFund, requireMember } from "./context.js";
import { assertSafeView, fundOwnerView, type FundView } from "./views.js";
import { validateModelCsv, type ValidationReport } from "./model.js";
import type { ModelRecord, ModelRow } from "./domain.js";
import { nowIso } from "./ids.js";
import type { Grant } from "./auth.js";

export interface UploadModelInput {
  sessionId: string;
  fundId: string;
  grant: Grant;
  csv: string;
  modelName?: string | null;
  expectedRevision?: number | null;
}

export interface UploadModelResult {
  ok: boolean;
  report: ValidationReport;
  fund: (FundView & { forecastSummary: unknown }) | null;
}

export async function uploadModel(
  ctx: AppContext,
  input: UploadModelInput,
): Promise<UploadModelResult> {
  if (input.grant.role !== "professor" && input.grant.fundId !== input.fundId) {
    throw forbidden("you can only upload a model for your own fund");
  }

  // Phase and ownership are checked first, so a student who uploads before check-in
  // opens gets "check-in has not started" rather than a wall of column errors.
  const context = await ctx.store.transact(input.sessionId, (tx) => {
    const session = tx.aggregate.session;
    assertRevision(session, input.expectedRevision ?? null);
    if (session.phase === "lobby") {
      // Distinguished from "closed" on purpose: a student who is early needs to be
      // told to wait, not told that they have missed their chance.
      throw conflict("model check-in has not been opened yet; wait for your professor");
    }
    if (session.phase !== "model_checkin") {
      throw conflict(
        `model check-in is closed (the session is '${session.phase}'); ` +
          "a model is frozen once play begins",
      );
    }
    const member = requireMember(tx, input.grant.memberId);
    const fund = requireFund(tx, input.fundId);
    assertMayActForFund(member, fund);
    if (fund.modelStatus === "locked") {
      throw conflict(
        `'${fund.name}' has locked its model; a locked model cannot be replaced`,
      );
    }
    return { bundleId: session.bundleId, phase: session.phase, fundName: fund.name };
  });

  const poolResponse = await pool(ctx, context.bundleId);
  const byId = new Map(poolResponse.properties.map((p) => [p.property_id, p]));

  const report = validateModelCsv(input.csv, {
    pool: byId,
    fundName: context.fundName,
  });

  if (!report.ok) {
    return { ok: false, report, fund: null };
  }

  const modelName =
    input.modelName?.trim() || report.summary.modelName || `${context.fundName} model`;
  const record: ModelRecord = {
    sessionId: input.sessionId,
    fundId: input.fundId,
    modelName,
    rowCount: report.rows.length,
    validatedAt: nowIso(),
    lockedAt: null,
    rows: report.rows as ModelRow[],
  };
  // Rows are written first. If the transaction below then refuses because the fund
  // locked in the meantime, the orphaned rows are inert: every read path goes through
  // the fund's status, which is still 'locked'.
  await ctx.store.putModel(record);

  const fund = await ctx.store.transact(input.sessionId, (tx) => {
    const member = requireMember(tx, input.grant.memberId);
    const live = requireFund(tx, input.fundId);
    assertMayActForFund(member, live);
    if (live.modelStatus === "locked") {
      throw conflict(`'${live.name}' locked its model while this upload was in flight`);
    }
    live.modelStatus = "validated";
    live.modelName = modelName;
    live.modelRowCount = report.rows.length;
    live.modelValidatedAt = record.validatedAt;
    live.forecastSummary = report.summary;
    tx.putFund(live);
    return fundOwnerView(live);
  });

  assertSafeView(fund, `uploadModel(fund=${input.fundId})`);
  return { ok: true, report, fund };
}

export interface LockModelInput {
  sessionId: string;
  fundId: string;
  grant: Grant;
  expectedRevision?: number | null;
}

export async function lockModel(ctx: AppContext, input: LockModelInput) {
  const existing = await ctx.store.getModel(input.sessionId, input.fundId);
  if (!existing) {
    throw conflict(
      "no validated model to lock yet — upload your prediction file first",
    );
  }

  const fund = await ctx.store.transact(input.sessionId, (tx) => {
    const session = tx.aggregate.session;
    assertRevision(session, input.expectedRevision ?? null);
    const member = requireMember(tx, input.grant.memberId);
    const live = requireFund(tx, input.fundId);
    assertMayActForFund(member, live);

    // The state machine's own answer, and the reason "one and only one lock" is a
    // property rather than a hope: the second caller sees 'locked' and is refused.
    if (live.modelStatus === "locked") {
      throw conflict(
        `'${live.name}' has already locked its model` +
          (live.modelLockedAt ? ` (${live.modelLockedAt})` : ""),
      );
    }
    if (live.modelStatus !== "validated") {
      throw conflict("upload a valid model before locking it");
    }
    const lockedAt = nowIso();
    live.modelStatus = "locked";
    live.modelLockedAt = lockedAt;
    live.modelName = existing.modelName;
    live.modelRowCount = existing.rowCount;
    tx.putFund(live);
    live.forecastSummary = live.forecastSummary ?? null;
    return fundOwnerView(live);
  });

  await ctx.store.putModel({ ...existing, lockedAt: fund.modelLockedAt });
  assertSafeView(fund, `lockModel(fund=${input.fundId})`);
  return fund;
}

export interface ReadModelInput {
  sessionId: string;
  fundId: string;
  grant: Grant;
}

/** A fund's own forecast. Refused for anyone else, including other students. */
export async function readModel(ctx: AppContext, input: ReadModelInput) {
  if (input.grant.role !== "professor" && input.grant.fundId !== input.fundId) {
    throw forbidden("you can only read your own fund's model");
  }
  const record = await ctx.store.getModel(input.sessionId, input.fundId);
  if (!record) throw notFound("this fund has not uploaded a model");
  return {
    fundId: record.fundId,
    modelName: record.modelName,
    rowCount: record.rowCount,
    validatedAt: record.validatedAt,
    lockedAt: record.lockedAt,
    rows: record.rows,
  };
}

export function assertCheckedIn(phase: string): void {
  if (phase !== "model_checkin") {
    throw new AppError(
      "illegal_phase",
      `models can only be locked during check-in, not while the session is '${phase}'`,
    );
  }
}
