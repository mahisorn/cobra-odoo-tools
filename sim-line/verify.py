#!/usr/bin/env python3
"""Read the SIM week back from cdrone-test and report counts, lead times, lateness and work-centre load."""
import json, datetime as dt, collections, statistics
from odoo_sim import x, ledger
U = '%Y-%m-%d %H:%M:%S'; P = lambda s: dt.datetime.strptime(s, U)
W0 = dt.datetime(2026, 11, 30, 1, 0); W1 = W0 + dt.timedelta(days=4, hours=8)   # Mon 08:00 .. Fri 16:00 ICT
L = ledger(); D = {d[0]: d for d in json.load(open('week_demand.json'))}
sos = x('sale.order', 'read', list(L['sale.order'].values()), fields=['name', 'client_order_ref', 'commitment_date', 'state'])
mos = x('mrp.production', 'search_read', [['product_id.default_code', '=like', 'SIM-%']], fields=['name', 'origin', 'product_id', 'product_qty', 'state', 'is_planned', 'date_start', 'date_finished'])
wos = x('mrp.workorder', 'search_read', [['production_id', 'in', [m['id'] for m in mos]]], fields=['production_id', 'workcenter_id', 'date_start', 'date_finished', 'duration_expected', 'state'])
print('SOs', len(sos), 'confirmed', sum(s['state'] == 'sale' for s in sos))
print('MOs', len(mos), 'planned', sum(m['is_planned'] for m in mos), 'states', dict(collections.Counter(m['state'] for m in mos)))
print('WOs', len(wos), 'with dates', sum(bool(w['date_start']) for w in wos))
print('WO window', min(w['date_start'] for w in wos), '->', max(w['date_finished'] for w in wos), '(UTC)')
kind = collections.Counter(m['product_id'][1].split(']')[0].split('-')[-1] for m in mos); print('MOs by level', dict(kind))
byo = collections.defaultdict(list)
for m in mos: byo[m['origin']].append(m)
wo_by = collections.defaultdict(list)
for w in wos: wo_by[w['production_id'][0]].append(w)
def tree_ids(m):
    out = [m]
    for k in byo.get(m['name'], []): out += tree_ids(k)
    return out
rows = []
for s in sos:
    ref = s['client_order_ref']; rel = W0 + dt.timedelta(days=D[ref][4]); due = P(s['commitment_date'])
    for fg in byo.get(s['name'], []):
        t = tree_ids(fg); ws = [w for m in t for w in wo_by[m['id']]]
        fin = max(P(w['date_finished']) for w in wo_by[fg['id']]); first = min(P(w['date_start']) for w in ws)
        lead = (fin - rel).total_seconds() / 3600
        wk = sum(1 for d in range((fin.date() - rel.date()).days + 1) if (rel.date() + dt.timedelta(days=d)).weekday() == 5)
        rows.append(dict(fg=fg['name'], sku=fg['product_id'][1].split(']')[0][1:], qty=fg['product_qty'], rel=rel, fin=fin, lead=lead,
                         lead_xwe=lead - 48 * wk, e2e=(fin - first).total_seconds() / 3600, late=fin > due, day=rel.strftime('%a %d')))
Lh = [r['lead'] for r in rows]; X = [r['lead_xwe'] for r in rows]
print(f'FG MOs {len(rows)}; release->finish lead h: min {min(Lh):.0f} median {statistics.median(Lh):.0f} max {max(Lh):.0f}; '
      f'excl. weekends: min {min(X):.0f} median {statistics.median(X):.0f} max {max(X):.0f}; within 72 h: {sum(l <= 72 for l in Lh)}; '
      f'late vs SO commitment (release+72 h): {sum(r["late"] for r in rows)}')
print('by release day (n, median lead, median excl weekend, late):')
for d in sorted({r['day'] for r in rows}, key=lambda d: d[-2:]):
    rr = [r for r in rows if r['day'] == d]
    print(f'  {d}: {len(rr)}, {statistics.median([r["lead"] for r in rr]):.0f} h, {statistics.median([r["lead_xwe"] for r in rr]):.0f} h, late {sum(r["late"] for r in rr)}')
print('by family (n, min/median/max lead excl weekend):')
for f in ('QX4', 'HX6', 'VT2', 'INT'):
    rr = [r['lead_xwe'] for r in rows if f'-{f}-' in r['sku']]
    print(f'  {f}: {len(rr)}, {min(rr):.0f}/{statistics.median(rr):.0f}/{max(rr):.0f} h')
print('last FG finish', max(r['fin'] for r in rows), 'UTC')
# load per work-centre group: planned hours (all week-1 orders) vs 1-shift week capacity
g = json.load(open('wc_groups.json')); st2g = {s: k for k, v in g.items() for s in v}
load = collections.defaultdict(float); inwk = collections.defaultdict(float)
for w in wos:
    k = st2g[w['workcenter_id'][0]]; load[k] += w['duration_expected'] / 60
print('work-centre load (stations, planned h, % of 1-shift week [passive: % of 24/7 week]):')
res = []
for k in g:
    capw = len(g[k]) * (168 if k.startswith(('CUR', 'RCK')) else 40)
    res.append((k, len(g[k]), round(load[k]), round(100 * load[k] / capw)))
for r in sorted(res, key=lambda r: -r[3]): print('  ', *r)
json.dump(dict(rows=[dict(r, rel=str(r['rel']), fin=str(r['fin'])) for r in rows], load=res), open('verify_result.json', 'w'), indent=0, default=str)
