"""Extract material lines from BOM INSEE REV.0.xlsx and compare with SAP master (plan.json) + prod snapshot. Read-only."""
import re, json, collections, openpyxl, pandas as pd
wb = openpyxl.load_workbook("BOM INSEE REV.0.xlsx", read_only=True, data_only=True)
cl = lambda v: (str(v).replace("\xa0", " ").strip() if v is not None else "")
CODE = re.compile(r"^\d{8}$")
lines = []
# Part Cost: A ply, C part/section, D material code/key, E desc, G area, H offcut, I usage, L unit cost, N layers, O qty, Q cost
part = None
for i, r in enumerate(wb["INSEE (Part Cost)"].iter_rows(min_row=2, max_col=18, values_only=True), 2):
    r = [cl(v) for v in r]
    if r[2] and not r[2].startswith("Carbon Rod") and r[2] != "DP8710": part = r[2] if "WING" in r[2] or "Spar" in r[2] else part
    if "WING" in r[2]: skin = r[2]
    if not (r[3] or r[4]) or r[4] in ("",) and not r[3]: continue
    if r[3] in ("",) and not r[4]: continue
    if r[8] == "weight with resin": continue
    sec = r[2] if r[2].startswith("Carbon Rod") or r[2] == "DP8710" else (part or "")
    lines.append(dict(sheet="INSEE (Part Cost)", row=i, assembly=skin if 'skin' in dir() else "", section=sec, key=r[3], description=r[4] or r[2],
                      usage=r[8], layers=r[13], qty=r[14], unit_cost_sheet=r[11], line_cost=r[16], sheet_uom=""))
# Material Codes price list
for i, r in enumerate(wb["Material Codes"].iter_rows(min_row=5, max_col=11, values_only=True), 5):
    r = [cl(v) for v in r]
    if not r[0] or not r[1]: continue
    lines.append(dict(sheet="Material Codes", row=i, assembly="(price list)", section="", key=r[0], description=r[1], sap_code_col=r[3],
                      unit_cost_sheet=r[6], sheet_uom=r[7], note=r[8] or r[9]))
sap = {r["default_code"]: r for r in json.load(open("/workspace/cobra/cobra-semi-parts/loadtest/plan.json"))["records"]}
prod = {p["default_code"]: p for p in json.load(open("snap_prod.json"))["products"] if p["default_code"]}
norm = lambda s: re.sub(r"[^0-9a-z]+", "", s.lower())
SAPN = collections.defaultdict(list)
for c, r in sap.items(): SAPN[norm(r["name"])].append(c)
# key -> code via price list col D
keymap = {l["key"]: l.get("sap_code_col") for l in lines if l["sheet"] == "Material Codes" and CODE.match(l.get("sap_code_col") or "")}
f = lambda v: float(v) if re.match(r"^-?\d+(\.\d+)?$", v or "") else None
for l in lines:
    code, how = "", "none"
    for cand, h in ((l.get("sap_code_col"), "code (col D)"), (l["key"], "code"), (keymap.get(l["key"]), "via Material Codes key")):
        if cand and CODE.match(cand): code, how = cand, h; break
    if not code:
        c = SAPN.get(norm(l["description"]))
        if c: code, how = c[0], f"name ({len(c)} SAP hits)"
    s, p = sap.get(code), prod.get(code); u = f(l["unit_cost_sheet"])
    l.update(code=code, match=how, in_sap=bool(s), sap_type=s and s["mtyp"], sap_name=s and s["name"], sap_uom=s and s["sap_uom"], sap_price=s and s["standard_price"],
             in_prod=bool(p), prod_name=p and p["name"], prod_categ=p and p["categ_id"][1], prod_uom=p and p["uom_id"][1], prod_cost=p and p["standard_price"],
             price_diff_pct=round(100 * (u - s["standard_price"]) / s["standard_price"], 1) if u and s and s["standard_price"] else None,
             name_differs=bool(s and norm(l["description"]) != norm(s["name"])),
             uom_differs=bool(s and l["sheet_uom"] and norm(l["sheet_uom"]) not in (norm(s["sap_uom"]), norm(s["uom"]))))
D = pd.DataFrame(lines); D.to_pickle("insee_lines.pkl")
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 38)
print(D[["sheet", "row", "section", "key", "description", "code", "match", "sap_type", "sap_uom", "sheet_uom", "unit_cost_sheet", "sap_price", "price_diff_pct", "in_prod", "prod_uom", "prod_cost", "name_differs"]].to_string())
