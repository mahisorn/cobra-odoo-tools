# insee-bom (RC-10 test build)

The INSEE wing shipset structure, inferred from `BOM INSEE REV.0.xlsx` (Chindanai, 26 Nov 2026), built on **cdrone-test only**.
Chang approved it 28 Nov 2026 ("Please try on test"). Production cdrone is never written to. `analysis/snap_products.py` only reads it.

| File | Purpose |
|---|---|
| `spec.py` | quantities, resin split, operations, work centres and sheet prices (all assumptions are here) |
| `build.py` | `setup` (tag, categories, 5 INSEE work centres), `products` (reuse 5 SAP items, create 2 TBC placeholders and 8 INSEE items), `boms` |
| `cost.py` | runs Odoo "Compute price from BoM" on INSEE products only, bottom-up, and reads the cost back |
| `test_mo.py` | creates 1 test MO for 1 shipset, confirms it (MTO creates child MOs), plans it, unreserves it; nothing is produced |
| `verify.py` | reads the BoMs back |
| `odoo_insee.py` | paced RPC (≥1 s) through `../sap-loadtest/odoo_test.py` (asserts cdrone-test); writes the ledger with `created` and `reused` ids kept separate |
| `analysis/` | RC-10 read-only workbook analysis (extract, compare with the SAP master and a production snapshot, build compare.xlsx) |

## Structure (per 1 parent)
```
INSEE-SHIPSET                       QC 4 final 40 min
├─ INSEE-WING-L / INSEE-WING-R      gluing 1+2 40+40, QC 2/3 10+20, sand+putty+coat 60*, primer 60*   (*paint scope TBC)
│  ├─ INSEE-SKIN-xU, INSEE-SKIN-xL  prep 15, mould 5, laminate 60 (2×30), vacuum 15, demould 10, trim 10, QC 1 5
│  │    glass 14001384 0.646 m (L) / 0.586 m (R), PVC 14003634 0.45 m², resin 14001821 0.101/0.097 kg, hardener 14001576 0.051/0.048 kg
│  ├─ INSEE-SPAR-SET ×2             CNC core cutting 15 min (machine)
│  │    glass 1.646 m, PVC 1.2 m², resin 0.270 kg, hardener 0.135 kg
│  ├─ INSEE-TBC-CROD ×2             carbon rod placeholder ฿400 (spec/price TBC, copied from DrN40)
│  └─ 24020685 DP8710 ×0.6          entered as tubes against the ml UoM (see notes)
└─ INSEE-TBC-CONS ×1                consumables placeholder ฿955.04 (sheet: 20% of material)
```
Labour is 980 man-minutes per shipset at ฿300/h (DL 150 + OH 150), plus 60 machine-minutes CNC at ฿350/h.
The resin system is split by laminate weight (0.75 kg resin and 0.375 kg hardener per kg of glass+PVC), which reproduces the sheet's 1.476 / 0.738 kg.

## Undo
The ledger `/workspace/cobra/chindanai-sheet/created_ids.json` holds `created` and `reused` ids. Never delete anything under `reused`.
Undo in this order:
1. Cancel and delete the test MOs.
2. Delete the BoMs.
3. Archive or delete the INSEE products.
4. Delete the work centres, categories and the INSEE tag.
