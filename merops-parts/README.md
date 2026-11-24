# merops-parts

This tool syncs a Merops part list (the "Flatpack BOM" xlsx) into cdrone Odoo 20 products under `Goods / Merops / RJ2`.

## Rules (Chang, 2026-11-24)
- **Internal Reference** is the Merops part number including its revision, e.g. `P03042-04`.
- **Same full code:** the tool updates that product.
- **New `-XX` revision:** the tool creates a new product and leaves the old one untouched.
- **Products are shared:** `company_id` is left empty. COBRA COMPOSITE STRUCTURES owns them, but every company can use them.
- **Not handled yet:** prices, vendors, and kit products/BoMs. Those decisions come later.
- **Units:** `Units` by default. `config.json` sets `uom_overrides`: ml for L00139-01 and P00460-01, m for P04003-01 and P03800-01.
- **Property values** (Weight (g), Dimensions (mm), Volume (mm3), Material, Process, Thickness (mm), Blank size (mm), Base PN, Revision):
  - The tool writes them only when the definitions already exist on the category.
  - It never creates those definitions; that is a separate config change that Chang must approve.
- **Legacy products:** existing Cobra-code products are mapped in `config.json` → `legacy_products`.
  - `adopt` rewrites the product's default_code, name and category.
  - `hold` changes nothing.

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
python3 sync_parts.py apply CURRENT.xlsx --older OLD_WITH_IMAGES.xlsx --plan RUNS/<ts>/plan.json
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
