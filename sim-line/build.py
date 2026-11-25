#!/usr/bin/env python3
"""RC-9 SIM line build on cdrone-test. Stages: setup, catalog, stock, orders, plan. Idempotent via created_ids.json."""
import sys, math, json, datetime as dt
from odoo_sim import x, record, changed, ledger, get_or_create
import spec as S
NOMAIL = {'tracking_disable': True, 'mail_create_nolog': True, 'mail_notrack': True}
CCS = 1

def setup():
    p = x('decimal.precision', 'search_read', [['name', '=', 'Product Unit']], fields=['digits'])[0]
    if p['digits'] != 3:
        x('decimal.precision', 'write', [p['id']], {'digits': 3}); changed('decimal.precision Product Unit', p['digits'], 3)
    r = x('stock.route', 'read', [1], fields=['active', 'name'], context={'active_test': False})[0]
    if not r['active']:
        x('stock.route', 'write', [1], {'active': True}); changed('stock.route 1 MTO active', False, True)
    rule = x('stock.rule', 'read', [3], fields=['active'], context={'active_test': False})[0]
    if not rule['active']:
        x('stock.rule', 'write', [3], {'active': True}); changed('stock.rule 3 Stock->Customers MTO active', False, True)
    att = [(0, 0, {'dayofweek': str(d), 'hour_from': 0.0, 'hour_to': 24.0, 'day_period': 'full_day'}) for d in range(7)]
    get_or_create('resource.calendar', 'SIM 24/7', [['name', '=', 'SIM 24/7']],
                  {'name': 'SIM 24/7', 'company_id': CCS, 'attendance_ids': att, 'hours_per_day': 24.0})
    goods = x('product.category', 'search', [['name', '=', 'Goods'], ['parent_id', '=', False]])[0]
    root = get_or_create('product.category', 'SIM Demo', [['name', '=', 'SIM Demo'], ['parent_id', '=', goods]], {'name': 'SIM Demo', 'parent_id': goods})
    for n in ('Finished', 'Semi', 'Purchased'):
        get_or_create('product.category', 'SIM Demo/' + n, [['name', '=', n], ['parent_id', '=', root]], {'name': n, 'parent_id': root})
    get_or_create('mrp.workcenter.tag', 'SIM', [['name', '=', 'SIM']], {'name': 'SIM'})
    get_or_create('res.partner.category', 'DEMO', [['name', '=', 'DEMO']], {'name': 'DEMO'})

def workcenters():
    L = ledger(); cal8 = x('resource.calendar', 'search', [['name', '=', 'Work Center 40 hours/week']])[0]
    cal24 = L['resource.calendar']['SIM 24/7']; tag = L['mrp.workcenter.tag']['SIM']
    groups = {}
    for code, name, kind, cap, eff, su, cl, cost, st in S.WCT:
        parts = {'': st} if isinstance(st, int) else st
        for line, n in parts.items():
            g = []
            for i in range(1, n + 1):
                wcode = f'SIM-{code}{"-" + line if line else ""}-{i:02d}'
                lname = f' (Line {line})' if line else (' (shared composite shop)' if kind == 'labour' else '')
                vals = {'name': f'{wcode} {name}{lname}', 'code': wcode, 'company_id': CCS, 'time_efficiency': eff,
                        'time_start': su, 'time_stop': cl, 'costs_hour': cost, 'tag_ids': [(6, 0, [tag])],
                        'resource_calendar_id': cal24 if kind == 'passive' else cal8, 'tz': 'Asia/Bangkok',
                        'note': f'ASSUMPTION (RC-9 PLAN.md): capacity {cap}/cycle, efficiency {eff}%, setup {su} min, cleanup {cl} min, {cost} THB/h'}
                g.append(get_or_create('mrp.workcenter', wcode, [['code', '=', wcode]], vals))
            groups[(code, line)] = g
    for (code, line), g in groups.items():   # alternatives within each group
        for w in g:
            alts = [o for o in g if o != w]
            if alts: x('mrp.workcenter', 'write', [w], {'alternative_workcenter_ids': [(6, 0, alts)]})
    json.dump({f'{c}|{l}': g for (c, l), g in groups.items()}, open('wc_groups.json', 'w'))
    return groups

def pid(code):
    r = x('product.product', 'search_read', [['default_code', '=', code]], fields=['id', 'product_tmpl_id', 'uom_id'], context={'active_test': False})
    assert len(r) == 1, (code, r); return r[0]

def products():
    L = ledger(); cat = {n: L['product.category']['SIM Demo/' + n] for n in ('Finished', 'Semi', 'Purchased')}
    mto, mfg = 1, 5
    def mk(code, name, categ, cost, routes=(), tracking=False, price=0):
        v = {'name': name, 'default_code': code, 'type': 'consu', 'is_storable': True, 'company_id': False, 'categ_id': categ,
             'standard_price': cost, 'list_price': price, 'route_ids': [(6, 0, [r for r in routes if r != 5])], 'sale_ok': bool(price), 'purchase_ok': not routes}
        if tracking: v['tracking'] = tracking
        return get_or_create('product.template', code, [['default_code', '=', code]], v, ctx=dict(NOMAIL, allowed_company_ids=[CCS]))
    for code, (name, cost) in S.PUR.items(): mk(code, 'SIM ' + name, cat['Purchased'], cost)
    for f in S.FAMS:
        mk(f'SIM-{f}-LAM', f'SIM {f} laminate set (layup + cure)', cat['Semi'], 0, (mfg, mto))
        mk(f'SIM-{f}-AF', f'SIM {f} airframe, bonded & painted', cat['Semi'], 0, (mfg, mto))
        mk(f'SIM-{f}-HAR', f'SIM {f} wiring harness', cat['Semi'], 0, (mfg, mto))
        mk(f'SIM-{f}-PRP', f'SIM {f} propulsion set', cat['Semi'], 0, (mfg, mto))
        mk(f'SIM-{f}-AVI', f'SIM {f} avionics set', cat['Semi'], 0, (mfg, mto))
    for code, (f, name, _) in S.SKU.items():
        mk(code, name, cat['Finished'], 0, (mfg, mto), tracking='serial', price=S.F[f]['price'])

def boms():
    groups = {tuple(k.split('|')): v for k, v in json.load(open('wc_groups.json')).items()}
    def wc(code, f):  # primary station of the group serving family f
        line = '' if (code, '') in groups else S.LINE[f]
        return groups[(code, line)][0], groups[(code, line)]
    caps = {c: cap for c, _, _, cap, *_ in S.WCT}
    def bom(code, lines, ops):
        p = pid(code)
        bl = []
        for c, q in lines:
            cp = pid(c); bl.append((0, 0, {'product_id': cp['id'], 'product_qty': q, 'uom_id': cp['uom_id'][0]}))
        ol = [(0, 0, {'name': n, 'workcenter_id': w, 'time_mode': 'manual', 'time_cycle_manual': m, 'sequence': (i + 1) * 10})
              for i, (n, w, m) in enumerate(ops)]
        bid = get_or_create('mrp.bom', code, [['product_tmpl_id', '=', p['product_tmpl_id'][0]], ['active', 'in', [True, False]]],
                            {'product_tmpl_id': p['product_tmpl_id'][0], 'product_qty': 1, 'type': 'normal', 'company_id': CCS,
                             'bom_line_ids': bl, 'operation_ids': ol}, ctx=NOMAIL)
        return p, bid
    cap_vals = []
    def capacity(p, code, f):
        if caps[code] > 1:
            for w in wc(code, f)[1]:
                cap_vals.append({'workcenter_id': w, 'product_id': p['id'], 'capacity': caps[code]})
    for f in S.FAMS:
        m = S.MIN[f]; d = S.F[f]
        p, _ = bom(f'SIM-{f}-LAM', d['lam'], [('Layup & vacuum bag', wc('LAY', f)[0], m['LAY']), ('Oven cure (calendar)', wc('CUR', f)[0], m['CUR'])])
        capacity(p, 'LAY', f); capacity(p, 'CUR', f)
        p, _ = bom(f'SIM-{f}-AF', [(f'SIM-{f}-LAM', 1)] + d['af'],
                   [('CNC trim & drill', wc('CNC', f)[0], m['CNC']), ('Bond structure', wc('BND', f)[0], m['BND']),
                    ('Bond cure (calendar)', wc('RCK', f)[0], m['RCK_BOND']), ('Prep & paint', wc('PNT', f)[0], m['PNT']),
                    ('Paint dry (calendar)', wc('RCK', f)[0], m['RCK_DRY'])])
        for c in ('BND', 'RCK', 'PNT'): capacity(p, c, f)
        bom(f'SIM-{f}-HAR', d['har'], [('Build harness', wc('HAR', f)[0], m['HAR'])])
        bom(f'SIM-{f}-PRP', d['prp'], [('Assemble propulsion', wc('PRP', f)[0], m['PRP'])])
        bom(f'SIM-{f}-AVI', d['avi'], [('Integrate avionics', wc('AVI', f)[0], m['AVI'])])
    for code, (f, name, extra) in S.SKU.items():
        m = S.MIN[f]; d = S.F[f]
        lines = [(f'SIM-{f}-AF', 1), (f'SIM-{f}-HAR', 1), (f'SIM-{f}-PRP', 1), (f'SIM-{f}-AVI', 1), d['bat']] + extra + S.PACK
        p, _ = bom(code, lines, [('Final assembly', wc('FAS', f)[0], m['FAS']), ('Calibration & firmware', wc('CAL', f)[0], m['CAL']),
                                 ('Functional & flight test', wc('TST', f)[0], m['TST']), ('Final QC', wc('QC', f)[0], m['QC']),
                                 ('Packing', wc('PCK', f)[0], m['PCK'])])
        for c in ('FAS', 'CAL', 'TST'): capacity(p, c, f)
    L = ledger()
    if 'mrp.workcenter.capacity' not in L:
        ids = x('mrp.workcenter.capacity', 'create', cap_vals)
        L = ledger(); L['mrp.workcenter.capacity'] = {'all': ids}; json.dump(L, open('created_ids.json', 'w'), indent=1, ensure_ascii=False)
        print('capacity lines', len(ids))

if __name__ == '__main__':
    st = sys.argv[1]
    if st == 'setup': setup()
    elif st == 'wc': workcenters()
    elif st == 'products': products()
    elif st == 'boms': boms()

# ---------- week demand, stock, customers, orders ----------
WEEK0 = dt.datetime(2026, 11, 30, 1, 0)   # Mon 30 Nov 2026 08:00 ICT = 01:00 UTC
def week_demand(seed=199, orders=25, units=227):
    import random
    import model as M
    r = random.Random(seed); fams = S.FAMS; w = [M.FAM[f]['share'] for f in fams]
    skus = {f: [k for k, v in S.SKU.items() if v[0] == f] for f in fams}
    out = []
    for i in range(orders):
        (lo, hi), = r.choices([b for b, _ in M.SIZE_BUCKETS], [p for _, p in M.SIZE_BUCKETS])
        f = r.choices(fams, w)[0]; out.append([f'SIM-OEM-W1-{i+1:02d}', r.choice(skus[f]), f, r.randint(lo, hi), i % 5, (i % 20) + 1])
    k = units / sum(o[3] for o in out)
    for o in out: o[3] = max(1, round(o[3] * k))
    return out   # ref, sku, family, qty, release weekday 0-4, customer no

def explode(code, q, acc):
    from spec import F, SKU, PACK
    if code in SKU:
        f, _, extra = SKU[code]; d = F[f]
        for c, n in [(f'SIM-{f}-AF', 1), (f'SIM-{f}-HAR', 1), (f'SIM-{f}-PRP', 1), (f'SIM-{f}-AVI', 1), d['bat']] + extra + PACK: explode(c, q * n, acc)
    elif code.startswith('SIM-') and code.split('-')[-1] in ('LAM', 'AF', 'HAR', 'PRP', 'AVI'):
        f, part = code.split('-')[1], code.split('-')[2]; d = S.F[f]
        lines = {'LAM': d['lam'], 'AF': [(f'SIM-{f}-LAM', 1)] + d['af'], 'HAR': d['har'], 'PRP': d['prp'], 'AVI': d['avi']}[part]
        for c, n in lines: explode(c, q * n, acc)
    else: acc[code] = acc.get(code, 0) + q

def stock():
    L = ledger()
    if 'stock.quant' in L: print('stock already done'); return
    D = week_demand(); acc = {}
    for _, sku, _, q, *_ in D: explode(sku, q, acc)
    vals = []
    for code, q in sorted(acc.items()):
        p = pid(code); vals.append({'product_id': p['id'], 'location_id': 6, 'inventory_quantity': math.ceil(q * 1.5 * 1000) / 1000})
    qids = x('stock.quant', 'create', vals, context=dict(NOMAIL, inventory_mode=True))
    L = ledger(); L['stock.quant'] = {'ids': qids, 'lines': {c: round(q * 1.5, 3) for c, q in acc.items()}}
    json.dump(L, open('created_ids.json', 'w'), indent=1, ensure_ascii=False)
    x('stock.quant', 'action_apply_inventory', qids, context=dict(NOMAIL, inventory_mode=True, inventory_name='SIM-RC9 week-1 component stock'))
    print('stock quants', len(qids))

def customers():
    tag = ledger()['res.partner.category']['DEMO']
    for i in range(1, 21):
        n = f'SIM-OEM Customer {i:02d}'
        get_or_create('res.partner', n, [['name', '=', n]], {'name': n, 'is_company': True, 'category_id': [(6, 0, [tag])], 'comment': 'RC-9 demo customer (SIM)'})

def orders(confirm_n=None):
    L = ledger(); D = week_demand(); json.dump(D, open('week_demand.json', 'w'), indent=0)
    done = 0
    for ref, sku, f, q, day, cust in D:
        if ref in L.get('sale.order', {}): continue
        lot = S.LOT[f]; p = pid(sku)
        chunks = [lot] * (q // lot) + ([q % lot] if q % lot else [])
        release = WEEK0 + dt.timedelta(days=day)
        vals = {'partner_id': L['res.partner'][f'SIM-OEM Customer {cust:02d}'], 'client_order_ref': ref, 'company_id': CCS,
                'commitment_date': (release + dt.timedelta(hours=72)).strftime('%Y-%m-%d %H:%M:%S'),
                'note': 'SIM RC-9 demo order (week 1)',
                'order_line': [(0, 0, {'product_id': p['id'], 'product_uom_qty': c}) for c in chunks]}
        sid = x('sale.order', 'create', vals, context=NOMAIL); record('sale.order', ref, sid)
        x('sale.order', 'action_confirm', [sid], context=NOMAIL)
        print('SO', ref, sku, q, 'lines', len(chunks), flush=True)
        done += 1
        if confirm_n and done >= confirm_n: break

if __name__ == '__main__' and sys.argv[1] in ('stock', 'customers', 'orders1', 'orders'):
    {'stock': stock, 'customers': customers, 'orders1': lambda: orders(1), 'orders': orders}[sys.argv[1]]()
