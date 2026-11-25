#!/usr/bin/env python3
"""Load-test loader: Cobra SAP MM60 (big.csv) -> cdrone-test product.template.

Default is a dry run (plan.json + plan_summary.json, read-only RPC). --apply writes to cdrone-test only
(approved by Chang 24 Nov 2026 19:04 ICT: all types, 9 count UoMs, cost on both companies, skip cancelled codes).

Design (for the apply step):
  - target: cdrone-test only (odoo_test.py refuses any other host/db)
  - one category per SAP material type: Goods/Cobra SAP/<MTyp>  -> easy archive/unlink later
  - fields: default_code, name, type='consu', is_storable=True, uom_id, standard_price (THB, CCS ctx),
            categ_id, company_id=False (shared), tracking='none', purchase_ok/sale_ok False except ZFG*/ZTR sale_ok
  - skip any default_code already in the db (active or archived) -> idempotent / resumable
  - sequential batches (default 1000), 1 call in flight, >=1 s gap (Odoo Cloud AUP), context
    tracking_disable + mail_create_nolog to avoid 258k chatter messages
  - progress log loadtest/progress.jsonl (batch no, codes, ids, seconds); rerun resumes by re-reading codes
"""
import csv, re, sys, json, hashlib, time, collections, argparse, os
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get('SAP_MM60_CSV', os.path.join(HERE, '..', 'big.csv'))
APPLY_ENABLED = True
CANCELLED = ('ยกเลิก (แจ้งสร้างผิด)', 'ยกเลิกแจ้งสร้าง Code ผิด')

UOM_MAP = {  # SAP BUn -> existing cdrone-test uom.uom name
    'EA': 'Units', 'PC': 'Units', 'KG': 'kg', 'G': 'g', 'LB': 'lb', 'OZ': 'oz', 'M': 'm', 'CM': 'cm', 'MM': 'mm',
    'FT': 'ft', 'YD': 'yd', 'M2': 'm²', 'L': 'L', 'ML': 'ml', 'GAL': 'gal (US)', 'DZ': 'Dozens', 'TON': 't',
    'AU': 'Units', 'PT': 'Units', '': 'Units',  # AU=activity unit, PT=pint (1 item), blank=1 corrupt row
}
NEW_UOMS = {  # proposed new count units (1 = 1 Units) to keep the SAP unit visible
    'PAC': 'Pack', 'SET': 'Set', 'PAA': 'Pair', 'ROL': 'Roll', 'CAR': 'Carton', 'CAN': 'Can',
    'BT': 'Bottle', 'DR': 'Drum', 'BAG': 'Bag',
}
COLS = ['Material', 'Material Description', 'Plnt', 'MTyp', 'Matl Group', 'BUn', 'PGr', 'Typ', 'ValCl',
        'Pr.', 'Price', 'Crcy', 'per', 'Created', 'Last Chg']

def read_rows():
    """Parse big.csv. Two source cells contain pasted tab-separated rows (xlsx corruption); expand them."""
    rows = []
    with open(SRC, encoding='utf-8') as f:
        r = csv.reader(f); next(r)
        for rec in r:
            rec = rec[:15]
            blob_at = next((i for i, v in enumerate(rec) if '\t' in v), None)
            if blob_at is None:
                rows.append(dict(zip(COLS, [v.strip() for v in rec]))); continue
            # head row: fields before the blob + first tab-chunk of blob
            parts = rec[blob_at].replace('_x000D_', '').split('\n')
            first = rec[:blob_at] + parts[0].split('\t')
            rows.append(dict(zip(COLS, [v.strip() for v in first])))
            tail = rec[blob_at + 1:]
            for k, line in enumerate(parts[1:], 1):
                cells = line.split('\t')
                if k == len(parts) - 1: cells = cells + tail  # last pasted row continues in the next CSV cells
                if cells and cells[0] == '': cells = cells[1:]
                if cells and re.fullmatch(r'\d{8}', cells[0] or ''):
                    rows.append(dict(zip(COLS, [v.strip() for v in cells])))
    return rows

def build(rows):
    seen, out, issues = set(), [], collections.Counter()
    for d in rows:
        code = d['Material']
        if code in seen: issues['dupe_code'] += 1; continue
        seen.add(code)
        try: price = float((d.get('Price') or '0').replace(',', '')) if d.get('Pr.') == 'S' else 0.0
        except ValueError: price = 0.0; issues['bad_price'] += 1
        per = d.get('per') or '1'
        try: price = price / float(per) if float(per) > 1 else price
        except ValueError: pass
        bun = d.get('BUn', '')
        uom = UOM_MAP.get(bun) or NEW_UOMS.get(bun)
        if not uom: issues['unmapped_uom:' + bun] += 1; uom = 'Units'
        name = d.get('Material Description') or code
        if not d.get('Material Description'): issues['blank_desc'] += 1
        if name in CANCELLED: issues['skipped_cancelled'] += 1; continue
        out.append(dict(default_code=code, name=name, mtyp=d.get('MTyp', ''), matl_group=d.get('Matl Group', ''),
                        sap_uom=bun, uom=uom, standard_price=round(price, 2), has_price=d.get('Pr.') == 'S'))
    return out, issues

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--types', help='comma list of MTyp, default all')
    ap.add_argument('--batch', type=int, default=1000); ap.add_argument('--offline', action='store_true')
    ap.add_argument('--apply', action='store_true'); ap.add_argument('--limit', type=int, help='max records this run (pilot)')
    ap.add_argument('--fix-costs', action='store_true'); ap.add_argument('--pilot', action='store_true', help='1,000 records spread across the file'); a = ap.parse_args()
    if a.apply and not APPLY_ENABLED: sys.exit('apply disabled: needs Chang-approved plan')
    rows = read_rows(); recs, issues = build(rows)
    if a.types: keep = set(a.types.split(',')); recs = [r for r in recs if r['mtyp'] in keep]
    existing = set()
    if not a.offline:
        sys.path.insert(0, HERE); import odoo_test as T
        ctx = {'active_test': False}
        existing = {p['default_code'] for p in T.x('product.product', 'search_read', [['default_code', '!=', False]],
                                                    fields=['default_code'], context=ctx)}
        uoms = {u['name'] for u in T.x('uom.uom', 'search_read', [], fields=['name'], context=ctx)}
        missing_uoms = sorted({r['uom'] for r in recs} - uoms)
    else: missing_uoms = sorted(set(NEW_UOMS.values()))
    todo = [r for r in recs if r['default_code'] not in existing]
    by_type = collections.Counter(r['mtyp'] for r in todo)
    summ = dict(source_rows_parsed=len(rows), unique_codes=len(recs), already_in_db=len(recs) - len(todo),
                to_create=len(todo), batches=-(-len(todo) // a.batch), batch_size=a.batch,
                by_type=dict(by_type.most_common()), categories=[f'Goods/Cobra SAP/{t}' for t in sorted(by_type)],
                uoms_to_create=missing_uoms, by_uom=dict(collections.Counter(r['uom'] for r in todo).most_common()),
                no_price=sum(not r['has_price'] for r in todo), issues=dict(issues),
                source_sha256=hashlib.sha256(open(SRC, 'rb').read()).hexdigest())
    json.dump(dict(summary=summ, records=todo), open(os.path.join(HERE, 'plan.json'), 'w'), ensure_ascii=False)
    open(os.path.join(HERE, 'plan_summary.json'), 'w').write(json.dumps(summ, ensure_ascii=False, indent=1))
    print(json.dumps(summ, ensure_ascii=False, indent=1))
    if a.apply or a.fix_costs:
        import apply as A
        if a.pilot: A.run(todo[::max(1, len(todo) // 1000)][:1000], a.batch); return
        if a.apply: A.run(todo[:a.limit] if a.limit else todo, a.batch)
        A.fix_costs(recs)

if __name__ == '__main__': main()
