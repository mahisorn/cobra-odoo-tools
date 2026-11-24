# material-costs: Cobra SAP standard material cost sync for cdrone Odoo

Takes Cobra's SAP material price export (xlsx) and creates or updates the matching
products and their standard cost in cdrone Odoo 20 (`https://cdrone.odoo.com`).

## Setup

```bash
pip install -r requirements.txt
export ODOO_URL=https://cdrone.odoo.com      # default
export ODOO_DB=cdrone                        # default
export ODOO_USER=mahisorn_w@cobrainter.com   # default
export COBRA_DRONE_ODOO_API_KEY=...          # required, never commit
export SYNC_RUNS_DIR=/path/to/runs           # optional, default ./runs
export SYNC_ROOT_CATEG="Raw Materials"       # optional parent category name
```

## Approval flow

1. **Dry run** (read-only): `python3 sync_costs.py dry-run FILE.xlsx [--company 1]`
   writes `runs/<YYYYMMDD-HHMMSS>/dryrun.csv`, `dryrun.md` and `plan.json`
   (file SHA-256, counts, prerequisites, and every `action|code`).
2. Send `dryrun.md` to Chang for approval.
3. **Apply**: `python3 sync_costs.py apply FILE.xlsx --plan runs/<ts>/plan.json`
   - refuses if the file's SHA-256 differs from the plan
   - recomputes the diff live and refuses if Odoo changed since the dry run
   - refuses if any row is an error (override with `--skip-errors`)
   - writes `apply.log` and `created-ids.jsonl` into the same run folder
   - checks the first create batch (cost on the target company only) before continuing
4. Re-run the dry run: it should show only `unchanged`.

The tool only ever calls `create` and `write`. It never deletes or archives.

## Expected input (SAP export, first sheet)

`Material, Material Description, Plnt, MTyp, Matl Group, BUn, PGr, Typ, ValCl, Pr., Price, Crcy, Last Chg`

Headers are matched case- and whitespace-insensitively. Required: Material,
Material Description, BUn, Price, Crcy. Prices are taken as THB per 1 base unit.

## Mapping

| SAP column | Odoo |
|---|---|
| Material | `product.template.default_code` (match key) |
| Material Description (whitespace trimmed) | `name` |
| BUn | `uom_id` (KG→kg, M2→m², EA/PC→Units, M→m, L→L, ML→ml, G→g, YD→yd, LB→lb, GAL→gal (US), SET/PAC/ROL/DR/CAN/PAA→Set/Pack/Roll/Drum/Can/Pair) |
| Price (THB) | `standard_price` on company 1 only (company-dependent; set with `allowed_company_ids=[1]`) |
| Matl Group | `categ_id` = `Raw Materials / <group>`; settings copied from `Goods` for every company |
| MTyp, ValCl, PGr, Typ, Plnt, Pr., Last Chg | text note in `description` (Internal Notes) |
| fixed | `type=consu`, `is_storable=True`, `purchase_ok=True`, `sale_ok=False`, `company_id=False` (shared) |

Prerequisites created idempotently by `apply`: the category tree, the stand-alone
units Set/Pack/Roll/Drum/Can/Pair (own reference, `relative_factor=1`), and
activation of yd, lb and gal (US).

## Actions in the report

- `create`: code not in Odoo
- `update`: name, unit, category, SAP note, archived state or cost differ
- `unchanged`: everything already matches
- `error`: bad or duplicate row, non-THB price, unknown unit, or the product is restricted to one company
- `missing_from_file`: a 14*/24* product exists in Odoo but not in the file; it is flagged only, and archiving needs approval
