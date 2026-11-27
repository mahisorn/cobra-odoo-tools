"""Read back INSEE BoMs + Odoo's own BoM cost (report.mrp.report_bom_structure.get_html, read-only)."""
import json
from odoo_insee import x, ledger
import spec as S
L = ledger(); B = L['created']['mrp.bom']
for code, bid in B.items():
    b = x('mrp.bom', 'read', [bid], fields=['bom_line_ids', 'operation_ids', 'company_id'])[0]
    ln = x('mrp.bom.line', 'read', b['bom_line_ids'], fields=['product_id', 'product_qty', 'product_uom_id'] if False else ['product_id', 'product_qty'])
    op = x('mrp.routing.workcenter', 'read', b['operation_ids'], fields=['name', 'workcenter_id', 'time_cycle_manual'])
    print(code, bid, b['company_id'][1][:12], [(l['product_id'][1][:28], l['product_qty']) for l in ln], sum(o['time_cycle_manual'] for o in op), 'min')
r = x('report.mrp.report_bom_structure', 'get_html', B['INSEE-SHIPSET'], 1, False)
json.dump(r, open('bom_report.json', 'w'), default=str, indent=1)
d = r.get('lines', r)
def show(n, depth=0):
    print('  ' * depth, n.get('name', '')[:50], n.get('quantity'), n.get('uom_name', ''), 'bom_cost', round(n.get('bom_cost', 0) or 0, 2), 'prod_cost', round(n.get('prod_cost', 0) or 0, 2))
    for c in n.get('components', []) or []: show(c, depth + 1)
    for o in (n.get('operations', []) or []) if depth == 0 else []: pass
show(d)
print('operations top', d.get('operations_cost'), 'total bom_cost', d.get('bom_cost'))
