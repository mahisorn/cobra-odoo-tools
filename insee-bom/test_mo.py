"""Create ONE test MO for 1 INSEE shipset, confirm (MTO explodes child MOs), plan, then unreserve. Nothing is produced/consumed."""
import xmlrpc.client
from odoo_insee import x, ledger, record
CTX = {'allowed_company_ids': [1], 'tracking_disable': True, 'mail_notrack': True}
def call(model, m, ids):
    try: return x(model, m, ids, context=CTX)
    except xmlrpc.client.Fault as e:
        if 'cannot marshal' not in str(e): raise
L = ledger()
mo = L.get('created', {}).get('mrp.production', {}).get('TEST-SHIPSET-1')
if not mo:
    p = x('product.product', 'search', [['default_code', '=', 'INSEE-SHIPSET']])[0]
    mo = x('mrp.production', 'create', {'product_id': p, 'product_qty': 1, 'bom_id': L['created']['mrp.bom']['INSEE-SHIPSET'], 'company_id': 1,
                                         'origin': 'INSEE-TEST RC-10'}, context=CTX)
    record('created', 'mrp.production', 'TEST-SHIPSET-1', mo); call('mrp.production', 'action_confirm', [mo])
def tree(ids, depth=0, acc=None):
    acc = [] if acc is None else acc
    for m in x('mrp.production', 'read', ids, fields=['name', 'product_id', 'product_qty', 'state', 'date_start', 'date_finished', 'workorder_ids']):
        acc.append(m); print('  ' * depth, m['name'], m['product_id'][1][:40], m['product_qty'], m['state'], m['date_start'], '→', m['date_finished'], len(m['workorder_ids']), 'WO')
        kids = x('mrp.production', 'search', [['origin', '=', m['name']]])
        tree(kids, depth + 1, acc)
    return acc
allm = tree([mo])
allm = x('mrp.production', 'search_read', [['id', '>=', mo], ['product_id.default_code', 'like', 'INSEE-']], fields=['name', 'state', 'workorder_ids'])
for m in allm: record('created', 'mrp.production', m['name'], m['id'])
for m in reversed(allm):   # children first
    if m['state'] == 'confirmed' and m['workorder_ids']: call('mrp.production', 'button_plan', [m['id']])
for m in allm: call('mrp.production', 'do_unreserve', [m['id']])
print('--- after plan/unreserve')
allm = tree([mo])
wo = x('mrp.workorder', 'search_read', [['production_id', 'in', [m['id'] for m in allm]]], fields=['workcenter_id', 'duration_expected'])
import collections; c = collections.Counter(); [c.update({w['workcenter_id'][1][:10]: w['duration_expected']}) for w in wo]
print(len(wo), 'WOs', dict(c), sum(c.values()), 'min')
mv = x('stock.move', 'search_read', [['raw_material_production_id', 'in', [m['id'] for m in allm]]], fields=['product_id', 'product_uom_qty', 'quantity', 'state'])
print(len(mv), 'raw moves; reserved qty sum', sum(m['quantity'] for m in mv), set(m['state'] for m in mv))
