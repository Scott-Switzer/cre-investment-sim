/**
 * Property image library invariants:
 * - deterministic by (type, property id): same deal → same variant everywhere
 * - multiple variants per type: a 4-deal board of one type does not repeat
 * - public URL shape, served locally, never hotlinked
 */

import { describe, expect, it } from "vitest";

import { allVariants, imageForProperty, populatedTypes } from "./propertyImages";

describe("property image library", () => {
  it("provides three variants for all four property types", () => {
    expect(populatedTypes()).toEqual(["Office", "Industrial", "Multifamily", "Retail"]);
    for (const type of populatedTypes()) {
      expect(allVariants(type)).toHaveLength(3);
    }
  });

  it("maps deterministically: same (type, id) always returns the same variant", () => {
    const a = imageForProperty("Industrial", "OC-INDU-01");
    const b = imageForProperty("Industrial", "OC-INDU-01");
    expect(a.url).toBe(b.url);
  });

  it("selects by property id, not just type: distinct ids spread across variants", () => {
    const ids = ["OC-INDU-01", "OC-INDU-02", "OC-INDU-03", "OC-INDU-04", "OC-INDU-05"];
    const urls = new Set(ids.map((id) => imageForProperty("Industrial", id).url));
    expect(urls.size).toBeGreaterThan(1);
  });

  it("serves from the local public asset directory, never a remote host", () => {
    for (const type of populatedTypes()) {
      for (const url of allVariants(type)) {
        expect(url).toMatch(/^\/images\/properties\/.+\.jpg$/);
      }
    }
    expect(imageForProperty("Office", "OC-OFFI-01").url).toMatch(/^\/images\/properties\/office-\d\.jpg$/);
  });

  it("falls back to Office for unknown types and defaults to the first variant", () => {
    const unknown = imageForProperty("DataCenter", "X-1");
    expect(unknown.url).toMatch(/^\/images\/properties\/office-[123]\.jpg$/);
    const allOffice = allVariants("Office");
    expect(imageForProperty("Office", null).url).toBe(allOffice[0]);
  });

  it("carries the illustrative credit on every image", () => {
    for (const type of populatedTypes()) {
      const img = imageForProperty(type, "any-id");
      expect(img.credit).toContain("Illustrative");
      expect(img.credit).toContain("PROPERTY_IMAGE_SOURCES");
    }
  });
});
