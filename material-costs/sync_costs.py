#!/usr/bin/env python3
"""Sync Cobra's SAP standard material costs into cdrone Odoo (Odoo 20).

Two modes:
  dry-run  parse the xlsx, diff it against live Odoo, write a run folder with
           dryrun.csv / dryrun.md / plan.json. Read-only.
  apply    re-check the file hash against an approved plan.json, recompute the
           diff live, refuse if it no longer matches the plan, then create the
           prerequisites (categories, units) and create/update products.

Products are matched by default_code (= SAP Material). Products that vanish
from a later file are only flagged (action missing_from_file); nothing is
archived or deleted by this tool.
"""
import argparse, csv, datetime as dt, hashlib, html, json, os, re, sys, time, xmlrpc.client
from collections import Counter

import openpyxl

URL = os.environ.get("ODOO_URL", "https://cdrone.odoo.com")
DB = os.environ.get("ODOO_DB", "cdrone")
USER = os.environ.get("ODOO_USER", "mahisorn_w@cobrainter.com")
READ_METHODS = {"search_read", "read", "search", "search_count", "fields_get"}
WRITE_METHODS = {"create", "write"}  # never unlink

# SAP base unit -> Odoo uom.uom name
UOM_MAP = {"KG": "kg", "M2": "m²", "EA": "Units", "PC": "Units", "M": "m", "L": "L", "ML": "ml",
           "G": "g", "YD": "yd", "LB": "lb", "GAL": "gal (US)",
           "SET": "Set", "PAC": "Pack", "ROL": "Roll", "DR": "Drum", "CAN": "Can", "PAA": "Pair"}
NEW_UOMS = ["Set", "Pack", "Roll", "Drum", "Can", "Pair"]   # stand-alone (own reference)
ACTIVATE_UOMS = ["yd", "lb", "gal (US)"]
ROOT_CATEG = os.environ.get("SYNC_ROOT_CATEG", "Raw Materials")  # parent category for SAP material groups
TEMPLATE_CATEG = "Goods"         # valuation/costing settings copied from this category
MATERIAL_PREFIXES = ("14", "24")  # SAP raw-material number ranges managed by this tool
COST_TOL = 0.005
BATCH = 200

COLS = {"material": "code", "material description": "name", "plnt": "plant", "mtyp": "mtype",
        "matl group": "matl_group", "bun": "uom", "pgr": "purch_group", "typ": "mrp_type",
        "valcl": "val_class", "pr.": "price_control", "price": "price", "crcy": "currency",
        "last chg": "last_change"}


# ---------------------------------------------------------------- Odoo client
class Odoo:
    def __init__(self, allow_write=False, log=None):
        self.key = os.environ.get("COBRA_DRONE_ODOO_API_KEY") or sys.exit("COBRA_DRONE_ODOO_API_KEY not set")
        self.obj = xmlrpc.client.ServerProxy(URL + "/xmlrpc/2/object", allow_none=True)
        self.uid = xmlrpc.client.ServerProxy(URL + "/xmlrpc/2/common").authenticate(DB, USER, self.key, {})
        if not self.uid:
            sys.exit("Odoo authentication failed")
        self.allow_write, self.log = allow_write, log or (lambda m: None)

    def __call__(self, model, method, *args, **kw):
        if method not in READ_METHODS and not (self.allow_write and method in WRITE_METHODS):
            raise PermissionError(f"refusing {model}.{method} (allow_write={self.allow_write})")
        if method in WRITE_METHODS:
            self.log(f"RPC {model}.{method} n={len(args[0]) if args and isinstance(args[0], list) else 1}")
        return self.obj.execute_kw(DB, self.uid, self.key, model, method, list(args), kw)


# ---------------------------------------------------------------- file
def file_sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def clean(s):
    return " ".join(str(s if s is not None else "").split())


def sap_note(r):
    parts = [("MTyp", r.get("mtype")), ("Matl Group", r.get("matl_group")), ("ValCl", r.get("val_class")),
             ("PGr", r.get("purch_group")), ("Typ", r.get("mrp_type")), ("Plant", r.get("plant")),
             ("Price control", r.get("price_control")), ("SAP unit", r.get("uom")), ("Last Chg", r.get("last_change") or "-")]
    return "SAP material master: " + "; ".join(f"{k} {clean(v) or '-'}" for k, v in parts)


def html_text(v):
    return clean(html.unescape(re.sub(r"<[^>]+>", " ", v or "")))


def load_file(path):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    header = [clean(h).lower() for h in next(it)]
    idx = {COLS[h]: i for i, h in enumerate(header) if h in COLS}
    missing = {"code", "name", "uom", "price", "currency"} - set(idx)
    if missing:
        sys.exit(f"missing required columns {sorted(missing)}; header={header}")
    rows = []
    for n, r in enumerate(it, start=2):
        if all(v in (None, "") for v in r):
            continue
        rec = {k: r[i] for k, i in idx.items()}
        code = rec["code"]
        rec["code"] = str(int(code)) if isinstance(code, float) and code.is_integer() else clean(code)
        rec["name"], rec["uom"], rec["currency"] = clean(rec.get("name")), clean(rec.get("uom")).upper(), clean(rec.get("currency")).upper()
        lc = rec.get("last_change")
        rec["last_change"] = lc.date().isoformat() if isinstance(lc, dt.datetime) else clean(lc)
        rec["row"], errs = n, []
        if not rec["code"]: errs.append("blank material code")
        if not rec["name"]: errs.append("blank description")
        if not isinstance(rec["price"], (int, float)) or rec["price"] < 0: errs.append(f"bad price {rec['price']!r}")
        if rec["currency"] != "THB": errs.append(f"non-THB currency {rec['currency']!r}")
        if rec.get("price_control") not in (None, "S"): errs.append(f"price control {rec['price_control']!r} (not S)")
        if rec["uom"] not in UOM_MAP: errs.append(f"unknown SAP unit {rec['uom']!r}")
        rec["errors"] = errs
        rows.append(rec)
    dup = {c for c, k in Counter(r["code"] for r in rows).items() if k > 1}
    for r in rows:
        if r["code"] in dup:
            r["errors"].append("duplicate material code in file")
    return rows, ws.title


# ---------------------------------------------------------------- live state + diff
def categ_name(r):
    return f"{ROOT_CATEG} / {clean(r.get('matl_group')) or 'Unassigned'}"


def read_state(odoo, companies):
    comp = {c["id"]: c["name"] for c in odoo("res.company", "search_read", [], fields=["name"])}
    uoms = {}
    for u in odoo("uom.uom", "search_read", [["active", "in", [True, False]]], fields=["name", "active"]):
        uoms.setdefault(u["name"], u)
    categs = {c["complete_name"]: c["id"] for c in odoo("product.category", "search_read", [], fields=["complete_name"])}
    dom = [["default_code", "!=", False], ["active", "in", [True, False]]]
    prods = {}
    for p in odoo("product.product", "search_read", dom, context={"allowed_company_ids": list(comp)},
                  fields=["default_code", "name", "uom_id", "categ_id", "company_id", "active", "product_tmpl_id", "description"]):
        prods.setdefault(p["default_code"], []).append(p)
    cost = {}
    for cid in companies:
        for p in odoo("product.product", "search_read", dom, fields=["default_code", "standard_price"],
                      context={"allowed_company_ids": [cid]}):
            cost[(p["default_code"], cid)] = p["standard_price"]
    return dict(comp=comp, uoms=uoms, categs=categs, prods=prods, cost=cost)


def build_plan(rows, st, companies):
    out, file_codes = [], set()
    for r in rows:
        file_codes.add(r["code"])
        uom, categ = UOM_MAP.get(r["uom"]), categ_name(r)
        notes = []
        if uom and uom not in st["uoms"]: notes.append(f"needs new UoM '{uom}'")
        elif uom and not st["uoms"][uom]["active"]: notes.append(f"needs UoM '{uom}' activated")
        if categ not in st["categs"]: notes.append(f"needs category '{categ}'")
        base = dict(row=r["row"], code=r["code"], name=r["name"], sap_unit=r["uom"], odoo_uom=uom or "", category=categ,
                    mtype=r.get("mtype"), val_class=r.get("val_class"), last_change=r["last_change"], new_cost=r["price"],
                    currency=r["currency"], notes="; ".join(notes), old_cost="", changes="", company="", product_id="", _rec=r)
        if r["errors"]:
            out.append(dict(base, action="error", changes="; ".join(r["errors"]))); continue
        matches = st["prods"].get(r["code"], [])
        if len(matches) > 1:
            out.append(dict(base, action="error", changes="multiple Odoo products share this code")); continue
        p = matches[0] if matches else None
        if p is None:
            out.append(dict(base, action="create", company=",".join(map(str, companies)), changes="new product + cost")); continue
        if p["company_id"]:
            out.append(dict(base, action="error", product_id=p["id"], changes=f"existing product restricted to {p['company_id'][1]}")); continue
        ch, fields = [], {}
        if p["name"] != r["name"]: ch.append(f"name '{p['name']}' -> '{r['name']}'"); fields["name"] = 1
        if (p["uom_id"] or [0, ""])[1] != uom: ch.append(f"uom {(p['uom_id'] or [0, ''])[1]} -> {uom}"); fields["uom_id"] = 1
        if (p["categ_id"] or [0, ""])[1] != categ: ch.append(f"category {(p['categ_id'] or [0, ''])[1]} -> {categ}"); fields["categ_id"] = 1
        if html_text(p["description"]) != sap_note(r): ch.append("SAP info note"); fields["description"] = 1
        if not p["active"]: ch.append("reactivate (archived in Odoo)"); fields["active"] = 1
        costs = {}
        for cid in companies:
            old = st["cost"].get((r["code"], cid), 0.0)
            if abs(old - r["price"]) > COST_TOL:
                ch.append(f"cost[c{cid}] {old} -> {r['price']}"); costs[cid] = old
        out.append(dict(base, action="update" if ch else "unchanged", company=",".join(map(str, companies)), product_id=p["id"],
                        old_cost=json.dumps({str(c): st["cost"].get((r["code"], c), 0.0) for c in companies}),
                        changes="; ".join(ch), _fields=fields, _costs=costs, _tmpl=p["product_tmpl_id"][0]))
    for code, ps in sorted(st["prods"].items()):
        if code not in file_codes and code.isdigit() and code.startswith(MATERIAL_PREFIXES):
            out.append(dict(row="", code=code, name=ps[0]["name"], action="missing_from_file", product_id=ps[0]["id"],
                            changes="flag only: in Odoo but not in this file (archive needs approval)",
                            sap_unit="", odoo_uom="", category="", mtype="", val_class="", last_change="", new_cost="",
                            currency="", notes="", old_cost="", company=""))
    return out


def plan_key(out):
    return sorted(f"{o['action']}|{o['code']}" for o in out)


# ---------------------------------------------------------------- reports
CSV_COLS = ["action", "company", "code", "name", "sap_unit", "odoo_uom", "category", "mtype", "val_class",
            "old_cost", "new_cost", "currency", "last_change", "changes", "notes", "product_id", "row"]


def write_reports(run_dir, path, sha, sheet, rows, out, st, companies):
    with open(os.path.join(run_dir, "dryrun.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS, extrasaction="ignore"); w.writeheader(); w.writerows(out)
    cnt = Counter(o["action"] for o in out)
    need_uom = sorted({u for u in NEW_UOMS if u not in st["uoms"]})
    need_act = sorted({u for u in ACTIVATE_UOMS if u in st["uoms"] and not st["uoms"][u]["active"]})
    need_cat = sorted({o["category"] for o in out if "needs category" in o.get("notes", "")})
    if need_cat and ROOT_CATEG not in st["categs"]:
        need_cat = [ROOT_CATEG] + need_cat
    errs = [o for o in out if o["action"] == "error"]
    plan = dict(file=os.path.basename(path), sha256=sha, sheet=sheet, root_categ=ROOT_CATEG, rows=len(rows), companies=companies,
                created_at=dt.datetime.now().isoformat(timespec="seconds"), counts=dict(cnt),
                prereqs=dict(categories=need_cat, new_uoms=need_uom, activate_uoms=need_act), keys=plan_key(out))
    json.dump(plan, open(os.path.join(run_dir, "plan.json"), "w"), indent=1, ensure_ascii=False)
    md = [f"# cdrone material cost sync: DRY RUN {dt.datetime.now():%Y-%m-%d %H:%M} (UTC+7)", "",
          f"- File `{os.path.basename(path)}` (sheet `{sheet}`), sha256 `{sha[:12]}`, {len(rows)} data rows",
          f"- Odoo {URL} db `{DB}`; cost goes to company " + ", ".join(f"{c} {st['comp'].get(c)}" for c in companies),
          "- Read-only: nothing written.", "", "## Counts", "", "| action | rows |", "|---|---|"]
    md += [f"| {k} | {v} |" for k, v in sorted(cnt.items())]
    md += ["", "## Prerequisites apply would create", "",
           f"- Categories ({len(need_cat)}): " + (", ".join(need_cat) if len(need_cat) <= 8 else f"{need_cat[0]}, {need_cat[1]} … {need_cat[-1]}"),
           f"- New UoMs: {', '.join(need_uom) or 'none'}", f"- UoMs to activate: {', '.join(need_act) or 'none'}",
           "", f"## Errors ({len(errs)})", ""] + [f"- row {e['row']} `{e['code']}`: {e['changes']}" for e in errs[:100]]
    upd = [o for o in out if o["action"] == "update"]
    md += ["", f"## Updates ({len(upd)}, first 50)", ""] + [f"- `{o['code']}` {o['name']}: {o['changes']}" for o in upd[:50]]
    miss = [o for o in out if o["action"] == "missing_from_file"]
    md += ["", f"## Missing from file ({len(miss)}, flag only)", ""] + [f"- `{o['code']}` {o['name']}" for o in miss[:100]]
    md += ["", f"Approve, then run: `sync_costs.py apply {os.path.basename(path)} --plan {os.path.join(run_dir, 'plan.json')}`"]
    open(os.path.join(run_dir, "dryrun.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    return plan


# ---------------------------------------------------------------- apply
def ensure_prereqs(odoo, out, companies, log):
    created = {"categories": [], "uoms": [], "activated_uoms": []}
    # units
    uoms = {}
    for u in odoo("uom.uom", "search_read", [["active", "in", [True, False]]], fields=["name", "active"]):
        uoms.setdefault(u["name"], u)
    for name in NEW_UOMS:
        if name not in uoms:
            uid = odoo("uom.uom", "create", [{"name": name, "relative_factor": 1.0, "relative_uom_id": False}])[0]
            created["uoms"].append({"id": uid, "name": name}); log(f"created uom {name} id={uid}")
    for name in ACTIVATE_UOMS:
        if name in uoms and not uoms[name]["active"]:
            odoo("uom.uom", "write", [uoms[name]["id"]], {"active": True})
            created["activated_uoms"].append({"id": uoms[name]["id"], "name": name}); log(f"activated uom {name}")
    # categories, with costing/valuation copied per company from TEMPLATE_CATEG
    all_cids = [c["id"] for c in odoo("res.company", "search_read", [], fields=["id"])]
    fc = odoo("product.category", "fields_get", attributes=["company_dependent"])
    props = [k for k, v in fc.items() if v.get("company_dependent")]
    tmpl_id = odoo("product.category", "search", [["complete_name", "=", TEMPLATE_CATEG]])
    if not tmpl_id:
        raise RuntimeError(f"template category {TEMPLATE_CATEG!r} not found")
    ref = {cid: odoo("product.category", "read", tmpl_id, props, context={"allowed_company_ids": [cid]})[0] for cid in all_cids}
    categs = {c["complete_name"]: c["id"] for c in odoo("product.category", "search_read", [], fields=["complete_name"])}
    wanted = sorted({o["category"] for o in out if o["action"] in ("create", "update")})

    def ensure(name, parent_id):
        if name in categs:
            return categs[name], False
        cid_ = odoo("product.category", "create", [{"name": name.split(" / ")[-1], "parent_id": parent_id}])[0]
        categs[name] = cid_; created["categories"].append({"id": cid_, "name": name}); log(f"created category {name} id={cid_}")
        return cid_, True

    new_ids = []
    root, is_new = ensure(ROOT_CATEG, False)
    if is_new: new_ids.append(root)
    for name in wanted:
        if name != ROOT_CATEG:
            i, is_new = ensure(name, root)
            if is_new: new_ids.append(i)
    # copy settings onto every category this tool owns (idempotent: write only differences)
    owned = [categs[ROOT_CATEG]] + [categs[n] for n in wanted]
    for cid in all_cids:
        cur = odoo("product.category", "read", owned, props, context={"allowed_company_ids": [cid]})
        tvals = {k: (v[0] if isinstance(v, list) else v) for k, v in ref[cid].items() if k != "id"}
        groups = {}
        for c in cur:
            diff = {k: tv for k, tv in tvals.items() if (c[k][0] if isinstance(c[k], list) else c[k]) != tv}
            if diff:
                groups.setdefault(json.dumps(diff, sort_keys=True), []).append(c["id"])
        for d, ids in groups.items():
            odoo("product.category", "write", ids, json.loads(d), context={"allowed_company_ids": [cid]})
            log(f"company {cid}: set category settings on {len(ids)} categories: {sorted(json.loads(d))}")
    return created


def apply(args):
    run_dir = os.path.dirname(os.path.abspath(args.plan))
    logf = open(os.path.join(run_dir, "apply.log"), "a", encoding="utf-8")

    def log(m):
        line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {m}"; print(line); logf.write(line + "\n"); logf.flush()

    plan = json.load(open(args.plan))
    sha = file_sha(args.file)
    if sha != plan["sha256"]:
        sys.exit(f"file hash {sha[:12]} does not match approved plan {plan['sha256'][:12]}; run dry-run again")
    if plan.get("root_categ", ROOT_CATEG) != ROOT_CATEG:
        sys.exit(f"plan used root category {plan['root_categ']!r} but SYNC_ROOT_CATEG is {ROOT_CATEG!r}")
    companies = plan["companies"]
    rows, _ = load_file(args.file)
    ro = Odoo()
    out = build_plan(rows, read_state(ro, companies), companies)
    if plan_key(out) != plan["keys"]:
        sys.exit("live Odoo state changed since the dry run (plan no longer matches); run dry-run again")
    if any(o["action"] == "error" for o in out) and not args.skip_errors:
        sys.exit("plan has error rows; fix the file or pass --skip-errors")
    odoo = Odoo(allow_write=True, log=log)
    ids_path = os.path.join(run_dir, "created-ids.jsonl")
    idsf = open(ids_path, "a", encoding="utf-8")
    log(f"apply start file={plan['file']} sha={sha[:12]} companies={companies} counts={dict(Counter(o['action'] for o in out))}")
    try:
        pre = ensure_prereqs(odoo, out, companies, log)
        idsf.write(json.dumps({"prereqs": pre}, ensure_ascii=False) + "\n"); idsf.flush()
        st = read_state(ro, companies)
        uom_id = {n: u["id"] for n, u in st["uoms"].items()}
        main_c = companies[0]
        ctx = {"allowed_company_ids": [main_c]}

        def vals(o):
            r = o["_rec"]
            return {"name": r["name"], "default_code": r["code"], "type": "consu", "is_storable": True,
                    "purchase_ok": True, "sale_ok": False, "company_id": False, "uom_id": uom_id[UOM_MAP[r["uom"]]],
                    "categ_id": st["categs"][o["category"]], "description": f"<p>{html.escape(sap_note(r))}</p>"}

        creates = [o for o in out if o["action"] == "create"]
        for i in range(0, len(creates), BATCH):
            chunk = creates[i:i + BATCH]
            tids = odoo("product.template", "create", [dict(vals(o), standard_price=float(o["_rec"]["price"])) for o in chunk], context=ctx)
            for o, t in zip(chunk, tids):
                idsf.write(json.dumps({"action": "create", "code": o["code"], "template_id": t}) + "\n")
            idsf.flush()
            for extra in companies[1:]:
                pp = odoo("product.product", "search_read", [["product_tmpl_id", "in", tids]], fields=["default_code"])
                price = {o["code"]: float(o["_rec"]["price"]) for o in chunk}
                for p in pp:
                    odoo("product.product", "write", [p["id"]], {"standard_price": price[p["default_code"]]}, context={"allowed_company_ids": [extra]})
            if i == 0:  # verify the first batch landed as intended before continuing
                price = {o["code"]: float(o["_rec"]["price"]) for o in chunk}
                for cid in [c for c in st["comp"]]:
                    got = odoo("product.product", "search_read", [["product_tmpl_id", "in", tids]],
                               fields=["default_code", "standard_price"], context={"allowed_company_ids": [cid]})
                    bad = [g["default_code"] for g in got if abs(g["standard_price"] - (price[g["default_code"]] if cid in companies else 0.0)) > COST_TOL]
                    if len(got) != len(chunk) or bad:
                        raise RuntimeError(f"first-batch check failed for company {cid}: {len(got)} variants, cost mismatch {bad[:5]}")
                log("first batch verified: cost on target company, 0 elsewhere")
            log(f"created templates {i + 1}-{i + len(chunk)} of {len(creates)}")
            time.sleep(0.2)
        for o in (o for o in out if o["action"] == "update"):
            v = vals(o)
            tv = {k: v[k] for k in o["_fields"] if k in v}
            if "active" in o["_fields"]: tv["active"] = True
            if tv:
                odoo("product.template", "write", [o["_tmpl"]], tv, context=ctx)
            for cid in o["_costs"]:
                odoo("product.product", "write", [o["product_id"]], {"standard_price": float(o["_rec"]["price"])}, context={"allowed_company_ids": [cid]})
            idsf.write(json.dumps({"action": "update", "code": o["code"], "product_id": o["product_id"], "changes": o["changes"]}, ensure_ascii=False) + "\n")
            log(f"updated {o['code']}: {o['changes']}")
    except Exception as e:
        log(f"STOPPED with error: {e!r}. Nothing was deleted; see {ids_path} for what was created.")
        raise
    log("apply done")


# ---------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)
    d = sub.add_parser("dry-run", help="diff file vs live Odoo (read-only)")
    d.add_argument("file")
    d.add_argument("--company", type=int, action="append", help="company id(s) receiving the cost; first is primary (default 1)")
    d.add_argument("--runs-dir", default=os.environ.get("SYNC_RUNS_DIR", "runs"))
    a = sub.add_parser("apply", help="apply an approved dry-run plan")
    a.add_argument("file")
    a.add_argument("--plan", required=True, help="plan.json from the approved dry run")
    a.add_argument("--skip-errors", action="store_true", help="apply valid rows even if some rows are errors")
    args = ap.parse_args()
    if args.mode == "apply":
        return apply(args)
    companies = args.company or [1]
    run_dir = os.path.join(args.runs_dir, dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    os.makedirs(run_dir, exist_ok=True)
    rows, sheet = load_file(args.file)
    odoo = Odoo()
    st = read_state(odoo, companies)
    out = build_plan(rows, st, companies)
    plan = write_reports(run_dir, args.file, file_sha(args.file), sheet, rows, out, st, companies)
    print(json.dumps({"run_dir": run_dir, "counts": plan["counts"], "prereqs": {k: len(v) for k, v in plan["prereqs"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
