/**
 * Deterministic local property imagery.
 *
 * Each property type maps to a small library of professional, CC-licensed
 * photographs (3 variants per type, 12 total) served from the public asset
 * directory. A variant is selected deterministically by a hash of the property id
 * so every asset keeps a stable image across reloads, funds and devices.
 *
 * The images are *illustrative* — the synthetic parcels do not exist and no
 * photograph is represented as the actual address. Every render carries that
 * disclaimer in the tooltip.
 *
 * Sources and licenses: docs/PROPERTY_IMAGE_SOURCES.md
 */

export type PropertyType = "Office" | "Industrial" | "Multifamily" | "Retail";

export interface PropertyImage {
  url: string;
  credit: string;
}

const BASE = "/images/properties";

const VARIANTS: Record<PropertyType, string[]> = {
  Office: ["office-1.jpg", "office-2.jpg", "office-3.jpg"],
  Industrial: ["industrial-1.jpg", "industrial-2.jpg", "industrial-3.jpg"],
  Multifamily: ["multifamily-1.jpg", "multifamily-2.jpg", "multifamily-3.jpg"],
  Retail: ["retail-1.jpg", "retail-2.jpg", "retail-3.jpg"],
};

/** FNV-1a over the property id — stable, cheap, no crypto dependency. */
function hashId(id: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < id.length; i += 1) {
    h ^= id.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

const CREDIT = "Illustrative photography — CC-licensed (docs/PROPERTY_IMAGE_SOURCES.md)";

/**
 * Deterministic pick: same (type, property id) → same variant, always.
 * The property id, not just the type, selects the variant so a board of four
 * industrials does not render the same photo four times.
 */
export function imageForProperty(propertyType: string, propertyId?: string | null): PropertyImage {
  const known = (["Office", "Industrial", "Multifamily", "Retail"] as PropertyType[]).includes(
    propertyType as PropertyType,
  );
  const type: PropertyType = known ? (propertyType as PropertyType) : "Office";
  const variants = VARIANTS[type];
  const idx = propertyId ? hashId(propertyId) % variants.length : 0;
  return { url: `${BASE}/${variants[idx]}`, credit: CREDIT };
}

/** All variant URLs for a type — used by the gallery page and tests. */
export function allVariants(propertyType: string): string[] {
  const known = (["Office", "Industrial", "Multifamily", "Retail"] as PropertyType[]).includes(
    propertyType as PropertyType,
  );
  if (!known) return [];
  return VARIANTS[propertyType as PropertyType].map((f) => `${BASE}/${f}`);
}

/** The four types with at least one asset present — drives the gallery. */
export function populatedTypes(): PropertyType[] {
  return (["Office", "Industrial", "Multifamily", "Retail"] as PropertyType[]).filter(
    (t) => VARIANTS[t].length > 0,
  );
}
