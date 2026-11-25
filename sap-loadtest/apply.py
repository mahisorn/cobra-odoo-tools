"""Apply step for load_sap.py (cdrone-test only). Sequential, >=1 s between calls, resumable, logged."""
import time, json, os, sys, socket, xmlrpc.client
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import odoo_test as T
from load_sap import NEW_UOMS
LOG = os.path.join(HERE, 'progress.jsonl')
NOMAIL = {'tracking_disable': True, 'mail_create_nolog': True, 'mail_notrack': True}
C1, C2 = 1, 2
_last = [0.0]

NETERR = (socket.timeout, TimeoutError, xmlrpc.client.ProtocolError, ConnectionError, OSError)

def call(model, method, *a, retry=True, **k):
    """One RPC at a time, >=1 s apart. Reads/idempotent writes retry on network errors; create does not."""
    for attempt in range(6):
        wait = 1.0 - (time.time() - _last[0])
        if wait > 0: time.sleep(wait)
        try: return T.x(model, method, *a, **k)
        except NETERR as e:
            if not retry or attempt == 5: raise
            log(event='net_retry', model=model, method=method, attempt=attempt + 1, err=str(e)[:200]); time.sleep(30)
        finally: _last[0] = time.time()

def log(**kw):
    kw['ts'] = time.strftime('%Y-%m-%d %H:%M:%S')
    with open(LOG, 'a') as f: f.write(json.dumps(kw, ensure_ascii=False) + '\n')
    print(json.dumps(kw, ensure_ascii=False), flush=True)

def ensure_uoms():
    have = {u['name']: u['id'] for u in call('uom.uom', 'search_read', [], fields=['name'], context={'active_test': False})}
    for name in NEW_UOMS.values():
        if name not in have:
            have[name] = call('uom.uom', 'create', {'name': name, 'relative_factor': 1.0, 'relative_uom_id': have['Units']})
            log(event='uom_created', name=name, id=have[name])
    return have

def ensure_categs(types):
    goods = call('product.category', 'search', [['complete_name', '=', 'Goods']])[0]
    def get(name, parent):
        r = call('product.category', 'search', [['name', '=', name], ['parent_id', '=', parent]])
        if r: return r[0]
        cid = call('product.category', 'create', {'name': name, 'parent_id': parent}); log(event='categ_created', name=name, id=cid); return cid
    root = get('Cobra SAP', goods)
    return root, {t: get(t, root) for t in sorted(types)}

def run(todo, batch):
    uoms = ensure_uoms(); root, cats = ensure_categs({r['mtyp'] for r in todo})
    log(event='start', records=len(todo), batch=batch)
    t0 = time.time(); i = 0; created_total = 0
    while i < len(todo):
        chunk = todo[i:i + batch]; codes = [r['default_code'] for r in chunk]
        exist = {p['default_code'] for p in call('product.product', 'search_read', [['default_code', 'in', codes]],
                                                   fields=['default_code'], context={'active_test': False})}
        new = [r for r in chunk if r['default_code'] not in exist]
        if not new: i += len(chunk); continue
        vals = [{'name': r['name'], 'default_code': r['default_code'], 'type': 'consu', 'is_storable': True,
                 'tracking': False, 'company_id': False, 'categ_id': cats[r['mtyp']], 'uom_id': uoms[r['uom']],
                 'standard_price': r['standard_price']} for r in new]
        tb = time.time()
        try:
            tids = call('product.template', 'create', vals, retry=False, context=dict(NOMAIL, allowed_company_ids=[C1]))
        except NETERR as e:
            log(event='create_error', at=i, batch=batch, err=str(e)[:300])
            if batch > 500: batch = 500; time.sleep(30); continue  # re-check existing, retry smaller
            raise
        dt = time.time() - tb
        prods = call('product.product', 'search_read', [['product_tmpl_id', 'in', tids]], fields=['default_code'])
        price = {r['default_code']: r['standard_price'] for r in new}
        pv = [(p['id'], price[p['default_code']]) for p in prods if price.get(p['default_code'])]
        if pv:
            call('product.product', 'web_save_multi', [p for p, _ in pv], [{'standard_price': v} for _, v in pv],
                 specification={}, context=dict(NOMAIL, allowed_company_ids=[C2]))
        created_total += len(tids); i += len(chunk)
        log(event='batch', at=i, created=len(tids), create_s=round(dt, 1), per_s=round(len(tids) / dt, 1),
            total=created_total, elapsed_s=round(time.time() - t0))
    log(event='done', created=created_total, elapsed_s=round(time.time() - t0))

def fix_costs(recs):
    """Ensure cost on both companies for every planned code (covers crash between create and company-2 write)."""
    price = {r['default_code']: r['standard_price'] for r in recs}
    root = call('product.category', 'search', [['name', '=', 'Cobra SAP'], ['parent_id.name', '=', 'Goods']])
    if not root: return
    for cid in (C1, C2):
        off = 0; fixed = 0
        while True:
            ps = call('product.product', 'search_read', [['categ_id', 'child_of', root[0]]], fields=['default_code', 'standard_price'],
                      offset=off, limit=20000, order='id', context={'allowed_company_ids': [cid], 'active_test': False})
            if not ps: break
            off += len(ps)
            bad = [(p['id'], price[p['default_code']]) for p in ps if p['default_code'] in price and abs(p['standard_price'] - price[p['default_code']]) > 0.005]
            for k in range(0, len(bad), 1000):
                b = bad[k:k + 1000]
                call('product.product', 'web_save_multi', [p for p, _ in b], [{'standard_price': v} for _, v in b],
                     specification={}, context=dict(NOMAIL, allowed_company_ids=[cid]))
            fixed += len(bad)
        log(event='fix_costs', company=cid, checked=off, fixed=fixed)
