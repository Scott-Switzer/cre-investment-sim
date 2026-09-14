/**
 * The model-upload contract.
 *
 * Students build their model outside the game and upload a CSV. This module decides
 * whether that file may enter play. Three properties matter more than the parsing:
 *
 * **1. Check-in must be at least as strict as the engine's refusal.** The engine
 * hard-rejects a submission that does not cover its pool — by refusing to start the
 * game. If this validator were looser, a fund could pass check-in, lock its model,
 * and then discover at "start game" that its model is unusable, in class, with no
 * opportunity to fix it. So the pool-coverage rule enforced here is *identical* to
 * the engine's, and a test asserts the two agree.
 *
 * **2. The report describes, it never scores.** `summary` carries counts and
 * dispersions, never accuracy, because no outcome is known yet. A check-in screen
 * that hinted at accuracy would defeat the whole exercise.
 *
 * **3. The fund is the authority on identity, not the file.** The CSV contract
 * requires a `team_id` column, so a file must carry one, but a student writing their
 * own team name in it must not be able to submit into another fund. This service
 * ignores the column's *value* for attribution and warns when a file names more than
 * one team, which is the signature of exporting the wrong sheet.
 *
 * Bounds are copied from `src/game/submission.py` deliberately, rather than
 * imported, because the engine is a separate container. A test pins each one so the
 * two cannot drift apart silently.
 */

import { validationFailed } from "./errors.js";
import type { ForecastSummary, ModelRow } from "./domain.js";
import type { PoolProperty } from "./engineClient.js";

// Mirrors src/game/submission.py. A test asserts every value.
export const MAX_TARGET_LTV = 0.95;
export const MIN_NOI_GROWTH = -0.5;
export const MAX_NOI_GROWTH = 0.5;
export const MAX_PLAUSIBLE_FAIR_VALUE = 5_000;

export const REQUIRED_COLUMNS = [
  "team_id",
  "property_id",
  "model_name",
  "predicted_fair_value",
  "predicted_noi_growth",
  "probability_of_downside",
  "max_bid",
  "target_ltv",
] as const;

export const OPTIONAL_COLUMNS = [
  "predicted_noi",
  "predicted_exit_cap",
  "confidence",
  "notes",
  "model_version",
] as const;

// ── CSV ───────────────────────────────────────────────────────────────────

export interface ParsedCsv {
  header: string[];
  rows: string[][];
}

/**
 * RFC 4180 CSV, which is what a spreadsheet exports.
 *
 * Hand-written rather than borrowed because the failure it must handle is specific:
 * a `notes` column containing a comma or a newline is exactly what students type
 * into a submission template, and a naive `split(",")` would silently shift every
 * subsequent column.
 */
export function parseCsv(text: string): ParsedCsv {
  const clean = text.replace(/^\uFEFF/, "");
  const rows: string[][] = [];
  let field = "";
  let row: string[] = [];
  let inQuotes = false;
  let index = 0;

  const pushField = () => {
    row.push(field);
    field = "";
  };
  const pushRow = () => {
    pushField();
    rows.push(row);
    row = [];
  };

  while (index < clean.length) {
    const char = clean[index]!;
    if (inQuotes) {
      if (char === '"') {
        if (clean[index + 1] === '"') {
          field += '"';
          index += 2;
          continue;
        }
        inQuotes = false;
        index += 1;
        continue;
      }
      field += char;
      index += 1;
      continue;
    }
    if (char === '"' && field === "") {
      inQuotes = true;
      index += 1;
      continue;
    }
    if (char === ",") {
      pushField();
      index += 1;
      continue;
    }
    if (char === "\r") {
      index += 1;
      continue;
    }
    if (char === "\n") {
      pushRow();
      index += 1;
      continue;
    }
    field += char;
    index += 1;
  }
  if (field !== "" || row.length > 0) pushRow();

  const nonEmpty = rows.filter((r) => r.some((cell) => cell.trim() !== ""));
  const headerRow = nonEmpty.shift();
  if (!headerRow) return { header: [], rows: [] };
  const header = headerRow.map((h) => h.trim());
  return {
    header,
    rows: nonEmpty.map((r) => {
      // Tolerate a trailing empty field from a spreadsheet export.
      const trimmed = [...r];
      while (trimmed.length > header.length && trimmed[trimmed.length - 1]!.trim() === "") {
        trimmed.pop();
      }
      return trimmed;
    }),
  };
}

function num(raw: string | undefined): number {
  if (raw === undefined) return NaN;
  const cleaned = raw.trim().replace(/^\$/, "").replace(/,/g, "");
  if (cleaned === "") return NaN;
  return Number(cleaned);
}

// ── validation ────────────────────────────────────────────────────────────

export interface ValidationReport {
  ok: boolean;
  errors: string[];
  warnings: string[];
  rows: ModelRow[];
  summary: ForecastSummary;
}

export interface ValidationContext {
  /** The bundle's candidate pool, keyed by property id. */
  pool: Map<string, PoolProperty>;
  /** Fallback model name when the file leaves the column blank. */
  fundName: string;
}

export function validateModelCsv(text: string, context: ValidationContext): ValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];
  const { header, rows } = parseCsv(text);

  if (header.length === 0) {
    throw validationFailed("the uploaded file is empty");
  }

  const columnIndex = new Map(header.map((name, i) => [name, i]));
  const missingColumns = REQUIRED_COLUMNS.filter((c) => !columnIndex.has(c));
  if (missingColumns.length > 0) {
    // Named explicitly: "which column is missing" is the single most common reason a
    // student's first upload fails, and a vague message costs a class five minutes.
    return report(
      false,
      [`Missing required column(s): ${missingColumns.join(", ")}`],
      OPTIONAL_COLUMNS.filter((c) => !columnIndex.has(c)).map(
        (c) => `Optional column absent: ${c}`,
      ),
      [],
      context,
      rows.length,
    );
  }

  const at = (row: string[], name: string): string | undefined => {
    const i = columnIndex.get(name);
    return i === undefined ? undefined : row[i];
  };

  const modelRows: ModelRow[] = [];
  const seen = new Set<string>();
  const duplicateIds: string[] = [];
  const teamIds = new Set<string>();
  const badLtv: string[] = [];
  let missingCells = 0;
  let nonNumericRows = 0;
  let aboveFairValue = 0;

  rows.forEach((row, rowIndex) => {
    const line = rowIndex + 2; // 1-based, plus the header
    const propertyId = (at(row, "property_id") ?? "").trim();
    const teamId = (at(row, "team_id") ?? "").trim();
    if (teamId) teamIds.add(teamId);
    if (!propertyId) {
      errors.push(`Row ${line}: property_id is blank`);
      return;
    }
    if (seen.has(propertyId)) {
      duplicateIds.push(propertyId);
      return;
    }
    seen.add(propertyId);

    const fairValue = num(at(row, "predicted_fair_value"));
    const noiGrowth = num(at(row, "predicted_noi_growth"));
    const downside = num(at(row, "probability_of_downside"));
    const maxBid = num(at(row, "max_bid"));
    const targetLtv = num(at(row, "target_ltv"));

    const rawCells = [
      at(row, "predicted_fair_value"),
      at(row, "predicted_noi_growth"),
      at(row, "probability_of_downside"),
      at(row, "max_bid"),
      at(row, "target_ltv"),
    ];
    if (rawCells.some((cell) => cell === undefined || cell.trim() === "")) {
      missingCells += 1;
      errors.push(`Row ${line} (${propertyId}): a required numeric column is blank`);
      return;
    }
    if ([fairValue, noiGrowth, downside, maxBid, targetLtv].some((v) => !Number.isFinite(v))) {
      nonNumericRows += 1;
      errors.push(`Row ${line} (${propertyId}): a required numeric column is not a number`);
      return;
    }

    if (fairValue <= 0) errors.push(`Row ${line} (${propertyId}): predicted_fair_value must be > 0`);
    if (fairValue > MAX_PLAUSIBLE_FAIR_VALUE)
      errors.push(
        `Row ${line} (${propertyId}): predicted_fair_value above the plausible cap of $${MAX_PLAUSIBLE_FAIR_VALUE}M`,
      );
    if (maxBid <= 0) errors.push(`Row ${line} (${propertyId}): max_bid must be > 0`);
    if (maxBid > MAX_PLAUSIBLE_FAIR_VALUE)
      errors.push(
        `Row ${line} (${propertyId}): max_bid above the plausible cap of $${MAX_PLAUSIBLE_FAIR_VALUE}M`,
      );
    if (downside < 0 || downside > 1)
      errors.push(`Row ${line} (${propertyId}): probability_of_downside must be in [0, 1]`);
    if (targetLtv <= 0 || targetLtv > MAX_TARGET_LTV)
      errors.push(
        `Row ${line} (${propertyId}): target_ltv must be in (0, ${MAX_TARGET_LTV}]`,
      );
    if (noiGrowth < MIN_NOI_GROWTH || noiGrowth > MAX_NOI_GROWTH)
      errors.push(
        `Row ${line} (${propertyId}): predicted_noi_growth must be between ${MIN_NOI_GROWTH} and ${MAX_NOI_GROWTH}`,
      );

    const confidenceRaw = at(row, "confidence");
    const confidence =
      confidenceRaw === undefined || confidenceRaw.trim() === "" ? null : num(confidenceRaw);
    if (confidence !== null && (!Number.isFinite(confidence) || confidence < 0 || confidence > 1)) {
      errors.push(`Row ${line} (${propertyId}): confidence must be in [0, 1]`);
    }

    // Not an error in the engine either, so not one here: a team may deliberately
    // bid above its own valuation. It is worth *saying*, because on the debrief it is
    // the difference between a modelling error and a management decision.
    if (maxBid > fairValue) aboveFairValue += 1;

    // Stricter than the CSV contract but identical to the auction: the engine refuses
    // an LTV above the property's own ceiling. Catching it here means the student is
    // told at check-in rather than discovering it when a bid is rejected mid-round.
    const poolEntry = context.pool.get(propertyId);
    const poolMaxLtv = poolEntry?.max_ltv;
    if (typeof poolMaxLtv === "number" && targetLtv > poolMaxLtv + 1e-9) {
      badLtv.push(propertyId);
    }

    modelRows.push({
      propertyId,
      forecast: {
        modelName: (at(row, "model_name") ?? "").trim() || context.fundName,
        predictedFairValue: fairValue,
        predictedNoiGrowth: noiGrowth,
        probabilityOfDownside: downside,
        confidence,
      },
      policy: { maxBid, targetLtv },
    });
  });

  if (duplicateIds.length > 0) {
    const sample = [...new Set(duplicateIds)].slice(0, 5).join(", ");
    errors.push(
      `Duplicate property_id rows (${duplicateIds.length}): ${sample}${duplicateIds.length > 5 ? "…" : ""}`,
    );
  }
  if (missingCells > 0) errors.push(`${missingCells} row(s) have a blank required numeric cell`);
  if (nonNumericRows > 0) errors.push(`${nonNumericRows} row(s) have a non-numeric required cell`);

  // ── the pool check, identical to the engine's ──────────────────────────
  const submitted = new Set(modelRows.map((r) => r.propertyId));
  const poolIds = new Set(context.pool.keys());
  const unknown = [...submitted].filter((id) => !poolIds.has(id)).sort();
  const missing = [...poolIds].filter((id) => !submitted.has(id)).sort();

  if (unknown.length > 0) {
    errors.push(
      `${unknown.length} property id(s) are not offered by this dataset: ` +
        `${unknown.slice(0, 5).join(", ")}${unknown.length > 5 ? "…" : ""}`,
    );
  }
  if (missing.length > 0) {
    errors.push(
      `${missing.length} property id(s) from this dataset are missing from your file: ` +
        `${missing.slice(0, 5).join(", ")}${missing.length > 5 ? "…" : ""}`,
    );
  }
  if (unknown.length > 0 || missing.length > 0) {
    errors.push(
      "This model was built for a different property dataset. Download the correct packet " +
        "or create a session using the matching bundle.",
    );
  }

  if (badLtv.length > 0) {
    errors.push(
      `${badLtv.length} row(s) request a target LTV above the property's own ceiling ` +
        `(e.g. ${badLtv.slice(0, 3).join(", ")}). The auction would refuse these bids.`,
    );
  }
  if (teamIds.size > 1) {
    warnings.push(
      `The file names ${teamIds.size} different team ids (${[...teamIds].slice(0, 3).join(", ")}). ` +
        "It will be recorded against your own fund, but this usually means the wrong sheet was exported.",
    );
  }
  if (aboveFairValue > 0) {
    warnings.push(
      `${aboveFairValue} row(s) set max_bid above your own predicted_fair_value. ` +
        "Allowed — your policy is yours — but it is a deliberate choice worth noticing.",
    );
  }

  return report(errors.length === 0, errors, warnings, modelRows, context, rows.length);
}

function report(
  ok: boolean,
  errors: string[],
  warnings: string[],
  rows: ModelRow[],
  context: ValidationContext,
  rawRowCount: number,
): ValidationReport {
  return {
    ok,
    errors,
    warnings,
    rows,
    summary: summarise(rows, context, rawRowCount, ok),
  };
}

/**
 * Descriptive statistics for the check-in screen.
 *
 * `scored: false` is part of the payload rather than a comment: the check-in screen
 * renders from this object, and stating in the data that nothing here is a score
 * makes it much harder to accidentally display one.
 */
function summarise(
  rows: ModelRow[],
  context: ValidationContext,
  rawRowCount: number,
  ok: boolean,
): ForecastSummary {
  const modelName = rows[0]?.forecast.modelName ?? "unnamed model";
  const base = {
    modelName,
    scored: false as const,
    note:
      "Descriptive only. No outcome is known until rounds resolve, so nothing here " +
      "can tell you whether the forecast is any good.",
  };
  if (!ok || rows.length === 0) {
    return {
      propertiesMatched: 0,
      meanPredictedUpsideVsAsk: null,
      meanPredictedNoiGrowth: null,
      meanDownsideProbability: null,
      meanMaxBidDiscountToAsk: null,
      meanTargetLtv: null,
      ...base,
    };
  }

  const upsides: number[] = [];
  const discounts: number[] = [];
  for (const row of rows) {
    const ask = context.pool.get(row.propertyId)?.asking_price;
    if (typeof ask !== "number" || ask <= 0) continue;
    upsides.push(row.forecast.predictedFairValue / ask - 1);
    discounts.push(row.policy.maxBid / ask - 1);
  }
  const mean = (xs: number[]): number | null =>
    xs.length === 0 ? null : round(xs.reduce((a, b) => a + b, 0) / xs.length);

  return {
    propertiesMatched: rows.length,
    meanPredictedUpsideVsAsk: mean(upsides),
    meanPredictedNoiGrowth: mean(rows.map((r) => r.forecast.predictedNoiGrowth)),
    meanDownsideProbability: mean(
      rows
        .map((r) => r.forecast.probabilityOfDownside)
        .filter((v): v is number => v !== null),
    ),
    meanMaxBidDiscountToAsk: mean(discounts),
    meanTargetLtv: mean(rows.map((r) => r.policy.targetLtv)),
    ...base,
  };
}

function round(value: number): number {
  return Math.round(value * 1e6) / 1e6;
}
