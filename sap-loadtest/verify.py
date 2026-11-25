"""Read back loaded products vs plan: code, name, uom, category, tracking, company, cost on both companies."""
import json, os, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import odoo_test as T
# plan.json must be the full plan: run `python3 load_sap.py --offline` first (no RPC). The 3 Merops skins pre-existed outside Cobra SAP.
PRE = {'12201047', '12201048', '12201049'}
plan = {r['default_code']: r for r in json.load(open(os.path.join(HERE, 'plan.json')))['records'] if r['default_code'] not in PRE}
from load_sap import NEW_UOMS
root = T.x('product.category', 'search', [['name', '=', 'Cobra SAP']])[0]
cats = {c['id']: c['name'] for c in T.x('product.category', 'search_read', [['parent_id', '=', root]], fields=['name'])}
uoms = {u['id']: u['name'] for u in T.x('uom.uom', 'search_read', [], fields=['name'], context={'active_test': False})}
seen = collections.Counter(); got = {}; errs = collections.Counter(); ex = []
for cid in (1, 2):
    off = 0
    while True:
        ps = T.x('product.product', 'search_read', [['categ_id', 'child_of', root]], offset=off, limit=20000, order='id',
                 fields=['default_code', 'name', 'uom_id', 'categ_id', 'standard_price', 'tracking', 'company_id', 'is_storable'],
                 context={'allowed_company_ids': [cid], 'active_test': False})
        if not ps: break
        off += len(ps)
        for p in ps:
            if cid == 1: seen[p['default_code']] += 1
            r = plan.get(p['default_code'])
            if not r: errs['not_in_plan'] += 1; continue
            got[p['default_code']] = p['categ_id'][1]
            chk = {'cost_c%d' % cid: abs(p['standard_price'] - r['standard_price']) < 0.005}
            if cid == 1:
                chk.update(name=p['name'] == r['name'], uom=uoms[p['uom_id'][0]] == r['uom'], categ=cats.get(p['categ_id'][0]) == r['mtyp'],
                           untracked=not p['tracking'], shared=not p['company_id'], storable=p['is_storable'])
            for k, ok in chk.items():
                if not ok:
                    errs[k] += 1
                    if len(ex) < 10: ex.append((k, p['default_code'], p, r))
dupes = [c for c, n in seen.items() if n > 1]; missing = sorted(set(plan) - set(got))
print('plan', len(plan), 'records read back', sum(seen.values()), 'unique codes', len(got), 'errors', dict(errs))
print('duplicates', len(dupes), dupes[:20]); print('missing', len(missing), missing[:20])
print('count UoMs present', sorted(set(NEW_UOMS.values()) & set(uoms.values())), 'missing', sorted(set(NEW_UOMS.values()) - set(uoms.values())))
exp = collections.Counter(r['mtyp'] for r in plan.values()); act = collections.Counter(v.split('/')[-1].strip() for v in got.values())
print('per category (plan, odoo, diff):'); [print(f'  {t:5s} {exp[t]:7d} {act[t]:7d} {act[t]-exp[t]:+d}') for t in sorted(exp, key=lambda t: -exp[t])]
noprice = [c for c, r in plan.items() if not r['has_price']]; print('no-price items in plan', len(noprice), '(cost checked = 0 on both companies via cost_c1/cost_c2)')
for e in ex: print(e)
print('by category', dict(collections.Counter(v.split('/')[-1].strip() for v in got.values()).most_common()))
