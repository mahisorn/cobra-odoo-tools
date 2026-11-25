# sap-loadtest

Load test: put every material from Cobra's SAP MM60 standard-cost export (plant 1000, ~258k codes) into the
**cdrone-test** database to see how Odoo 20 behaves with 200k+ products. Test db only: `odoo_test.py` refuses any other host.

Approved by Chang 24 Nov 2026 19:04 ICT: all material types, 9 new count UoMs, SAP standard cost on both companies,
no-price items at 0, skip the 10 cancelled codes.

| File | Purpose |
|---|---|
| `odoo_test.py` | XML-RPC client pinned to `cdrone-test`, 300 s socket timeout, auth retry |
| `load_sap.py` | parse the CSV (expands rows pasted inside 2 corrupt xlsx cells), map UoM, build `plan.json`; `--pilot`, `--apply`, `--fix-costs` |
| `apply.py` | creates UoMs + `Goods/Cobra SAP/<MTyp>` categories, then products in sequential batches of 1,000 (one call in flight, >=1 s gap, chatter off), company-2 cost via `web_save_multi`, final cost fix pass |
| `run_full.sh` | nohup wrapper, restarts after a crash; reruns skip existing codes |
| `verify.py` | read back code/name/UoM/category/tracking/company/cost (both companies) vs plan |
| `timing.py` | times search by code/name, list view, BoM component name_search, stock.quant |
| `probe.py` | read-only access/profile checks |
| `PLAN.md` | the approved plan |

Input `../big.csv` (from the SAP xlsx with `parse_big.py`) is not committed. Neither are run outputs (`plan.json`, `progress.jsonl`, logs).

Undo (test only): archive or unlink products under `Goods/Cobra SAP`.

Input path defaults to `../big.csv`; override with `SAP_MM60_CSV=/path/big.csv`.

Run: `export COBRA_DRONE_ODOO_API_KEY=...; python3 load_sap.py` (dry run) → `python3 load_sap.py --apply --pilot` → `nohup ./run_full.sh &` → `python3 verify.py` → `python3 timing.py`.

## Run history (24–25 Nov 2026, ICT)

- Pilot 1,000 products 19:07: 84 products/s on create, all read back correct.
- Full load 19:08 → finished 25 Nov 03:58:56 (about 8 h 50 min wall clock). Speed about 90/s early, 65–70/s mid, down to about 38/s late.
- SSLEOF / read-timeout crashes at about 78k/82k and 31k/32k into later runs; stalls of 6 and 16 min. On a create timeout the loader
  dropped batches to 500; `run_full.sh` restarted it (6 attempts) and skip-existing resumed cleanly. Some timed-out creates had
  committed on the server, so the per-batch log undercounts (249,461 logged vs 257,961 in Odoo).
- The final cost fix pass first missed its category lookup (bug, fixed); rerun 25 Nov 07:04 set company-2 cost on 3,000 products
  from crashed batches.
- `verify.py` 25 Nov: 257,961 products under Goods/Cobra SAP = plan, 0 missing, 0 duplicates, all 14 type categories match,
  9 count UoMs present, code/name/UoM/category/untracked/shared/cost on both companies correct for every product
  (39,329 no-price items at 0).
- `timing.py` (median of 3, includes ~0.3 s network): exact code 0.31 s, name ilike 0.31 s, list view 80 0.41 s (category filter 0.38 s,
  offset 80k 0.49 s), BoM component name_search 0.55–0.70 s, product count 0.37 s, stock.quant 0.31 s.
