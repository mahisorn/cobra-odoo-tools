# merops-semi

Syncs Cobra's Merops semi-parts into cdrone Odoo: the Goods/Merops/Semi category, the semi-part products, SAP standard costs (per company), and the multi-level skin BoMs (skin → CNC skin → laminate → materials).

- `config.json`: the structure (codes, BoM lines and quantities from Cobra's multi-level BoM file). It holds no prices.
- Names, units and standard costs are read from an SAP MM60 export CSV passed with `--sap`. That file is not committed.

```
python3 sync_semi.py --sap big.csv           # dry run
python3 sync_semi.py --sap big.csv --apply   # write
```

Rules:
- The script never deletes or archives anything.
- Existing BoM lines are edited in place by sequence.
- A product that has stock history is not moved to the new category.
- A BoM line whose quantity has more decimals than the "Product Unit" precision is reported as BLOCKED and not written.
- Re-running is idempotent: a dry run after a successful apply reports 0 actions.
