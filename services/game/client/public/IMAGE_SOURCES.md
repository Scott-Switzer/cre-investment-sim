# Image sources and licenses

The deal board, the underwriting drawer and the results screen show **illustrative**
imagery. The properties are synthetic teaching cases — the addresses do not exist —
so no photograph is presented as a depiction of a real building.

## What is used

Four architectural illustrations, one per property type (Office, Industrial,
Multifamily, Retail), selected deterministically: a property's type always renders the
same image, so the board is stable across reloads and identical for every fund.

## Provenance and license

- The images are **original SVG artwork authored for this repository**
  (`client/src/propertyImages.ts`), drawn as flat geometric architectural scenes.
- They are compiled into the client bundle as data URLs; no external request is made
  to render them.
- **License:** same as the repository. No third-party stock photography, no
  attribution requirement, no usage restriction beyond the repository's own terms.

## Why not real photographs

A stock photo of a real office tower would imply a specificity the synthetic data
does not have, and a photograph licensed for a classroom product quietly becomes a
redistribution problem the day the repository is shared. Self-authored illustration
is honest (illustrative by construction) and license-free by construction.

If real photography is introduced later, record it here per file: source URL,
photographer, license name, and whether attribution is required.
