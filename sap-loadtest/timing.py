"""Time common read operations on cdrone-test after the load (median of 3 runs, includes ~0.3 s network)."""
import time, statistics, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import odoo_test as T
x = T.x
def t(label, fn, n=3):
    ts = []
    for _ in range(n):
        a = time.time(); r = fn(); ts.append(time.time() - a); time.sleep(1)
    print(f'{label:55s} median {statistics.median(ts):6.2f}s  (min {min(ts):.2f}, max {max(ts):.2f})  result={r}')
t('ping (version)', lambda: T.common.version()['server_version'])
t('count all products', lambda: x('product.product', 'search_count', []))
t('search by exact code =', lambda: len(x('product.product', 'search_read', [['default_code', '=', '24008612']], fields=['name'])))
t('search code ilike "2400861"', lambda: len(x('product.product', 'search_read', [['default_code', 'ilike', '2400861']], fields=['name'], limit=80)))
t('search name ilike "hinge" (limit 80)', lambda: len(x('product.product', 'search_read', [['name', 'ilike', 'hinge']], fields=['name'], limit=80)))
t('search name ilike "hinge" count', lambda: x('product.product', 'search_count', [['name', 'ilike', 'hinge']]))
t('search name ilike rare "WOODPELLET"', lambda: len(x('product.product', 'search_read', [['name', 'ilike', 'WOODPELLET']], fields=['name'], limit=80)))
LIST = ['default_code', 'name', 'list_price', 'standard_price', 'categ_id', 'uom_id', 'qty_available', 'virtual_available']
t('product list view: search_read 80 (default order)', lambda: len(x('product.template', 'search_read', [], fields=LIST, limit=80)))
t('product list view: category ZRM filter, 80', lambda: len(x('product.template', 'search_read', [['categ_id.name', '=', 'ZRM']], fields=LIST, limit=80)))
t('product list view: page 1000 (offset 80k)', lambda: len(x('product.template', 'search_read', [], fields=LIST, limit=80, offset=80000)))
t('list grouped by category (read_group)', lambda: len(x('product.template', 'read_group', [], ['categ_id'], ['__count'])))
t('BoM component name_search "resin"', lambda: len(x('product.product', 'name_search', 'resin', [['type', '=', 'consu']], 'ilike', 8)))
t('BoM component name_search "1220104"', lambda: len(x('product.product', 'name_search', '1220104', [['type', '=', 'consu']], 'ilike', 8)))
t('stock.quant search_read (inventory report)', lambda: len(x('stock.quant', 'search_read', [['location_id.usage', '=', 'internal']], fields=['product_id', 'quantity', 'value'], limit=80)))
t('product qty_available for 80 products', lambda: len(x('product.product', 'search_read', [['categ_id.name', '=', 'ZRM']], fields=['qty_available', 'virtual_available'], limit=80)))
