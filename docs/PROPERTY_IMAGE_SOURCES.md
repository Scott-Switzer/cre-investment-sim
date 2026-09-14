# Property Image Sources

The deal board and results screens use a small local library of commercial-
real-estate photography. Twelve images, three variants per property type, 
selected deterministically by a hash of the synthetic property id.

**These photographs are illustrative only.** The properties in the simulation
are semi-synthetic teaching assets; no photograph is represented as the actual
property, its address, or its condition. A deterministic type + id mapping only
means every fund sees the same image for the same deal.

## Library

| Type | File | License | Title | Creator / Source |
|---|---|---|---|---|
| Office | `client/public/images/properties/office-1.jpg` | BY-SA 2.0 | Wainwright Building, 7th Street and Chestnut Street, St. Lou | [w_lemay](https://commons.wikimedia.org/w/index.php?curid=134543318) |
| Office | `client/public/images/properties/office-2.jpg` | BY-SA 2.0 | Rookery Building, LaSalle Street and Adams Street, Chicago,  | [w_lemay](https://commons.wikimedia.org/w/index.php?curid=134419763) |
| Office | `client/public/images/properties/office-3.jpg` | BY-SA | KeyBank Tower, 2nd Street and Main Street, Dayton, OH | [Warren LeMay](https://commons.wikimedia.org/w/index.php?curid=147053210) |
| Industrial | `client/public/images/properties/industrial-1.jpg` | BY-SA 4.0 | High-bay warehouse in the central industrial warehouse in Er | [JanatAMANNGroup](https://commons.wikimedia.org/w/index.php?curid=93324916) |
| Industrial | `client/public/images/properties/industrial-2.jpg` | BY-SA 4.0 | Industrial warehouse | [Castle Hills AS](https://commons.wikimedia.org/w/index.php?curid=122996371) |
| Industrial | `client/public/images/properties/industrial-3.jpg` | BY-SA 3.0 | Industrial Warehouse - Early 20th Century Building - panoram | [agracier - NO VIEWS](https://commons.wikimedia.org/w/index.php?curid=57316156) |
| Multifamily | `client/public/images/properties/multifamily-1.jpg` | BY-SA | Wohnbebauung an der Johannesstraße, Kiel-Gaarden-Ost | [DYVER](https://commons.wikimedia.org/w/index.php?curid=196004619) |
| Multifamily | `client/public/images/properties/multifamily-2.jpg` | BY-SA 3.0 | Apartment buildings at Praia da Rocha, Portimão | [Steven Fruitsmaak](https://commons.wikimedia.org/w/index.php?curid=4872535) |
| Multifamily | `client/public/images/properties/multifamily-3.jpg` | BY-SA 4.0 | 20140723 Postmodern apartment buildings in Helmond 02 | [Mark Ahsmann](https://commons.wikimedia.org/w/index.php?curid=37923995) |
| Retail | `client/public/images/properties/retail-1.jpg` | BY-SA 2.0 | Toptani Shopping Mall Tirana 2016 | [Photo: Chris Walts](https://commons.wikimedia.org/w/index.php?curid=52560642) |
| Retail | `client/public/images/properties/retail-2.jpg` | BY-SA 3.0 | File:Cevahir Shopping Mall in Istanbul.jpg | [CherryX](https://commons.wikimedia.org/w/index.php?curid=26504385) |
| Retail | `client/public/images/properties/retail-3.jpg` | BY-SA 3.0 | Aquarium in shopping mall, Kaunas | [Foledman](https://commons.wikimedia.org/w/index.php?curid=7046986) |

## License notes

- **CC0 / Public Domain Mark**: no attribution required.
- **CC BY**: attribution required — provided via the creator/source link above and in
  the UI's image credit tooltip.
- **CC BY-SA**: attribution required and derivatives must stay share-alike. These
  images are used unmodified (only resized/recompressed for web delivery, which
  does not create a new creative work requiring re-licensing).

## Acquisition

Sourced via the Openverse API (api.openverse.org) and re-downloaded on demand by
`scripts/curate_property_images.py`. The script records license metadata into
`client/public/images/properties/manifest.json` at download time.

Local copies are committed to the repository — the app never hotlinks.
