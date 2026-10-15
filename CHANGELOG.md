# Changelog

## 0.1.0

The first release, built for ToangTown's Model Lab guns (2026-10-15).

* **The finish library:** 21 finishes (anodized, phosphate, blued, nitrided, ceramic coatings, stainless, polymer,
  rubber, brass, copper, lead, walnut) as physically based values with their sources; 9 measured, 12 estimated and
  marked so. Every finish passes the physical rules (a non-metal's colour inside sRGB 30 to 240, a metal reflecting at
  least linear 0.46, metallic 0 or 1).
* **Coating specs and variants:** a finish on each material slot, as many variants as wanted, each at a wear level.
  `spec_for_modellab` reads a Model Lab build (0.2 or later: upper, lower and barrel slots apart). The `ar15` template
  has six variants: issued, new black, FDE two-tone, OD green ceramic, tungsten with a stainless barrel, abused.
* **The wear bake:** edges, the hands' contacts, the rub lines, occlusion and carbon into the vertex colour, from
  ray-cast exposure (a hidden edge does not wear, a corner gathers grime), every mesh of the gun baked.
* **The checks:** each variant's worn share inside its level's band (new 0 to 1 %, issued 0.3 to 6 %, worn 2 to 15 %,
  abused 6 to 35 %), no wear in corners, every finish physical.
* **One formula** for the checks, the look-dev renders and an engine's material.
