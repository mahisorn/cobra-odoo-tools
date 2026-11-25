import time, sys, xmlrpc.client, os
sys.path.insert(0, '.')
import odoo_test as T
x = T.x
print('uid', T.UID, T.common.version()['server_version'])
print('user', x('res.users','read',[T.UID],fields=['name','login','company_ids','company_id']))
print('companies', x('res.company','search_read',[],fields=['name','currency_id']))
ctx={'active_test':False}
for m in ['product.template','product.product']:
    print(m,'all',x(m,'search_count',[],context=ctx),'active',x(m,'search_count',[]))
print('cats', [(c['id'],c['complete_name'],c['product_count']) for c in x('product.category','search_read',[['complete_name','ilike','Goods']],fields=['complete_name','product_count'])])
last=x('product.template','search_read',[],fields=['default_code','write_date','create_date'],order='create_date desc',limit=3,context=ctx); print('latest tmpl',last)
for p in ['database.uuid','database.create_date','database.expiration_date','database.enterprise_code','web.base.url']:
    try: print(p, x('ir.config_parameter','get_param',p) if p!='database.uuid' else x('ir.config_parameter','get_param',p)[:8]+'…')
    except Exception as e: print(p,'n/a',str(e)[-80:])
print('uoms',[(u['id'],u['name']) for u in x('uom.uom','search_read',[],fields=['name'],context=ctx)])
print('precision',x('decimal.precision','search_read',[],fields=['name','digits']))
print('tmpl fields has is_storable', 'is_storable' in x('product.template','fields_get',attributes=['type']))
print('type sel', x('product.template','fields_get',['type'],attributes=['selection']))
mods=x('ir.module.module','search_read',[['state','=','installed'],['name','in',['stock','mrp','purchase','product_expiry','stock_account','account','sale']]],fields=['name']); print('mods',[m['name'] for m in mods])
# timing: read codes
t=time.time(); ids=x('product.product','search',[],context=ctx); t1=time.time()-t
t=time.time(); r=x('product.product','read',ids[:2000],fields=['default_code']); t2=time.time()-t
print(f'search {len(ids)} ids {t1:.2f}s; read {len(r)} codes {t2:.2f}s')
t=time.time(); r=x('product.product','search_read',[['default_code','in',[str(12000000+i) for i in range(5000)]]],fields=['default_code'],context=ctx); print(f'search_read 5000-code IN filter: {len(r)} hits {time.time()-t:.2f}s')
