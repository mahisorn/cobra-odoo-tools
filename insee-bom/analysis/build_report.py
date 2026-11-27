import pandas as pd, json, pickle, re
D = pd.read_pickle("insee_lines.pkl"); M = pickle.load(open("mm60_cmp.pkl", "rb"))
sap = {r["default_code"]: r for r in json.load(open("/workspace/cobra/cobra-semi-parts/loadtest/plan.json"))["records"]}
prod = {p["default_code"]: p for p in json.load(open("snap_prod.json"))["products"] if p["default_code"]}
f = lambda v: float(v) if re.match(r"^-?\d+(\.\d+)?$", str(v or "")) else 0.0
# suggested SAP candidates for no-code items (manual search, need Chindanai to confirm)
SUG = {"DP8710": "24020685", "T700 16mm OD  ID 14mm": "", "pvc 2mm": "14003673", "G200": "14001386", "Twill 205gsm": "14003685",
       "CBT20X18": "", "CBT40X37": "", "CBT52X50": "", "CBT13X10": "", "EXANDFOAM": "", "MONOKOAT": "", "CARBONUD200": "", "CARBONTWILL200SYT45FR": "14003571", "SNAP": ""}
def sug(r):
    c = SUG.get(r["key"]) or SUG.get(r["description"]) or ""
    if not c: return ""
    s = sap[c]; return f"{c} {s['name']} ({s['mtyp']}, {s['sap_uom']}, ฿{s['standard_price']}){' – in prod' if c in prod else ' – not in prod'}"
D["candidate_if_no_code"] = D.apply(lambda r: sug(r) if not r["code"] else "", axis=1)
# BoM structure (per shipset) from INSEE (Part Cost)
B = D[D.sheet == "INSEE (Part Cost)"].copy()
B.loc[B.key.isin(["SR1280","SD4993"]), ["assembly","section"]] = ["WHOLE SHIPSET (resin system)", "Laminating resin + hardener"]
B["qty_per_shipset"] = B.apply(lambda r: f(r["usage"]) * (f(r["layers"]) or 1) if f(r["usage"]) else f(r["qty"]) or 1, axis=1)
B["uom"] = B.apply(lambda r: (sap[r["code"]]["sap_uom"] if r["code"] in sap else ("tube" if "DP8710" in r["key"] else "pc")), axis=1)
B["line_cost_thb"] = B["line_cost"].map(f)
roll = B.groupby(["code", "key", "description", "uom"], dropna=False).agg(lines=("row", "count"), qty_per_shipset=("qty_per_shipset", "sum"), cost_thb=("line_cost_thb", "sum")).reset_index()
struct = B.groupby(["assembly", "section"], sort=False).agg(lines=("row", "count"), cost_thb=("line_cost_thb", "sum")).reset_index()
U = D.drop_duplicates(subset=["key", "description"])[["key", "description", "code", "match", "in_sap", "sap_type", "sap_name", "sap_uom", "sheet_uom", "unit_cost_sheet", "sap_price", "price_diff_pct", "in_prod", "prod_uom", "prod_cost", "prod_categ", "name_differs", "candidate_if_no_code"]]
UM = U[U.code == ""]
coded = U[U.code != ""]
summ = [("Workbook", "BOM INSEE REV.0.xlsx (Chindanai, 26 Nov 2026) – cost estimate for INSEE wing set, customer Thai Sky (Vision)"),
        ("Material lines in INSEE (Part Cost)", len(B)), ("Price-list lines in Material Codes", int((D.sheet == "Material Codes").sum())),
        ("Unique materials (both sheets)", len(U)), ("…with SAP code (sheet or via key)", len(coded)),
        ("…in SAP master", int(coded.in_sap.sum())), ("   ZRM", int((coded.sap_type == "ZRM").sum())), ("   ZRMN", int((coded.sap_type == "ZRMN").sum())),
        ("…in production cdrone", int(coded.in_prod.sum())), ("…in SAP but missing from production", int((coded.in_sap & ~coded.in_prod).sum())),
        ("Unique materials without any code", len(UM)), ("…of which a likely SAP candidate exists", int((UM.candidate_if_no_code != "").sum())),
        ("INSEE BoM unique materials", B.drop_duplicates(["key", "description"]).shape[0]), ("…coded and in prod", int(B.drop_duplicates(["key", "description"]).in_prod.sum())),
        ("Sheet price ≠ SAP price (coded)", int((coded.price_diff_pct.fillna(0).abs() > 0.5).sum())),
        ("Embedded MM60 15-10-26 rows vs plan.json", f"{len(M['mm'])} vs {len(sap)}; 0 codes only in workbook; {len(M['only_sap'])} newer in plan.json; price diffs {len(M['pd'])}, name diffs {len(M['nd'])}, UoM diffs {len(M['ud'])}"),
        ("Material cost per shipset (sheet)", "4,775.22 THB + 20% consumables = 5,730.26; total incl. labour 16.33 h + CNC = 10,980.26 THB"),]
with pd.ExcelWriter("compare.xlsx", engine="openpyxl") as w:
    pd.DataFrame(summ, columns=["Item", "Value"]).astype(str).to_excel(w, sheet_name="Summary", index=False)
    struct.to_excel(w, sheet_name="BoM structure", index=False)
    roll.to_excel(w, sheet_name="Materials per shipset", index=False)
    U.to_excel(w, sheet_name="Unique materials", index=False)
    D.to_excel(w, sheet_name="Detail (all lines)", index=False)
    UM.to_excel(w, sheet_name="Unmatched", index=False)
    pd.DataFrame([dict(code=c, workbook_MM60=str(M["mm"][c]), plan_json=str({k: sap[c][k] for k in ("name", "mtyp", "sap_uom", "standard_price")})) for c in M["pd"] + M["nd"] + M["ud"]]).to_excel(w, sheet_name="MM60 vs SAP master", index=False)
    for ws in w.book.worksheets:
        for col in ws.columns: ws.column_dimensions[col[0].column_letter].width = min(60, max(10, max(len(str(c.value or "")) for c in col) + 2))
print(pd.DataFrame(summ).to_string()); print(struct.to_string()); print(roll.to_string())
print(coded[coded.price_diff_pct.fillna(0).abs() > 0.5][["key", "code", "unit_cost_sheet", "sheet_uom", "sap_price", "sap_uom", "price_diff_pct", "in_prod"]].to_string())
print(coded[~coded.in_prod][["key", "code", "sap_name"]].to_string())
