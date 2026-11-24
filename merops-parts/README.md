# merops-parts

This tool syncs a Merops part list (the "Flatpack BOM" xlsx) into cdrone Odoo 20 products under `Goods / Merops / RJ2`.

## Rules (Chang, 2026-11-24)
- **Internal Reference** is the Merops part number including its revision, e.g. `P03042-04`.
- **Same full code:** the tool updates that product.
- **New `-XX` revision:** the tool creates a new product and leaves the old one untouched.
- **Products are shared:** `company_id` is left empty. COBRA COMPOSITE STRUCTURES owns them, but every company can use them.
- **Not handled yet:** prices, vendors, and kit products/BoMs. Those decisions come later.
- **Units:** `Units` by default. `config.json` sets `uom_overrides`: ml for L00139-01 and P00460-01, m for P04003-01 and P03800-01.
- **Property values** go into category properties on `Goods / Merops / RJ2` (id 63). The definitions were created on 2026-11-24 with Chang's approval:

  | Property | Name | Type |
  |---|---|---|
  | Weight (g) | `weight_g` | float |
  | Dimensions (mm) | `dimensions_mm` | char |
  | Volume (mm3) | `volume_mm3` | float |
  | Material | `material` | char |
  | Process | `process` | char |
  | Thickness (mm) | `thickness_mm` | float |
  | Blank size (mm) | `blank_size_mm` | char |
  | Base PN | `base_pn` | char |
  | Revision | `revision` | char |

  - The tool matches definitions by their label and writes `categ_id` in the same write, because Odoo drops property values otherwise.
  - The tool never creates or changes definitions.
- **Standard weight:** kg = g/1000, rounded to 2 dp. Parts under 5 g round to 0 and get no weight. Volume is left empty.
- **Legacy products:** existing Cobra-code products are mapped in `config.json` → `legacy_products`.
  - `adopt` rewrites the product's default_code, name and category.
  - `hold` changes nothing.

## config.json overrides
These settings survive a re-sync:
- `include_from_older`: codes to take from an `--older` file when the current file lacks them. P03016-01 was deleted from the online sheet by mistake.
- `name_overrides`: a fixed product name per code, e.g. P03751-01 → "Bracket, Optical Array".
- `uom_overrides`: units other than Units. P03800-01 foam strip is counted in pieces, so it stays on Units.
- `legacy_products`: older Cobra-code products adopted under the Merops code (12201047/48/49 → P03042-04 / P03043-04 / P03046-03).

## Tracking
`config.json` → `tracking` sets each product's tracking:
- **Category defaults:**
  - Made parts are **serial**: 3D print, composite, metal, wood, fuel tank, airbag/parachute, Fuel-Misc.
  - Off-the-shelf hardware, consumables, rope and foam are **lot**.
- **Per-part overrides** take precedence. The 3 off-the-shelf fuel items and the high-quantity parts P04188-01, P03123-01, P03061-01, P03674-01 and P04086-01 are lot.
- Anything not counted in Units (m, ml) is always lot.

Applied on 2026-11-24 with Chang's approval: 130 serial, 69 lot.

## Inputs
- **Current BOM file:** the source of truth for which parts exist and for names and materials.
  - The tool finds the sheet by its `Part No. latest` header.
  - It reads every row, including rows hidden by a filter.
- **`--older` files (optional):** used only to fill in in-cell images, dimensions, volume and weight for the same full code.
  - Images are Excel "Place in Cell" pictures. openpyxl reads these as `#VALUE!`, so the tool resolves them itself through the `richData` parts.

## Usage
```bash
export COBRA_DRONE_ODOO_API_KEY=...
# 1. Dry run (read-only). Writes runs/<timestamp>/dryrun.md, dryrun.csv and plan.json
python3 sync_parts.py dry-run CURRENT.xlsx --older OLD_WITH_IMAGES.xlsx --runs-dir RUNS
# 2. After Chang approves that run:
python3 sync_parts.py apply CURRENT.xlsx --older OLD_WITH_IMAGES.xlsx --plan RUNS/<ts>/plan.json [--only P03010-01]
# --only applies a one-product test. Run a new dry run before applying the rest.
```

## Safety checks in apply
Apply refuses to run if any of these fail:
- The sha256 of every input file matches the plan.
- The dry run, rebuilt against live Odoo, produces the same fingerprint as the plan.
- Each product's `write_date` is unchanged since the dry run.

During apply:
- The tool only creates and writes records. It never unlinks or archives anything.
- A create is skipped if that code appeared in the meantime.
- Images are compared by sha256, falling back to pixel comparison. Running apply twice therefore produces `unchanged`.
