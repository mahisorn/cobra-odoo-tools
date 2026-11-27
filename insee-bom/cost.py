"""Ask Odoo to compute cost from BoM (button_bom_cost) on INSEE products only, bottom-up; read standard_price back."""
import json, xmlrpc.client
from odoo_insee import x, ledger, note
L = ledger(); T = L['created']['product.template']
order = ['INSEE-SKIN-LU', 'INSEE-SKIN-LL', 'INSEE-SKIN-RU', 'INSEE-SKIN-RL', 'INSEE-SPAR-SET', 'INSEE-WING-L', 'INSEE-WING-R', 'INSEE-SHIPSET']
for c in order:
    try: x('product.template', 'button_bom_cost', [T[c]], context={'allowed_company_ids': [1]})
    except xmlrpc.client.Fault as e:
        if 'marshal None' not in str(e) and 'cannot marshal' not in str(e): raise
out = {r['default_code']: r['standard_price'] for r in x('product.template', 'read', [T[c] for c in order], fields=['default_code', 'standard_price'])}
print(json.dumps(out, indent=1)); json.dump(out, open('odoo_cost.json', 'w'), indent=1)
