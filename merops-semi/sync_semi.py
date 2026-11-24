#!/usr/bin/env python3
"""Merops semi-parts sync for cdrone Odoo (dry-run by default; --apply to write).

Desired state comes from config.json (structure from Cobra's multi-level BoM file)
plus an SAP MM60 export CSV (names, units, standard cost THB) passed with --sap.
Never deletes or archives. BoM lines whose quantity needs more decimals than the
'Product Unit' precision are reported as BLOCKED and not written.
"""
import argparse, csv, json, os, sys
sys.path.insert(0, os.environ.get("ODOO_HELPER", "/workspace/cobra/odoo-cdrone"))
import odoo

ap = argparse.ArgumentParser()
ap.add_argument("--sap", required=True, help="MM60 CSV (header row first)")
ap.add_argument("--config", default=os.path.join(os.path.dirname(__file__), "config.json"))
ap.add_argument("--apply", action="store_true")
a = ap.parse_args()
cfg = json.load(open(a.config))
odoo.UID = odoo.uid(); x = odoo.x
NA = {"active_test": False}

need = set(cfg["sap_cost_products"].values()) | set(cfg["create_products"])
sap = {}
with open(a.sap, encoding="utf-8-sig") as f:
    r = csv.reader(f); next(r)
    for row in r:
        if row and row[0] in need:
            sap[row[0]] = {"name": row[1].strip(), "uom": row[5], "price": float(row[10]) if row[10] else None}
missing = need - set(sap)
if missing: sys.exit(f"SAP rows missing: {sorted(missing)}")

prec = {d["name"]: d["digits"] for d in x("decimal.precision", "search_read", [], fields=["name", "digits"])}
qty_digits = prec.get("Product Unit", 2)
uoms = {u["name"]: u["id"] for u in x("uom.uom", "search_read", [], fields=["name"])}
actions, blocked = [], []

def do(desc, fn):
    actions.append(desc)
    if a.apply: return fn()

# 1 category
par = x("product.category", "search_read", [["name", "=", cfg["parent_category"]], ["parent_id.name", "=", cfg["parent_category_parent"]]], fields=["id"])
assert len(par) == 1, par
par = par[0]["id"]
ACC = ["property_account_income_categ_id", "property_account_expense_categ_id", "property_valuation",
       "property_stock_valuation_account_id", "property_stock_journal", "property_cost_method",
       "property_price_difference_account_id", "account_stock_variation_id",
       "property_stock_account_production_cost_id", "removal_strategy_id", "packaging_reserve_method"]
def m2o(v): return v[0] if isinstance(v, list) else v
cat = x("product.category", "search_read", [["name", "=", cfg["category"]], ["parent_id", "=", par]], fields=["id"])
cat_id = cat[0]["id"] if cat else None
if not cat_id:
    cat_id = do(f"create category {cfg['category']} under {par}", lambda: x("product.category", "create", {"name": cfg["category"], "parent_id": par}))
for c in cfg["companies"]:
    ctx = {"allowed_company_ids": [c]}
    want = {k: m2o(v) for k, v in x("product.category", "read", [par], fields=ACC, context=ctx)[0].items() if k != "id"}
    have = {k: m2o(v) for k, v in x("product.category", "read", [cat_id], fields=ACC, context=ctx)[0].items() if k != "id"} if cat_id and not isinstance(cat_id, str) else {}
    diff = {k: v for k, v in want.items() if have.get(k) != v}
    if diff: do(f"category accounting company {c}: {sorted(diff)}", lambda: x("product.category", "write", [cat_id], diff, context=ctx))

# 2 products
def prod(code):
    p = x("product.product", "search_read", [["default_code", "=", code]], fields=["id", "product_tmpl_id", "categ_id", "uom_id", "tracking", "company_id", "name", "qty_available"], context=NA)
    assert len(p) <= 1, (code, p)
    return p[0] if p else None
for code in cfg["create_products"]:
    s = sap[code]; p = prod(code)
    vals = {"default_code": code, "name": s["name"], "type": "consu", "is_storable": True, "tracking": False,
            "categ_id": cat_id, "uom_id": uoms[cfg["uom_map"][s["uom"]]], "company_id": False}
    if not p:
        do(f"create product {code} {s['name']}", lambda: x("product.product", "create", vals))
    else:
        if m2o(p["categ_id"]) != cat_id: do(f"set categ {code}", lambda: x("product.product", "write", [p["id"]], {"categ_id": cat_id}))
for code in cfg["move_products"]:
    p = prod(code)
    moves = x("stock.move", "search_count", [["product_id", "=", p["id"]]]) + x("stock.quant", "search_count", [["product_id", "=", p["id"]]])
    if moves: blocked.append(f"{code}: has stock history, not moved"); continue
    if m2o(p["categ_id"]) != cat_id: do(f"move {code} to Semi", lambda: x("product.product", "write", [p["id"]], {"categ_id": cat_id}))

# 3 costs (company-dependent)
for code, sapc in cfg["sap_cost_products"].items():
    price = sap[sapc]["price"]
    for c in cfg["companies"]:
        ctx = {"allowed_company_ids": [c], "active_test": False}
        p = x("product.product", "search_read", [["default_code", "=", code]], fields=["id", "standard_price"], context=ctx)
        if not p:
            do(f"standard_price {code} c{c} -> {price} (after create)", lambda: x("product.product", "write", [x("product.product", "search", [["default_code", "=", code]], context=ctx)[0]], {"standard_price": price}, context=ctx))
        elif abs(p[0]["standard_price"] - price) > 0.005:
            do(f"standard_price {code} c{c} {p[0]['standard_price']} -> {price}", lambda: x("product.product", "write", [p[0]["id"]], {"standard_price": price}, context=ctx))

# 4 BoMs
co = cfg["bom_company"]
for b in cfg["boms"]:
    p = prod(b["product"])
    if not p: actions.append(f"BoM {b['product']}: product created in this run"); p = prod(b["product"]) if a.apply else None
    if not p: continue
    tmpl = p["product_tmpl_id"][0]
    boms = x("mrp.bom", "search_read", [["product_tmpl_id", "=", tmpl], ["company_id", "=", co], ["type", "=", "normal"]], fields=["id", "bom_line_ids"], context=NA)
    assert len(boms) <= 1, (b, boms)
    lines_have = x("mrp.bom.line", "search_read", [["bom_id", "=", boms[0]["id"]]], fields=["id", "product_id", "product_qty", "uom_id", "sequence"], order="sequence,id") if boms else []
    want = []
    for i, (code, q, u) in enumerate(b["lines"], 1):
        if round(q, qty_digits) != q:
            blocked.append(f"BoM {b['product']} line {i} {code} {q} {u}: needs {len(str(q).split('.')[1])} decimals, Product Unit precision is {qty_digits}")
            continue
        cp = prod(code)
        if not cp: actions.append(f"BoM {b['product']} line {code}: component created in this run"); cp = prod(code) if a.apply else None
        want.append((i, cp["id"] if cp else None, q, uoms[u], code))
    if not boms:
        def mk(tmpl=tmpl, want=want):
            return x("mrp.bom", "create", {"product_tmpl_id": tmpl, "product_qty": 1, "uom_id": uoms["Units"], "type": "normal", "company_id": co,
                                          "bom_line_ids": [(0, 0, {"product_id": w[1], "product_qty": w[2], "uom_id": w[3], "sequence": w[0]}) for w in want]})
        do(f"create BoM {b['product']} with {[(w[4], w[2]) for w in want]}", mk)
        continue
    # edit existing lines in place by sequence; add missing; never remove
    byseq = {l["sequence"]: l for l in lines_have}
    for (i, pid, q, uid_, code) in want:
        l = byseq.get(i)
        if not l:
            do(f"BoM {b['product']} add line {i} {code} {q}", lambda: x("mrp.bom", "write", [boms[0]["id"]], {"bom_line_ids": [(0, 0, {"product_id": pid, "product_qty": q, "uom_id": uid_, "sequence": i})]}))
            continue
        d = {}
        if l["product_id"][0] != pid: d["product_id"] = pid
        if abs(l["product_qty"] - q) > 1e-9: d["product_qty"] = q
        if l["uom_id"][0] != uid_: d["uom_id"] = uid_
        if d: do(f"BoM {b['product']} line {l['id']} seq {i}: {d}", lambda: x("mrp.bom.line", "write", [l["id"]], d))
    extra = [l for l in lines_have if l["sequence"] not in {w[0] for w in want}]
    for l in extra: blocked.append(f"BoM {b['product']} existing line {l['id']} {l['product_id'][1]} qty {l['product_qty']} left unchanged")

print(("APPLIED" if a.apply else "DRY RUN") + f": {len(actions)} actions")
for s in actions: print("  +", s)
for s in blocked: print("  ! BLOCKED/HELD:", s)
