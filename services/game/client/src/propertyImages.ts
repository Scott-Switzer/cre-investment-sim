/**
 * Illustrative imagery, deterministic per property type.
 *
 * The synthetic addresses do not exist, so the images are deliberately *not*
 * representations of the specific asset: each property type maps to one abstract
 * architectural image, self-authored for this project (SVG, embedded below and served
 * as data URLs at build time). The same type always renders the same image, so a
 * board is stable across reloads and across funds.
 *
 * License note: these four images are original SVG artwork created for this
 * repository (documented in client/public/IMAGE_SOURCES.md) and carry no
 * third-party restriction.
 */

export type PropertyType = "Office" | "Industrial" | "Multifamily" | "Retail";

export interface PropertyImage {
  url: string;
  credit: string;
}

/** Deterministic pick: same type → same image, always. */
export function imageForProperty(propertyType: string): PropertyImage {
  switch (propertyType) {
    case "Industrial":
      return { url: INDUSTRIAL, credit: "Illustrative — original artwork (see IMAGE_SOURCES.md)" };
    case "Office":
      return { url: OFFICE, credit: "Illustrative — original artwork (see IMAGE_SOURCES.md)" };
    case "Multifamily":
      return { url: MULTIFAMILY, credit: "Illustrative — original artwork (see IMAGE_SOURCES.md)" };
    case "Retail":
      return { url: RETAIL, credit: "Illustrative — original artwork (see IMAGE_SOURCES.md)" };
    default:
      return { url: OFFICE, credit: "Illustrative — original artwork (see IMAGE_SOURCES.md)" };
  }
}

function svgUrl(inner: string, sky1: string, sky2: string): string {
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 280" preserveAspectRatio="xMidYMid slice">` +
    `<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">` +
    `<stop offset="0" stop-color="${sky1}"/><stop offset="1" stop-color="${sky2}"/></linearGradient></defs>` +
    `<rect width="640" height="280" fill="url(#sky)"/>${inner}</svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

const OFFICE = svgUrl(
  `<g fill="#31465e"><rect x="70" y="70" width="86" height="180"/><rect x="170" y="40" width="110" height="210"/><rect x="294" y="96" width="74" height="154"/><rect x="382" y="58" width="96" height="192"/></g>` +
    `<g fill="#8fa7bd" opacity="0.75"><rect x="82" y="84" width="14" height="10"/><rect x="104" y="84" width="14" height="10"/><rect x="82" y="104" width="14" height="10"/><rect x="104" y="104" width="14" height="10"/><rect x="82" y="124" width="14" height="10"/><rect x="104" y="124" width="14" height="10"/><rect x="182" y="54" width="18" height="12"/><rect x="208" y="54" width="18" height="12"/><rect x="234" y="54" width="18" height="12"/><rect x="182" y="76" width="18" height="12"/><rect x="208" y="76" width="18" height="12"/><rect x="234" y="76" width="18" height="12"/><rect x="182" y="98" width="18" height="12"/><rect x="208" y="98" width="18" height="12"/><rect x="234" y="98" width="18" height="12"/><rect x="182" y="120" width="18" height="12"/><rect x="208" y="120" width="18" height="12"/><rect x="234" y="120" width="18" height="12"/><rect x="394" y="72" width="16" height="11"/><rect x="418" y="72" width="16" height="11"/><rect x="442" y="72" width="16" height="11"/><rect x="394" y="94" width="16" height="11"/><rect x="418" y="94" width="16" height="11"/><rect x="442" y="94" width="16" height="11"/><rect x="394" y="116" width="16" height="11"/><rect x="418" y="116" width="16" height="11"/><rect x="442" y="116" width="16" height="11"/></g>` +
    `<rect x="0" y="250" width="640" height="30" fill="#22354b"/>`,
  "#c7d3de",
  "#8fa3b6",
);

const INDUSTRIAL = svgUrl(
  `<g><rect x="60" y="130" width="240" height="110" fill="#4a5a6d"/><polygon points="60,130 180,86 300,130" fill="#3a4a5c"/><rect x="330" y="112" width="230" height="128" fill="#55677c"/><polygon points="330,112 445,72 560,112" fill="#42536a"/></g>` +
    `<g fill="#aab9c9"><rect x="90" y="160" width="34" height="34"/><rect x="140" y="160" width="34" height="34"/><rect x="190" y="160" width="34" height="34"/><rect x="240" y="160" width="34" height="34"/><rect x="360" y="146" width="36" height="36"/><rect x="414" y="146" width="36" height="36"/><rect x="468" y="146" width="36" height="36"/><rect x="522" y="146" width="36" height="36"/></g>` +
    `<rect x="252" y="182" width="46" height="58" fill="#2c3b4d"/>` +
    `<rect x="0" y="240" width="640" height="40" fill="#33455a"/>` +
    `<rect x="120" y="52" width="8" height="36" fill="#62748a"/><circle cx="124" cy="50" r="4" fill="#b3372e" opacity="0.85"/>`,
  "#d3dde6",
  "#9db0c2",
);

const MULTIFAMILY = svgUrl(
  `<g fill="#54687e"><rect x="90" y="84" width="150" height="166"/><rect x="260" y="60" width="150" height="190"/><rect x="430" y="100" width="120" height="150"/></g>` +
    `<g fill="#f2e9d8" opacity="0.85"><rect x="104" y="98" width="20" height="16"/><rect x="136" y="98" width="20" height="16"/><rect x="168" y="98" width="20" height="16"/><rect x="104" y="128" width="20" height="16"/><rect x="136" y="128" width="20" height="16"/><rect x="168" y="128" width="20" height="16"/><rect x="104" y="158" width="20" height="16"/><rect x="136" y="158" width="20" height="16"/><rect x="168" y="158" width="20" height="16"/><rect x="104" y="188" width="20" height="16"/><rect x="136" y="188" width="20" height="16"/><rect x="168" y="188" width="20" height="16"/><rect x="274" y="74" width="20" height="16"/><rect x="306" y="74" width="20" height="16"/><rect x="338" y="74" width="20" height="16"/><rect x="274" y="104" width="20" height="16"/><rect x="306" y="104" width="20" height="16"/><rect x="338" y="104" width="20" height="16"/><rect x="274" y="134" width="20" height="16"/><rect x="306" y="134" width="20" height="16"/><rect x="338" y="134" width="20" height="16"/><rect x="274" y="164" width="20" height="16"/><rect x="306" y="164" width="20" height="16"/><rect x="338" y="164" width="20" height="16"/><rect x="274" y="194" width="20" height="16"/><rect x="306" y="194" width="20" height="16"/><rect x="338" y="194" width="20" height="16"/><rect x="442" y="114" width="20" height="16"/><rect x="474" y="114" width="20" height="16"/><rect x="442" y="144" width="20" height="16"/><rect x="474" y="144" width="20" height="16"/><rect x="442" y="174" width="20" height="16"/><rect x="474" y="174" width="20" height="16"/></g>` +
    `<rect x="316" y="210" width="38" height="40" fill="#2e3f52"/><rect x="0" y="250" width="640" height="30" fill="#31445a"/>` +
    `<circle cx="580" cy="46" r="42" fill="#7f97ab" opacity="0.5"/>`,
  "#d8dfe6",
  "#a9bac9",
);

const RETAIL = svgUrl(
  `<g><rect x="80" y="140" width="330" height="100" fill="#5b6d80"/><rect x="80" y="118" width="330" height="26" fill="#43556a"/><rect x="440" y="96" width="120" height="144" fill="#4d5f74"/></g>` +
    `<g fill="#e8f0f5" opacity="0.9"><rect x="100" y="168" width="60" height="44"/><rect x="180" y="168" width="60" height="44"/><rect x="260" y="168" width="60" height="44"/><rect x="340" y="168" width="50" height="44"/><rect x="458" y="120" width="18" height="22"/><rect x="486" y="120" width="18" height="22"/><rect x="514" y="120" width="18" height="22"/></g>` +
    `<rect x="196" y="118" width="98" height="20" fill="#1e7f4f" opacity="0.85"/>` +
    `<rect x="0" y="240" width="640" height="40" fill="#394c60"/>` +
    `<g fill="#c9d4dd"><rect x="70" y="230" width="500" height="4"/></g>`,
  "#d5dee6",
  "#a3b6c7",
);
