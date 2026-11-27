"""Profile a BoM/part-list workbook and compare rows with SAP master + cdrone prod snapshot. Read-only; usage: compare.py <xlsx>"""
import sys, re, json, collections, unicodedata
import pandas as pd
SRC = sys.argv[1]
CODE_RE = re.compile(r"^\s*(\d{8})(?:\.0)?\s*$")
def norm(s):
    s = unicodedata.normalize("NFKC", str(s or "")).lower()
    return re.sub(r"[^0-9a-z\u0e00-\u0e7f]+", "", s)
sap = json.load(open("/workspace/cobra/cobra-semi-parts/loadtest/plan.json"))["records"]
SAP = {r["default_code"]: r for r in sap}
SAPN = collections.defaultdict(list)
for r in sap: SAPN[norm(r["name"])].append(r["default_code"])
prod = json.load(open("snap_prod.json"))["products"]
PROD = {p["default_code"]: p for p in prod if p["default_code"]}
PRODN = collections.defaultdict(list)
for p in prod: PRODN[norm(p["name"])].append(p["default_code"])
xl = pd.ExcelFile(SRC); profile = []; rows = []
for sh in xl.sheet_names:
    raw = xl.parse(sh, header=None, dtype=object)
    if raw.empty: profile.append(dict(sheet=sh, rows=0)); continue
    # header row = first row among top 30 with >=3 text cells
    hdr = next((i for i in range(min(30, len(raw))) if raw.iloc[i].map(lambda v: isinstance(v, str)).sum() >= 3), 0)
    df = raw.iloc[hdr + 1:].copy(); df.columns = [str(c).strip() if pd.notna(c) else f"col{j}" for j, c in enumerate(raw.iloc[hdr])]
    df = df.dropna(how="all")
    codecols = [c for c in df.columns if df[c].map(lambda v: bool(CODE_RE.match(str(v)))).sum() >= max(3, 0.2 * df[c].notna().sum())]
    pick = lambda *ks: next((c for c in df.columns if any(k in c.lower() for k in ks)), None)
    namec = pick("description", "desc", "name", "material", "รายการ", "ชื่อ"); uomc = pick("uom", "unit", "หน่วย"); qtyc = pick("qty", "quantity", "จำนวน"); pricec = pick("price", "cost", "ราคา")
    profile.append(dict(sheet=sh, header_row=hdr + 1, rows=len(df), columns=" | ".join(map(str, df.columns))[:900], code_cols=", ".join(codecols), name_col=namec, uom_col=uomc, qty_col=qtyc, price_col=pricec))
    for i, r in df.iterrows():
        code = next((CODE_RE.match(str(r[c])).group(1) for c in codecols if CODE_RE.match(str(r[c]))), None)
        name = str(r[namec]) if namec and pd.notna(r[namec]) else ""
        if not code and not name.strip(): continue
        how = "code" if code else ""
        if not code and norm(name):
            cand = SAPN.get(norm(name)) or PRODN.get(norm(name))
            if cand: code, how = cand[0], f"name({len(cand)})"
        s = SAP.get(code); p = PROD.get(code)
        uom = str(r[uomc]) if uomc and pd.notna(r[uomc]) else ""; price = r[pricec] if pricec else None
        try: price = float(price)
        except Exception: price = None
        rows.append(dict(sheet=sh, row=int(i) + 1, code_in_sheet=code if how == "code" else "", name_in_sheet=name, qty=r[qtyc] if qtyc else None, uom_in_sheet=uom, price_in_sheet=price,
            matched_code=code or "", match=how or "none", in_sap=bool(s), sap_type=s and s["mtyp"], sap_name=s and s["name"], sap_uom=s and s["sap_uom"], sap_price=s and s["standard_price"],
            in_prod=bool(p), prod_name=p and p["name"], prod_categ=p and p["categ_id"][1], prod_uom=p and p["uom_id"][1], prod_cost=p and p["standard_price"],
            name_diff=bool(s and name and norm(name) != norm(s["name"])), uom_diff=bool(uom and s and norm(uom) != norm(s["sap_uom"]) and norm(uom) != norm(s["uom"])),
            price_diff_pct=(round(100 * (price - s["standard_price"]) / s["standard_price"], 1) if price and s and s.get("standard_price") else None),
            prod_vs_sap_cost_pct=(round(100 * (p["standard_price"] - s["standard_price"]) / s["standard_price"], 1) if p and s and s.get("standard_price") else None)))
D = pd.DataFrame(rows); P = pd.DataFrame(profile)
json.dump(dict(profile=profile, n=len(D)), open("profile.json", "w"), ensure_ascii=False, default=str, indent=1)
D.to_pickle("detail.pkl"); print(P.to_string()); print(len(D), "rows")
