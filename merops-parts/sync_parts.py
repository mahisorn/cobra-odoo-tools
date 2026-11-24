#!/usr/bin/env python3
"""Sync a Merops part list (Flatpack BOM xlsx) into cdrone Odoo products (Odoo 20).

Modes:
  dry-run  parse the current BOM file (+ optional older files that carry the
           in-cell images / dimensions), diff against live Odoo, write a run
           folder with dryrun.md / dryrun.csv / plan.json. Read-only.
  apply    re-check every input file's sha256 against an approved plan.json,
           rebuild the diff live and refuse unless it is identical to the plan,
           then create/update products. Never deletes or archives anything.

Rules (Chang, t109u):
  - Internal Reference = Merops part number with revision (P03042-04).
  - Same full code -> update that product. New -XX revision -> new product,
    the old revision is kept untouched.
  - Products are shared (company_id empty), category Goods / Merops / RJ2.
  - No prices. No kit / BoM (decided later).
  - Category properties (Weight (g), Dimensions (mm), ...) are written only if
    their definitions already exist on the category; otherwise listed as pending.
"""
import argparse, base64, csv, datetime as dt, hashlib, io, json, os, re, sys, xmlrpc.client, zipfile
from collections import Counter, defaultdict
from posixpath import normpath, dirname, join as pjoin

from lxml import etree

URL = os.environ.get("ODOO_URL", "https://cdrone.odoo.com")
DB = os.environ.get("ODOO_DB", "cdrone")
USER = os.environ.get("ODOO_USER", "mahisorn_w@cobrainter.com")
READ_METHODS = {"search_read", "read", "search", "search_count", "fields_get"}
WRITE_METHODS = {"create", "write"}  # never unlink
HERE = os.path.dirname(os.path.abspath(__file__))
M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"
RD = "{http://schemas.microsoft.com/office/spreadsheetml/2017/richdata}"
CODE_RE = re.compile(r"^[A-Z]\d{5}(-\d{2})?$")

# header text (normalised, lower) -> field. First occurrence wins.
HEADERS = {"part no. latest": "code", "item name": "name", "qty": "qty", "category": "category",
           "material": "material", "tech.": "tech", "dimension(mm)": "dimension", "volume": "volume",
           "weight (g)": "weight", "remark change from bom#1=>2": "remark", "group description": "group",
           "status": "status", "suppliers 1": "supplier", "remark": "remark2", "rev.": "rev_class",
           "change": "change", "no.": "no"}


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
            self.log(f"RPC {model}.{method}")
        return self.obj.execute_kw(DB, self.uid, self.key, model, method, list(args), kw)


# ---------------------------------------------------------------- xlsx reading (streaming, handles in-cell images)
def clean(v):
    if v is None: return ""
    if isinstance(v, float) and v.is_integer(): v = int(v)
    return " ".join(str(v).split())


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def col_of(ref):
    return re.match(r"[A-Z]+", ref).group(0)


class Workbook:
    def __init__(self, path):
        self.path, self.z = path, zipfile.ZipFile(path)
        names = set(self.z.namelist())
        self.ss = []
        if "xl/sharedStrings.xml" in names:
            for si in etree.fromstring(self.z.read("xl/sharedStrings.xml")).findall(M + "si"):
                self.ss.append("".join(t.text or "" for t in si.iter(M + "t")))
        wb = etree.fromstring(self.z.read("xl/workbook.xml"))
        rels = {e.get("Id"): e.get("Target") for e in etree.fromstring(self.z.read("xl/_rels/workbook.xml.rels"))}
        self.sheets = []
        for s in wb.iter(M + "sheet"):
            t = rels[s.get(R + "id")]
            t = t.lstrip("/") if t.startswith("/") else normpath(pjoin("xl", t))
            self.sheets.append((s.get("name"), t))
        self.images = self._rich_images(names)

    def _rels(self, part):
        p = pjoin(dirname(part), "_rels", part.rsplit("/", 1)[1] + ".rels")
        if p not in self.z.namelist(): return {}
        return {e.get("Id"): normpath(pjoin(dirname(part), e.get("Target"))) for e in etree.fromstring(self.z.read(p))}

    def _rich_images(self, names):
        """vm index (1-based, as on <c vm=..>) -> media path, for Excel 'Place in Cell' pictures."""
        need = ["xl/metadata.xml", "xl/richData/rdrichvalue.xml", "xl/richData/richValueRel.xml"]
        if not all(n in names for n in need): return {}
        rv = [int(r.findall(RD + "v")[0].text) for r in etree.fromstring(self.z.read(need[1])).findall(RD + "rv")]
        relids = [e.get(R + "id") for e in etree.fromstring(self.z.read(need[2]))]
        rmap = self._rels(need[2])
        md = etree.fromstring(self.z.read(need[0]))
        fm = [int(x.get("i")) for x in md.iter(RD + "rvb")]
        vmb = [int(rc.get("v")) for bk in md.find(M + "valueMetadata") for rc in bk.findall(M + "rc")]
        return {i + 1: rmap[relids[rv[fm[b]]]] for i, b in enumerate(vmb)}

    def iter_rows(self, part):
        for _, el in etree.iterparse(self.z.open(part), tag=M + "row"):
            r, cells = int(el.get("r")), {}
            for c in el.findall(M + "c"):
                v = c.find(M + "v"); val = v.text if v is not None else None
                if c.get("t") == "s" and val is not None: val = self.ss[int(val)]
                elif c.get("t") == "inlineStr": val = "".join(t.text or "" for t in c.iter(M + "t"))
                elif c.get("t") in (None, "n") and val is not None:
                    try: val = float(val)
                    except ValueError: pass
                if c.get("vm") and int(c.get("vm")) in self.images:
                    cells[col_of(c.get("r")) + "#img"] = self.images[int(c.get("vm"))]
                if val is not None: cells[col_of(c.get("r"))] = val
            el.clear()
            yield r, cells

    def find_bom_sheet(self):
        for name, part in self.sheets:
            for r, cells in self.iter_rows(part):
                if any(clean(v).lower() == "part no. latest" for v in cells.values()):
                    return name, part, r, cells
                if r > 6: break
        sys.exit(f"{self.path}: no sheet with a 'Part No. latest' header")

    def read_parts(self):
        name, part, hrow, hcells = self.find_bom_sheet()
        colmap = {}
        for c, v in sorted(hcells.items(), key=lambda kv: (len(kv[0]), kv[0])):
            f = HEADERS.get(clean(v).lower())
            if f and f not in colmap.values(): colmap[c] = f
        code_col = next(c for c, f in colmap.items() if f == "code")
        img_cols = set()
        rows = []
        for r, cells in self.iter_rows(part):
            if r <= hrow or not cells: continue
            rec = {f: cells.get(c) for c, f in colmap.items()}
            rec["row"] = r
            imgs = [v for k, v in cells.items() if k.endswith("#img")]
            img_cols |= {k for k in cells if k.endswith("#img")}
            rec["image"] = imgs[0] if imgs else None
            if not any(clean(v) for k, v in rec.items() if k not in ("row", "image")) and not rec["image"]: continue
            rows.append(rec)
        return dict(sheet=name, header_row=hrow, columns=colmap, rows=rows, image_cols=sorted(img_cols))

    def media(self, path):
        return self.z.read(path)


# ---------------------------------------------------------------- normalisation
def num(v):
    return v if isinstance(v, (int, float)) else None


def parse_tech(tech, remark2):
    t = clean(tech); out = {}
    procs = [p for p in ["MJF", "SLS", "CNC", "FDM", "Blow Molding"] if re.search(rf"\b{p}\b", t, re.I)]
    if procs: out["Process"] = " / ".join(procs)
    m = re.search(r"(?:T\s*=\s*|THK\s*:?\s*)(\d+(?:\.\d+)?)\s*(?:mm)?", t + " " + clean(remark2), re.I)
    if m: out["Thickness (mm)"] = float(m.group(1))
    vp = re.search(r"\b(\d{4}N\d{2,3}|\d{4}T\d{3})\b", t)
    if vp: out["_vendor_pn"] = vp.group(1)
    return out


def properties_for(rec, code):
    p = {}
    if num(rec.get("weight")) is not None: p["Weight (g)"] = round(rec["weight"], 3)
    if clean(rec.get("dimension")): p["Dimensions (mm)"] = clean(rec["dimension"])
    if num(rec.get("volume")) is not None: p["Volume (mm3)"] = round(rec["volume"], 2)
    mat = clean(rec.get("material"))
    if mat and mat.upper() not in ("N/A", "NOT SPECIFIED"): p["Material"] = mat
    p.update(parse_tech(rec.get("tech"), rec.get("remark2")))
    g = clean(rec.get("group"))
    if re.fullmatch(r"\d+\s*[Xx]\s*\d+", g): p["Blank size (mm)"] = re.sub(r"\s*[Xx]\s*", " x ", g)
    base, _, rev = code.partition("-")
    p["Base PN"] = base
    if rev: p["Revision"] = rev
    return p


def description_for(rec):
    bits = []
    for k, lab in [("remark", "BOM change remark"), ("remark2", "Remark"), ("group", "Group"), ("category", "Merops category")]:
        v = clean(rec.get(k))
        if v and not (k == "group" and re.fullmatch(r"\d+\s*[Xx]\s*\d+", v)): bits.append(f"{lab}: {v}")
    return "Merops RJ2B Flatpack BOM. " + "; ".join(bits) if bits else "Merops RJ2B Flatpack BOM."


def html_text(v):
    import html as h
    return clean(h.unescape(re.sub(r"<[^>]+>", " ", v or "")))


def load_inputs(bom_path, extra_paths, cfg):
    cur = Workbook(bom_path).read_parts()
    extras = []
    for p in extra_paths:
        wb = Workbook(p); d = wb.read_parts(); d["wb"] = wb; d["path"] = p; extras.append(d)
    cur_wb = Workbook(bom_path)
    parts, issues = [], []
    by_code_extra = defaultdict(list)
    for d in extras:
        for r in d["rows"]:
            c = clean(r.get("code"))
            if c: by_code_extra[c].append((d, r))
    seen = Counter(clean(r.get("code")) for r in cur["rows"])
    for r in cur["rows"]:
        code = clean(r.get("code"))
        if not code:
            issues.append(f"row {r['row']}: blank part number ({clean(r.get('name'))})"); continue
        if not CODE_RE.match(code):
            issues.append(f"row {r['row']}: '{code}' is not a part number ({clean(r.get('name'))}); skipped"); continue
        rec = dict(r)
        src_img = None
        if r.get("image"): src_img = (bom_path, r["image"], cur_wb)
        for d, er in by_code_extra.get(code, []):   # fill gaps from older files (same full code only)
            for k in ("dimension", "volume", "weight", "material", "tech", "group"):
                if clean(rec.get(k)) == "" and clean(er.get(k)) != "": rec[k] = er[k]; rec.setdefault("_filled", []).append(k)
            if not src_img and er.get("image"): src_img = (d["path"], er["image"], d["wb"])
        img = None
        if src_img:
            b = src_img[2].media(src_img[1])
            img = dict(source=os.path.basename(src_img[0]), member=src_img[1], sha256=hashlib.sha256(b).hexdigest(), bytes=b)
        rec.update(code=code, name=clean(r.get("name")), qty=num(r.get("qty")), img=img, dup=seen[code] > 1)
        parts.append(rec)
    cur_codes = {p["code"] for p in parts}
    for code, why in (cfg.get("include_from_older") or {}).items():   # rows deliberately taken from an older file
        if code in cur_codes: continue
        hit = by_code_extra.get(code)
        if not hit:
            issues.append(f"{code}: listed in include_from_older but not found in any older file"); continue
        d, er = hit[0]
        b = d["wb"].media(er["image"]) if er.get("image") else None
        img = dict(source=os.path.basename(d["path"]), member=er["image"], sha256=hashlib.sha256(b).hexdigest(), bytes=b) if b else None
        rec = dict(er, code=code, name=clean(er.get("name")), qty=num(er.get("qty")), img=img, dup=False, _from_older=why)
        parts.append(rec); cur_codes.add(code)
    removed = []
    for d in extras:
        for r in d["rows"]:
            c = clean(r.get("code"))
            if CODE_RE.match(c or "") and c not in cur_codes:
                removed.append(f"{c} ({clean(r.get('name'))}) is in {os.path.basename(d['path'])} but not in the current file")
    return cur, extras, parts, issues, sorted(set(removed))


# ---------------------------------------------------------------- live state + diff
def img_same(b64_existing, new_bytes):
    if isinstance(b64_existing, dict): b64_existing = b64_existing.get("content")   # Odoo 20 RPC returns {content, size}
    if not b64_existing: return False
    old = base64.b64decode(b64_existing)
    if hashlib.sha256(old).digest() == hashlib.sha256(new_bytes).digest(): return True
    try:
        from PIL import Image, ImageChops, ImageStat
        a, b = Image.open(io.BytesIO(old)).convert("RGB"), Image.open(io.BytesIO(new_bytes)).convert("RGB")
        if a.size != b.size: return False
        return max(ImageStat.Stat(ImageChops.difference(a, b)).mean) < 2.0   # Odoo may re-encode
    except Exception:
        return False


def read_state(odoo, parts, cfg):
    # complete_name '=' search is unreliable on this db; match the leaf name, then the full path in Python
    categ = [c for c in odoo("product.category", "search_read", [["name", "=", cfg["category"].split(" / ")[-1]]],
                             fields=["id", "complete_name", "product_properties_definition"]) if c["complete_name"] == cfg["category"]]
    uoms = {u["name"]: u for u in odoo("uom.uom", "search_read", [["active", "in", [True, False]]],
                                       fields=["name", "active", "parent_path"])}
    codes = sorted({p["code"] for p in parts})
    bases = sorted({p["code"].split("-")[0] for p in parts})
    legacy = sorted({v["default_code"] for v in cfg["legacy_products"].values()})
    flds = ["default_code", "name", "uom_id", "categ_id", "company_id", "active", "write_date", "description", "type", "is_storable",
            "weight", "product_properties"]
    ctx = {"active_test": False}
    tmpls = odoo("product.template", "search_read",
                 ["|", "|", ["default_code", "in", codes + legacy], ["default_code", "=like", "P0%"], ["default_code", "in", bases]],
                 fields=flds, context=ctx)
    by_code = defaultdict(list)
    for t in tmpls: by_code[t["default_code"]].append(t)
    by_base = defaultdict(list)
    for t in tmpls:
        b = (t["default_code"] or "").split("-")[0]
        by_base[b].append(t)
    moves = {}
    if tmpls:
        ids = [t["id"] for t in tmpls]
        for m in odoo("stock.move", "search_read", [["product_id.product_tmpl_id", "in", ids]], fields=["product_id"], context=ctx):
            moves[m["product_id"][0]] = moves.get(m["product_id"][0], 0) + 1
    return dict(categ=categ[0] if categ else None, uoms=uoms, by_code=by_code, by_base=by_base, tmpls={t["id"]: t for t in tmpls}, moves=moves)


def m2o(v): return (v or [0, ""])[1]


def build_plan(parts, st, cfg):
    out = []
    cat = st["categ"]
    prop_defs = {d.get("string"): d.get("name") for d in (cat or {}).get("product_properties_definition") or []}
    for p in parts:
        code = p["code"]
        uom = cfg["uom_overrides"].get(code, cfg["default_uom"])
        props = properties_for(p, code)
        vendor_pn = props.pop("_vendor_pn", None)
        pending = [k for k in props if k not in prop_defs]
        notes = []
        if cfg["flags"].get(code): notes.append(cfg["flags"][code])
        if clean(p.get("remark2")).find("NOT TO INCLUDE") >= 0: notes.append("Merops: not included in the 2,000 flatpack order")
        if vendor_pn: notes.append(f"vendor PN {vendor_pn}")
        if p.get("_filled"): notes.append("from older file: " + ",".join(p["_filled"]))
        if p.get("_from_older"): notes.append("row from older file: " + p["_from_older"])
        if code in (cfg.get("name_overrides") or {}):
            notes.append(f"name override (file: '{p['name']}')"); p = dict(p, name=cfg["name_overrides"][code])
        if p["qty"] in (None, 0): notes.append(f"qty {p['qty']!r}")
        if uom not in st["uoms"]: notes.append(f"UoM '{uom}' missing in Odoo")
        elif not st["uoms"][uom]["active"]: notes.append(f"UoM '{uom}' archived")
        weight_kg = round(props["Weight (g)"] / 1000.0, 2) if "Weight (g)" in props else None   # Odoo Stock Weight = 2 dp (rounding accepted)
        prop_vals = {prop_defs[k]: v for k, v in props.items() if k in prop_defs}
        vals = dict(name=p["name"], default_code=code, categ_id=cat["id"] if cat else None, uom=uom, company_id=False,
                    type="consu", is_storable=True, sale_ok=True, purchase_ok=True, description=description_for(p))
        if weight_kg: vals["weight"] = weight_kg
        if prop_vals: vals["product_properties"] = prop_vals
        base = dict(row=p["row"], code=code, name=p["name"], qty=p["qty"], uom=uom, category=cfg["category"], company="shared",
                    image="yes" if p["img"] else "no", image_sha=(p["img"] or {}).get("sha256", ""), image_src=(p["img"] or {}).get("member", ""),
                    properties=props, properties_pending=pending, notes="; ".join(notes), product_id="", changes="", write_date="")
        if p["dup"]: out.append(dict(base, action="error", changes="duplicate part number in file")); continue
        if p.get("category") in cfg["skip_categories"]:
            out.append(dict(base, action="skip", changes=f"category '{p.get('category')}' not imported as a product")); continue
        if not cat: out.append(dict(base, action="error", changes=f"category '{cfg['category']}' not found")); continue
        hits = st["by_code"].get(code, [])
        legacy = cfg["legacy_products"].get(code)
        if len(hits) > 1:
            out.append(dict(base, action="error", changes="several Odoo products share this code")); continue
        t, adopt = (hits[0] if hits else None), False
        if not t and legacy:
            lt = st["by_code"].get(legacy["default_code"], [])
            if legacy["action"] == "hold":
                out.append(dict(base, action="hold", product_id=lt[0]["id"] if lt else "",
                                changes=f"existing {legacy['default_code']}: {legacy.get('reason','')}")); continue
            if lt: t, adopt = lt[0], True
        if t is None:
            older = [x["default_code"] for x in st["by_base"].get(code.split("-")[0], []) if x["default_code"] != code and CODE_RE.match(x["default_code"] or "")]
            ch = "new product" + (f"; new revision, keeps {', '.join(older)}" if older else "")
            out.append(dict(base, action="create", changes=ch, _vals=vals)); continue
        if t["company_id"]: notes.append(f"product restricted to {m2o(t['company_id'])} -> shared")
        ch, wv = [], {}
        if adopt: ch.append(f"default_code {t['default_code']} -> {code} (adopt existing)"); wv["default_code"] = code
        if t["name"] != p["name"]: ch.append(f"name '{t['name']}' -> '{p['name']}'"); wv["name"] = p["name"]
        if m2o(t["categ_id"]) != cfg["category"]: ch.append(f"category {m2o(t['categ_id'])} -> {cfg['category']}"); wv["categ_id"] = cat["id"]
        if m2o(t["uom_id"]) != uom:
            if st["moves"].get(t["id"]): out.append(dict(base, action="error", product_id=t["id"], changes=f"uom {m2o(t['uom_id'])} -> {uom} but product has stock moves")); continue
            ch.append(f"uom {m2o(t['uom_id'])} -> {uom}"); wv["uom_id"] = uom
        if t["company_id"]: ch.append("company -> shared"); wv["company_id"] = False
        if not t["active"]: ch.append("reactivate"); wv["active"] = True
        if weight_kg and abs((t.get("weight") or 0) - weight_kg) > 1e-9: ch.append(f"weight {t.get('weight') or 0} -> {weight_kg} kg"); wv["weight"] = weight_kg
        have = {d["name"]: d.get("value") for d in (t.get("product_properties") or []) if isinstance(d, dict)} if m2o(t["categ_id"]) == cfg["category"] else {}
        pdiff = {k: v for k, v in prop_vals.items() if not (have.get(k) == v or (isinstance(v, float) and isinstance(have.get(k), (int, float)) and abs(have[k] - v) < 1e-6))}
        if pdiff: ch.append("properties " + ",".join(sorted(pdiff))); wv["product_properties"] = prop_vals
        if "product_properties" in wv or "categ_id" in wv: wv["categ_id"] = cat["id"]   # properties need categ in the same write
        if html_text(t["description"]) != vals["description"] and not adopt or (adopt and not html_text(t["description"])):
            if html_text(t["description"]) != vals["description"]: ch.append("description"); wv["description"] = vals["description"]
        out.append(dict(base, action="update" if ch or p["img"] else "unchanged", product_id=t["id"], write_date=t["write_date"],
                        changes="; ".join(ch), notes="; ".join(notes), _write=wv, _check_img=bool(p["img"])))
    return out


def resolve_images(odoo, out):
    ids = [o["product_id"] for o in out if o.get("_check_img")]
    cur = {r["id"]: r["image_1920"] for r in odoo("product.template", "read", ids, ["image_1920"])} if ids else {}
    return cur


# ---------------------------------------------------------------- reports
CSV_COLS = ["action", "code", "name", "qty", "uom", "category", "company", "image", "changes", "notes",
            "properties_pending", "properties", "product_id", "row"]


def finalize(out, parts_by_code, cur_imgs):
    for o in out:
        if o.get("_check_img"):
            same = img_same(cur_imgs.get(o["product_id"]), parts_by_code[o["code"]]["img"]["bytes"])
            if not same:
                o["changes"] = "; ".join(x for x in [o["changes"], "image"] if x)
            o["_img_write"] = not same
            if o["action"] == "update" and not o["changes"]: o["action"] = "unchanged"
    return out


def plan_fingerprint(out):
    return sorted(f"{o['action']}|{o['code']}|{o['changes']}|{o.get('image_sha','')}" for o in out)


def write_reports(run_dir, inputs, cur, extras, out, issues, removed, st, cfg):
    cnt = Counter(o["action"] for o in out)
    for o in out:
        o_csv = dict(o, properties=json.dumps(o["properties"], ensure_ascii=False), properties_pending=",".join(o["properties_pending"]))
        o["_csv"] = o_csv
    with open(os.path.join(run_dir, "dryrun.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS, extrasaction="ignore"); w.writeheader(); w.writerows(o["_csv"] for o in out)
    cat = st["categ"]
    defs = [d.get("string") for d in (cat or {}).get("product_properties_definition") or []]
    missing_defs = [p for p in cfg["properties"] if p not in defs]
    imgs = Counter(o["image"] for o in out if o["action"] in ("create", "update", "unchanged"))
    uom_c = Counter(o["uom"] for o in out if o["action"] in ("create", "update"))
    L = [f"# Merops parts sync: dry run {os.path.basename(run_dir)} (Asia/Bangkok)", "",
         "Read-only against cdrone. Nothing was written.", "",
         "## Inputs", ""]
    for role, p in inputs: L.append(f"- {role}: `{os.path.basename(p)}` sha256 `{sha(p)[:16]}…`")
    L += [f"- Current sheet `{cur['sheet']}`, header row {cur['header_row']}, {len(cur['rows'])} data rows, in-cell images: {'yes' if cur['image_cols'] else 'none'}"]
    for d in extras: L.append(f"- Older file `{os.path.basename(d['path'])}` sheet `{d['sheet']}`: {len(d['rows'])} rows, images from column(s) {', '.join(c.replace('#img','') for c in d['image_cols']) or '-'} (used for images/dimensions/weight only, same full code)")
    L += ["", "## Counts", "", "| action | count |", "|---|---|"] + [f"| {k} | {v} |" for k, v in sorted(cnt.items())]
    L += ["", f"Images on products to write: yes {imgs.get('yes',0)} / no {imgs.get('no',0)}. UoM on create/update: " + ", ".join(f"{k} {v}" for k, v in sorted(uom_c.items())),
          f"Target: category `{cfg['category']}` (id {cat['id'] if cat else 'MISSING'}), company shared (empty), type Goods, track inventory on, no cost/price.", ""]
    L += ["## Config changes that must exist first (need Chang's approval; this tool does not create them)", ""]
    if missing_defs: L.append(f"- Property definitions on `{cfg['category']}`: " + ", ".join(missing_defs) + ". Until they exist, apply skips property values (listed per product below).")
    else: L.append("- none")
    L += ["", "## Existing products (legacy Cobra codes)", ""]
    for o in out:
        if o["code"] in cfg["legacy_products"]:
            L.append(f"- **{o['code']}** ({o['action']}): {o['changes']}")
    L += ["", "## Flags and unit issues", ""]
    for o in out:
        if o["notes"] and (o["code"] in cfg["flags"] or o["uom"] != cfg["default_uom"] or "not included" in o["notes"] or "qty" in o["notes"]):
            L.append(f"- {o['code']} {o['name']} [{o['qty']} {o['uom']}]: {o['notes']}")
    L += ["", "## File issues", ""] + [f"- {i}" for i in issues] + [f"- {r}" for r in removed] + ([] if issues or removed else ["- none"])
    errs = [o for o in out if o["action"] in ("error", "hold", "skip")]
    L += ["", "## Errors / holds / skips", ""] + [f"- {o['action']} {o['code']} {o['name']}: {o['changes']}" for o in errs] + ([] if errs else ["- none"])
    L += ["", "## All products", "", "| action | code | name | uom | image | changes | notes | properties |", "|---|---|---|---|---|---|---|---|"]
    for o in out:
        pr = "; ".join(f"{k}={v}" for k, v in o["properties"].items())
        L.append(f"| {o['action']} | {o['code']} | {o['name']} | {o['uom']} | {o['image']} | {o['changes']} | {o['notes']} | {pr} |")
    open(os.path.join(run_dir, "dryrun.md"), "w").write("\n".join(L) + "\n")
    plan = dict(created=dt.datetime.now().isoformat(timespec="seconds"), inputs=[dict(role=r, path=os.path.abspath(p), sha256=sha(p)) for r, p in inputs],
                category=cfg["category"], category_id=cat["id"] if cat else None, counts=dict(cnt), missing_property_definitions=missing_defs,
                fingerprint=plan_fingerprint(out),
                items=[{k: v for k, v in o.items() if not k.startswith("_") or k in ("_vals", "_write", "_img_write")} for o in out])
    json.dump(plan, open(os.path.join(run_dir, "plan.json"), "w"), indent=1, ensure_ascii=False, default=str)
    return plan


# ---------------------------------------------------------------- apply
def apply(args, cfg):
    plan = json.load(open(args.plan))
    inputs = [("current", args.bom)] + [("older", p) for p in args.older or []]
    if [(r, os.path.abspath(p), sha(p)) for r, p in inputs] != [(i["role"], i["path"], i["sha256"]) for i in plan["inputs"]]:
        sys.exit("input files differ from the approved plan (path or sha256); run a new dry run")
    run_dir = os.path.dirname(os.path.abspath(args.plan))
    logf = open(os.path.join(run_dir, "apply.log"), "a")
    def log(m):
        line = f"{dt.datetime.now().isoformat(timespec='seconds')} {m}"; print(line); logf.write(line + "\n"); logf.flush()
    ro = Odoo()
    cur, extras, parts, issues, removed = load_inputs(args.bom, args.older or [], cfg)
    st = read_state(ro, parts, cfg)
    out = finalize(build_plan(parts, st, cfg), {p["code"]: p for p in parts}, resolve_images(ro, build_plan(parts, st, cfg)))
    if plan_fingerprint(out) != plan["fingerprint"]:
        sys.exit("live Odoo state changed since the dry run (fingerprint mismatch); run a new dry run")
    wd = {i["code"]: i["write_date"] for i in plan["items"] if i.get("write_date")}
    for o in out:
        if o.get("product_id") and o["code"] in wd and o["write_date"] != wd[o["code"]]:
            sys.exit(f"{o['code']} was modified in Odoo after the dry run; run a new dry run")
    odoo = Odoo(allow_write=True, log=log)
    uoms = {u["name"]: u["id"] for u in odoo("uom.uom", "search_read", [], fields=["name"])}
    defs = {d.get("string"): d.get("name") for d in (st["categ"].get("product_properties_definition") or [])}
    pbc = {p["code"]: p for p in parts}
    ids_path = os.path.join(run_dir, "created-ids.jsonl")
    with open(ids_path, "a") as idsf:
        for o in out:
            if o["action"] not in ("create", "update"): continue
            if args.only and o["code"] not in args.only: continue
            p = pbc[o["code"]]
            if o["action"] == "create":
                v = dict(o["_vals"]); v["uom_id"] = uoms[v.pop("uom")]
                if p["img"]: v["image_1920"] = base64.b64encode(p["img"]["bytes"]).decode()
                if odoo("product.template", "search_count", [["default_code", "=", o["code"]]], context={"active_test": False}):
                    log(f"skip create {o['code']}: appeared meanwhile"); continue
                new = odoo("product.template", "create", [v])
                new = new[0] if isinstance(new, list) else new
                idsf.write(json.dumps({"action": "create", "code": o["code"], "tmpl_id": new}) + "\n"); idsf.flush()
                log(f"created {o['code']} tmpl {new}")
            else:
                v = dict(o["_write"])
                if "uom_id" in v: v["uom_id"] = uoms[v["uom_id"]]
                if o.get("_img_write"): v["image_1920"] = base64.b64encode(p["img"]["bytes"]).decode()
                if v:
                    odoo("product.template", "write", [o["product_id"]], v)
                    idsf.write(json.dumps({"action": "update", "code": o["code"], "tmpl_id": o["product_id"], "changes": o["changes"]}) + "\n")
                    log(f"updated {o['code']}: {o['changes']}")
    log("apply done")


# ---------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["dry-run", "apply"])
    ap.add_argument("bom", help="current Flatpack BOM xlsx (source of truth for parts)")
    ap.add_argument("--older", action="append", help="older BOM xlsx used only for in-cell images / dimensions / weight (same full code)")
    ap.add_argument("--config", default=os.path.join(HERE, "config.json"))
    ap.add_argument("--plan", help="approved plan.json (apply)")
    ap.add_argument("--only", action="append", help="apply: limit to these codes (one-product test); re-run dry-run afterwards")
    ap.add_argument("--runs-dir", default=os.environ.get("SYNC_RUNS_DIR", "runs"))
    args = ap.parse_args()
    cfg = json.load(open(args.config))
    if args.mode == "apply":
        if not args.plan: sys.exit("--plan required")
        return apply(args, cfg)
    run_dir = os.path.join(args.runs_dir, dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    os.makedirs(run_dir, exist_ok=True)
    cur, extras, parts, issues, removed = load_inputs(args.bom, args.older or [], cfg)
    odoo = Odoo()
    st = read_state(odoo, parts, cfg)
    out = build_plan(parts, st, cfg)
    out = finalize(out, {p["code"]: p for p in parts}, resolve_images(odoo, out))
    inputs = [("current", args.bom)] + [("older", p) for p in args.older or []]
    plan = write_reports(run_dir, inputs, cur, extras, out, issues, removed, st, cfg)
    print(json.dumps({"run_dir": run_dir, "counts": plan["counts"], "missing_property_definitions": plan["missing_property_definitions"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
