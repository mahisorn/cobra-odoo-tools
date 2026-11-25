#!/usr/bin/env python3
"""Schedule the SIM week bottom-up: LAM -> AF (after LAM) and HAR/PRP/AVI (at release) -> FG (after all children).
Uses Odoo's own work-order planner (button_plan, alternatives + calendars); this script only sets each MO's earliest start."""
import json, datetime as dt, sys
from odoo_sim import x, ledger
import build as B
UTC = '%Y-%m-%d %H:%M:%S'
def P(s): return dt.datetime.strptime(s, UTC)
def F(d): return d.strftime(UTC)

def tree():
    L = ledger(); D = {d[0]: d for d in json.load(open('week_demand.json'))}
    sos = x('sale.order', 'read', list(L['sale.order'].values()), fields=['name', 'client_order_ref'])
    so_ref = {s['name']: s['client_order_ref'] for s in sos}
    mos = x('mrp.production', 'search_read', [['product_id.default_code', '=like', 'SIM-%']],
            fields=['name', 'product_id', 'product_qty', 'origin', 'state', 'date_start', 'date_finished', 'is_planned', 'workorder_ids'])
    by_origin = {}
    for m in mos: by_origin.setdefault(m['origin'], []).append(m)
    out = []
    for so, ref in so_ref.items():
        day = D[ref][4]
        for fg in by_origin.get(so, []):
            kids = by_origin.get(fg['name'], [])
            af = [k for k in kids if k['product_id'][1].startswith('[SIM-') and '-AF]' in k['product_id'][1]]
            lam = [l for a in af for l in by_origin.get(a['name'], [])]
            out.append(dict(ref=ref, so=so, day=day, fg=fg, kids=kids, af=af, lam=lam))
    return out

def plan(ids, starts=None):
    if not ids: return
    if starts:
        x('mrp.production', 'web_save_multi', ids, [{'date_start': starts[i]} for i in ids], specification={})
    try: x('mrp.production', 'button_plan', ids)
    except Exception as e:
        if 'cannot marshal None' not in str(e): raise

def run():
    T = tree()
    for day in range(5):
        rel = F(B.WEEK0 + dt.timedelta(days=day)); rows = [t for t in T if t['day'] == day]
        if not rows: continue
        lam = [l['id'] for t in rows for l in t['lam'] if not l['is_planned']]
        plan(lam, {i: rel for i in lam})
        fin = {m['id']: m['date_finished'] for m in x('mrp.production', 'read', [l['id'] for t in rows for l in t['lam']], fields=['date_finished'])}
        af = {}
        for t in rows:
            for a in t['af']:
                if a['is_planned']: continue
                ls = [l for l in t['lam'] if l['origin'] == a['name']]
                af[a['id']] = max(fin[l['id']] for l in ls) if ls else rel
        plan(list(af), af)
        sub = [k['id'] for t in rows for k in t['kids'] if k not in t['af'] and not k['is_planned']]
        plan(sub, {i: rel for i in sub})
        fin = {m['id']: m['date_finished'] for m in x('mrp.production', 'read', [k['id'] for t in rows for k in t['kids']], fields=['date_finished'])}
        fg = {t['fg']['id']: max(fin[k['id']] for k in t['kids']) for t in rows if not t['fg']['is_planned']}
        plan(list(fg), fg)
        print('day', day, 'planned FG', len(fg), 'AF', len(af), 'LAM', len(lam), 'SUB', len(sub), flush=True)

if __name__ == '__main__':
    run()
