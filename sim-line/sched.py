#!/usr/bin/env python3
"""Finite-capacity scheduler for the SIM week (deviation from Odoo's Plan button, which in Odoo 20 always plans from 'now'
and does not wait for child MOs). Same rules as Odoo: station calendars (1 shift Mon-Fri 08-16 ICT / 24-7 for cure-dry),
alternative stations (pick earliest finish), capacity per cycle, efficiency, setup + cleanup. Writes workcenter + dates +
expected duration onto each SIM work order, so Odoo's Gantt / load views show the plan."""
import json, math, datetime as dt, sys, collections
from odoo_sim import x
import spec as S, plan as PL, build as B
W0 = B.WEEK0                                  # Mon 30 Nov 01:00 UTC = 08:00 ICT
SHIFT = (1.0, 9.0)                            # UTC hours = 08:00-16:00 ICT
def h(d): return (d - W0).total_seconds() / 3600 + 1.0   # hours since Mon 00:00 UTC
def T(hh): return W0 + dt.timedelta(hours=hh - 1.0)
def labour_end(start, mins):
    t, rem = start, mins / 60
    while rem > 1e-9:
        day, hr = divmod(t, 24)
        if day % 7 >= 5: t = (day // 7 + 1) * 168 + SHIFT[0]; continue
        if hr < SHIFT[0]: t = day * 24 + SHIFT[0]; continue
        if hr >= SHIFT[1] - 1e-9: t = (day + 1) * 24 + SHIFT[0]; continue
        step = min(rem, SHIFT[1] - hr); t += step; rem -= step
    return t
def align(t):  # first working instant >= t
    return labour_end(t, 0.0001) - 0.0001 / 60

WCT = {c: dict(kind=k, cap=cap, eff=eff, su=su, cl=cl) for c, _, k, cap, eff, su, cl, _, _ in S.WCT}
groups = {k: v for k, v in json.load(open('wc_groups.json')).items()}
wc_group = {v[0]: k for k, v in groups.items()}          # primary station id -> group key
busy = collections.defaultdict(list)                      # station id -> sorted [(start, end)] (gap filling)

def schedule_mo(mo, ready, wos, ops):
    t = ready; out = []
    for w in sorted(wos, key=lambda w: (ops[w['operation_id'][0]]['sequence'], w['id'])):
        g = wc_group[ops[w['operation_id'][0]]['workcenter_id'][0]]; code = g.split('|')[0]; c = WCT[code]
        cyc = ops[w['operation_id'][0]]['time_cycle_manual']
        dur = c['su'] + math.ceil(mo['product_qty'] / c['cap']) * cyc * 100 / c['eff'] + c['cl']
        best = None
        for st in groups[g]:
            s = t
            for bs, be in busy[st] + [(1e12, 1e12)]:      # earliest gap that fits
                if c['kind'] == 'labour': s = align(s); e = labour_end(s, dur)
                else: e = s + dur / 60
                if e <= bs + 1e-9: break
                s = max(s, be)
            if best is None or e < best[2]: best = (st, s, e)
        st, s, e = best; busy[st].append((s, e)); busy[st].sort(); t = e
        out.append(dict(id=w['id'], workcenter_id=st, s=s, e=e, dur=round(dur, 2), code=code, kind=c['kind']))
    return t, out

_CACHE = {}
def main(write=True, extra=None, even=False, out='schedule.json'):
    busy.clear()
    for k, n in (extra or {}).items():
        groups[k] = groups[k] + [-(1000 * len(groups) + i) for i in range(n)]   # virtual stations (what-if only)
    if 'trees' not in _CACHE: _CACHE['trees'] = PL.tree()
    trees = _CACHE['trees']
    mo_ids = [m['id'] for t in trees for m in [t['fg']] + t['kids'] + t['lam']]
    if 'wos' not in _CACHE: _CACHE['wos'] = x('mrp.workorder', 'search_read', [['production_id', 'in', mo_ids]], fields=['production_id', 'operation_id'])
    wos = _CACHE['wos']
    by_mo = collections.defaultdict(list)
    for w in wos: by_mo[w['production_id'][0]].append(w)
    if 'ops' not in _CACHE: _CACHE['ops'] = {o['id']: o for o in x('mrp.routing.workcenter', 'read', list({w['operation_id'][0] for w in wos}), fields=['sequence', 'workcenter_id', 'time_cycle_manual'])}
    ops = _CACHE['ops']
    D = {d[0]: d for d in json.load(open('week_demand.json'))}
    order = sorted(trees, key=lambda t: (t['day'], D[t['ref']][0], t['fg']['id']))
    plan, res = [], []
    for n, t in enumerate(order):
        rel = (int(n * 5 / len(order)) if even else t['day']) * 24 + SHIFT[0]
        kid_end = []
        for a in t['af']:
            lams = [l for l in t['lam'] if l['origin'] == a['name']]
            le = rel
            for l in lams:
                e, o = schedule_mo(l, rel, by_mo[l['id']], ops); plan += o; le = max(le, e)
            e, o = schedule_mo(a, le, by_mo[a['id']], ops); plan += o; kid_end.append(e)
        for k in t['kids']:
            if k in t['af']: continue
            e, o = schedule_mo(k, rel, by_mo[k['id']], ops); plan += o; kid_end.append(e)
        e, o = schedule_mo(t['fg'], max(kid_end), by_mo[t['fg']['id']], ops); plan += o
        res.append(dict(ref=t['ref'], fg=t['fg']['name'], sku=t['fg']['product_id'][1].split(']')[0][1:], qty=t['fg']['product_qty'],
                        release=T(rel).strftime('%Y-%m-%d %H:%M'), finish=T(e).strftime('%Y-%m-%d %H:%M'), lead_h=round(e - rel, 1),
                        deadline_h=72, late=e - rel > 72))
    json.dump(dict(plan=[dict(p, s=T(p['s']).strftime('%Y-%m-%d %H:%M:%S'), e=T(p['e']).strftime('%Y-%m-%d %H:%M:%S')) for p in plan], fg=res),
              open(out, 'w'), indent=0)
    print('WOs scheduled', len(plan), 'FG MOs', len(res))
    for k, n in (extra or {}).items(): groups[k] = [g for g in groups[k] if g > 0]
    if write:
        vals = [(p['id'], {'workcenter_id': p['workcenter_id'], 'date_start': T(p['s']).strftime('%Y-%m-%d %H:%M:%S'),
                           'date_finished': T(p['e']).strftime('%Y-%m-%d %H:%M:%S'), 'duration_expected': p['dur']}) for p in plan]
        for i in range(0, len(vals), 150):
            b = vals[i:i + 150]
            x('mrp.workorder', 'web_save_multi', [v[0] for v in b], [v[1] for v in b], specification={})
            print('written', i + len(b), flush=True)
    return res

if __name__ == '__main__':
    main(write='--write' in sys.argv)
