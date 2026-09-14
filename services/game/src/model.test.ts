/**
 * The two halves of the upload contract.
 *
 * The gate that matters is *agreement*: the Node validator and the Python engine must
 * refuse and accept the same files, or a fund passes check-in and is then refused at
 * "start game" — in class, with no chance to fix the file. The first suite therefore
 * reads the Python source and pins every constant and column name to it, rather than
 * restating them in TypeScript and hoping.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  MAX_PLAUSIBLE_FAIR_VALUE,
  MAX_TARGET_LTV,
  MAX_NOI_GROWTH,
  MIN_NOI_GROWTH,
  OPTIONAL_COLUMNS,
  REQUIRED_COLUMNS,
  parseCsv,
  validateModelCsv,
} from "./model.js";
import { FAKE_POOL } from "./testing/fakeEngine.js";
import { buildCsv, CSV_HEADER } from "./testing/scenarios.js";

const SUBMISSION_PY = resolve(process.cwd(), "../../src/game/submission.py");
const python = readFileSync(SUBMISSION_PY, "utf8");

function pythonNumber(name: string): number {
  const match = python.match(new RegExp(`^${name}\\s*=\\s*([-0-9_.]+)`, "m"));
  if (!match) throw new Error(`could not find ${name} in submission.py`);
  return Number(match[1]!.replace(/_/g, ""));
}

function pythonColumnList(name: string): string[] {
  const match = python.match(new RegExp(`${name}: List\\[str\\] = \\[([^\\]]*)\\]`, "s"));
  if (!match) throw new Error(`could not find ${name} in submission.py`);
  return [...match[1]!.matchAll(/"([^"]+)"/g)].map((m) => m[1]!);
}

function context() {
  return { pool: new Map(FAKE_POOL.map((p) => [p.property_id, p])), fundName: "Value Fund" };
}

describe("the upload contract matches the Python validator", () => {
  it("pins every numeric bound to src/game/submission.py", () => {
    expect(MAX_TARGET_LTV).toBe(pythonNumber("MAX_TARGET_LTV"));
    expect(MIN_NOI_GROWTH).toBe(pythonNumber("MIN_NOI_GROWTH"));
    expect(MAX_NOI_GROWTH).toBe(pythonNumber("MAX_NOI_GROWTH"));
    expect(MAX_PLAUSIBLE_FAIR_VALUE).toBe(pythonNumber("MAX_PLAUSIBLE_FAIR_VALUE"));
  });

  it("pins the required and optional column lists", () => {
    expect([...REQUIRED_COLUMNS]).toEqual(pythonColumnList("REQUIRED_COLUMNS"));
    expect([...OPTIONAL_COLUMNS]).toEqual(pythonColumnList("OPTIONAL_COLUMNS"));
  });

  it("requires pool coverage exactly, which is what the engine enforces at start", () => {
    // `_verify_submission_covers_pool` in service/engine_api/engine.py refuses missing
    // *and* unknown ids. If this validator were looser, a fund could pass check-in and
    // then be unable to start.
    expect(python).toContain("REQUIRED_COLUMNS");
    const engineSource = readFileSync(
      resolve(process.cwd(), "../../service/engine_api/engine.py"),
      "utf8",
    );
    expect(engineSource).toMatch(/pool_ids - submitted/);
    expect(engineSource).toMatch(/submitted - pool_ids/);
  });
});

describe("CSV parsing", () => {
  it("keeps a comma inside a quoted notes column from shifting the row", () => {
    // The exact thing students type into the template, and the reason a naive
    // split-on-comma parser cannot be used here.
    const csv =
      "a,b\n" + '"one, and a half",two\n' + '"said ""hello""",plain\n';
    const parsed = parseCsv(csv);
    expect(parsed.header).toEqual(["a", "b"]);
    expect(parsed.rows).toEqual([
      ["one, and a half", "two"],
      ['said "hello"', "plain"],
    ]);
  });

  it("tolerates CRLF, a BOM and a trailing newline from a spreadsheet export", () => {
    const parsed = parseCsv("\uFEFFa,b\r\n1,2\r\n");
    expect(parsed.header).toEqual(["a", "b"]);
    expect(parsed.rows).toEqual([["1", "2"]]);
  });

  it("ignores blank lines", () => {
    const parsed = parseCsv("a,b\n\n1,2\n\n");
    expect(parsed.rows).toEqual([["1", "2"]]);
  });
});

describe("validating a submission", () => {
  it("accepts a well-formed file and reports what it found without scoring it", () => {
    const report = validateModelCsv(buildCsv(), context());
    expect(report.ok).toBe(true);
    expect(report.errors).toEqual([]);
    expect(report.rows).toHaveLength(FAKE_POOL.length);
    expect(report.summary.propertiesMatched).toBe(FAKE_POOL.length);
    expect(report.summary.modelName).toBe("test_model_v1");
    // The teaching point, asserted: check-in describes, it never scores.
    expect(report.summary.scored).toBe(false);
    expect(report.summary.meanPredictedUpsideVsAsk).toBeCloseTo(0.05, 4);
    expect(report.summary.note).toMatch(/No outcome is known/);
  });

  it("names every missing required column", () => {
    const report = validateModelCsv("team_id,property_id\nValue Fund,P1\n", context());
    expect(report.ok).toBe(false);
    expect(report.errors.join(" ")).toMatch(/Missing required column\(s\): model_name/);
    expect(report.errors.join(" ")).toMatch(/predicted_fair_value/);
  });

  it("refuses a file missing properties from this dataset, and says which", () => {
    const report = validateModelCsv(
      buildCsv({ pool: FAKE_POOL.filter((p) => p.property_id !== "P4") }),
      context(),
    );
    expect(report.ok).toBe(false);
    expect(report.errors.join(" ")).toMatch(/from this dataset are missing from your file: P4/);
    expect(report.errors.join(" ")).toMatch(/built for a different property dataset/);
  });

  it("refuses unknown property ids, and says which", () => {
    const csv =
      buildCsv() +
      "Value Fund,NOT-A-PROPERTY,test_model_v1,10,0.02,0.2,9,0.5,,,\n";
    const report = validateModelCsv(csv, context());
    expect(report.ok).toBe(false);
    expect(report.errors.join(" ")).toMatch(/NOT-A-PROPERTY/);
  });

  it("refuses a duplicated property", () => {
    const lines = buildCsv().trim().split("\n");
    const report = validateModelCsv([...lines, lines[1]!].join("\n"), context());
    expect(report.ok).toBe(false);
    expect(report.errors.join(" ")).toMatch(/Duplicate property_id rows/);
  });

  it("refuses a blank or non-numeric required cell rather than reading it as zero", () => {
    // The failure this prevents is the worst kind: a silent default of 0 read as a
    // considered valuation of nothing.
    const csv = buildCsv().replace("10.5000", "");
    const report = validateModelCsv(csv, context());
    expect(report.ok).toBe(false);
    expect(report.errors.join(" ")).toMatch(/required numeric column is blank/);
  });

  it("refuses non-finite values", () => {
    const csv = buildCsv().replace("10.5000", "NaN");
    const report = validateModelCsv(csv, context());
    expect(report.ok).toBe(false);
    expect(report.errors.join(" ")).toMatch(/not a number/);
  });

  it("enforces every documented range", () => {
    const cases: { csv: string; expect: RegExp }[] = [
      { csv: buildCsv({ fairValueOf: () => 0 }), expect: /predicted_fair_value must be > 0/ },
      {
        csv: buildCsv({ fairValueOf: () => 9_000 }),
        expect: /above the plausible cap/,
      },
      { csv: buildCsv({ downside: 1.4 }), expect: /probability_of_downside must be in \[0, 1\]/ },
      { csv: buildCsv({ ltv: 0.99 }), expect: /target_ltv must be in \(0, 0.95\]/ },
      { csv: buildCsv({ noiGrowth: 0.9 }), expect: /predicted_noi_growth must be between/ },
      { csv: buildCsv({ maxBidOf: () => 0 }), expect: /max_bid must be > 0/ },
    ];
    for (const { csv, expect: pattern } of cases) {
      const report = validateModelCsv(csv, context());
      expect(report.ok, `expected a refusal for ${pattern}`).toBe(false);
      expect(report.errors.join(" ")).toMatch(pattern);
    }
  });

  it("refuses a per-property LTV above that property's own ceiling", () => {
    // Not in the CSV contract, but identical to the auction: catching it at check-in
    // means the student is told before the round, not when a bid is refused.
    const report = validateModelCsv(
      buildCsv({ ltv: (p) => (p.max_ltv ?? 0.6) + 0.05 }),
      context(),
    );
    expect(report.ok).toBe(false);
    expect(report.errors.join(" ")).toMatch(/above the property's own ceiling/);
    expect(report.errors.join(" ")).toMatch(/The auction would refuse these bids/);
  });

  it("warns rather than refuses when a fund bids above its own valuation", () => {
    const report = validateModelCsv(
      buildCsv({ maxBidOf: (p) => (p.asking_price ?? 0) * 1.5 }),
      context(),
    );
    expect(report.ok).toBe(true);
    expect(report.warnings.join(" ")).toMatch(/above your own predicted_fair_value/);
  });

  it("warns when the file names more than one team", () => {
    const lines = buildCsv().trim().split("\n");
    lines[1] = lines[1]!.replace("Fund 1", "Someone Else");
    const report = validateModelCsv(lines.join("\n"), context());
    expect(report.ok).toBe(true);
    expect(report.warnings.join(" ")).toMatch(/names 2 different team ids/);
  });

  it("tolerates a currency-formatted number, as a spreadsheet export would produce", () => {
    const report = validateModelCsv(
      buildCsv().replace("10.5000", '"$10.50"'),
      context(),
    );
    expect(report.ok).toBe(true);
    expect(report.rows.find((r) => r.propertyId === "P1")!.forecast.predictedFairValue).toBe(10.5);
  });

  it("throws on a completely empty file rather than reporting zero rows as valid", () => {
    expect(() => validateModelCsv("", context())).toThrow(/empty/);
    expect(() => validateModelCsv("\n\n\n", context())).toThrow(/empty/);
  });

  it("uses the header order the file declares, not the order this code expects", () => {
    const reordered =
      CSV_HEADER.split(",").reverse().join(",") +
      "\n" +
      buildCsv()
        .trim()
        .split("\n")
        .slice(1)
        .map((line) => line.split(",").reverse().join(","))
        .join("\n");
    const report = validateModelCsv(reordered, context());
    expect(report.ok).toBe(true);
    expect(report.rows.find((r) => r.propertyId === "P1")!.policy.maxBid).toBeCloseTo(9.8, 4);
  });
});
