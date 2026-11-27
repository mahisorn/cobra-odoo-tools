"""Build INSEE wing test structure on cdrone-test ONLY. Idempotent via ledger. Usage: build.py [setup|products|boms|all]"""
import sys, json
from odoo_insee import x, get_or_create, record, note, ledger
import spec as S
CCS = 1   # COBRA COMPOSITE STRUCTURES CO., LTD. = company of RC-9 SIM data and of the only warehouse (cdrone, WH/Stock)
NOMAIL = {'tracking_disable': True, 'mail_create_nolog': True, 'mail_notrack': True, 'allowed_company_ids': [CCS]}
MTO = 1; CAL8 = 4

def setup():
    tag = get_or_create('mrp.workcenter.tag', 'INSEE', [['name', '=', 'INSEE']], {'name': 'INSEE'})
    goods = 1
    root = get_or_create('product.category', 'INSEE Test', [['name', '=', 'INSEE Test'], ['parent_id', '=', goods]], {'name': 'INSEE Test', 'parent_id': goods})
    for c in ('Semi', 'Finished', 'Placeholder TBC'):
        get_or_create('product.category', f'INSEE Test/{c}', [['name', '=', c], ['parent_id', '=', root]], {'name': c, 'parent_id': root})
    for code, (name, cost) in S.WC.items():
        get_or_create('mrp.workcenter', code, [['code', '=', code]],
                      {'name': f'{code} {name}', 'code': code, 'company_id': CCS, 'costs_hour': cost, 'employee_costs_hour': 0.0,
                       'time_start': 0, 'time_stop': 0, 'time_efficiency': 100, 'tag_ids': [(6, 0, [tag])],
                       'resource_calendar_id': CAL8, 'tz': 'Asia/Bangkok'}, ctx=NOMAIL)

def pid(code):  # product.product id for code
    r = x('product.product', 'search_read', [['default_code', '=', code]], fields=['id', 'product_tmpl_id', 'uom_id', 'standard_price'], context={'active_test': False})
    assert len(r) == 1, (code, r); return r[0]

def products():
    L = ledger(); cat = L['created']['product.category'] if 'INSEE Test' in L.get('created', {}).get('product.category', {}) else L['reused']['product.category']
    raw = {}
    for code in S.RAW:  # must already exist from the RC-8 SAP load; reuse, do not modify
        p = pid(code); record('reused', 'product.product', code, p['id']); raw[code] = p
        print('reuse', code, p['uom_id'][1], p['standard_price'])
    for code, t in S.TBC.items():
        get_or_create('product.template', code, [['default_code', '=', code]],
                      {'name': t['name'], 'default_code': code, 'type': 'consu', 'is_storable': True, 'company_id': False, 'categ_id': cat['INSEE Test/Placeholder TBC'],
                       'standard_price': t['cost'], 'purchase_ok': True, 'sale_ok': False, 'description_purchase': t['note'], 'description': t['note']}, ctx=NOMAIL)
    for code, (name, _) in S.SEMI.items():
        fin = code == 'INSEE-SHIPSET'
        get_or_create('product.template', code, [['default_code', '=', code]],
                      {'name': name, 'default_code': code, 'type': 'consu', 'is_storable': True, 'company_id': False,
                       'categ_id': cat['INSEE Test/Finished' if fin else 'INSEE Test/Semi'], 'standard_price': 0.0, 'route_ids': [(6, 0, [MTO])],
                       'sale_ok': fin, 'purchase_ok': False,
                       'description': 'INSEE wing TEST build (RC-10, cdrone-test only) from BOM INSEE REV.0.xlsx; quantities inferred, see insee-bom/README.md'}, ctx=NOMAIL)
    note('DP8710', '24020685 UoM is ml in SAP/Odoo but 1080 THB looks per 45 ml tube; BoM qty entered as tubes (0.6 per wing) against the ml UoM - fix UoM before real use')

def boms():
    L = ledger(); wc = {**L.get('reused', {}).get('mrp.workcenter', {}), **L.get('created', {}).get('mrp.workcenter', {})}
    order = ['INSEE-SKIN-LU', 'INSEE-SKIN-LL', 'INSEE-SKIN-RU', 'INSEE-SKIN-RL', 'INSEE-SPAR-SET', 'INSEE-WING-L', 'INSEE-WING-R', 'INSEE-SHIPSET']
    for code in order:
        p = pid(code); lines = []
        for comp, q in S.SEMI[code][1]:
            c = pid(comp); lines.append((0, 0, {'product_id': c['id'], 'product_qty': q}))
        ops = [(0, 0, {'name': n, 'workcenter_id': wc[w], 'time_mode': 'manual', 'time_cycle_manual': m, 'sequence': (i + 1) * 10})
               for i, (n, w, m) in enumerate(S.OPS.get(code, []))]
        get_or_create('mrp.bom', code, [['product_tmpl_id', '=', p['product_tmpl_id'][0]], ['code', '=', 'INSEE-TEST']],
                      {'product_tmpl_id': p['product_tmpl_id'][0], 'product_qty': 1, 'type': 'normal', 'company_id': CCS, 'code': 'INSEE-TEST',
                       'bom_line_ids': lines, 'operation_ids': ops}, ctx=NOMAIL)

if __name__ == '__main__':
    st = sys.argv[1] if len(sys.argv) > 1 else 'all'
    for name, fn in (('setup', setup), ('products', products), ('boms', boms)):
        if st in (name, 'all'): print('==', name, flush=True); fn()
