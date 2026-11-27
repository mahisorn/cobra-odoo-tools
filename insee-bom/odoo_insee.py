"""Paced RPC for cdrone-test ONLY + INSEE ledger (created vs reused) for undo."""
import os, sys, time, json, socket, xmlrpc.client
HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(HERE, '..', 'sap-loadtest'), '/workspace/cobra/cobra-semi-parts/loadtest'):
    sys.path.insert(0, _p)
import odoo_test as T                      # asserts URL/DB == cdrone-test
assert T.DB == 'cdrone-test' and T.URL == 'https://cdrone-test.odoo.com'
LEDGER = os.environ.get('INSEE_LEDGER', '/workspace/cobra/chindanai-sheet/created_ids.json')
_last = [0.0]
def x(model, method, *a, **k):
    for attempt in range(4):
        w = 1.0 - (time.time() - _last[0])
        if w > 0: time.sleep(w)
        try: return T.x(model, method, *a, **k)
        except (socket.timeout, TimeoutError, ConnectionError, xmlrpc.client.ProtocolError) as e:
            if attempt == 3 or method not in ('search', 'search_read', 'read', 'search_count', 'fields_get'): raise
            print('retry', model, method, e, flush=True); time.sleep(20)
        finally: _last[0] = time.time()
def ledger(): return json.load(open(LEDGER)) if os.path.exists(LEDGER) else {}
def _save(L): json.dump(L, open(LEDGER, 'w'), indent=1, ensure_ascii=False)
def record(kind, model, key, rid):
    L = ledger(); L.setdefault(kind, {}).setdefault(model, {})[key] = rid; _save(L)
def note(key, val):
    L = ledger(); L.setdefault('_notes', {})[key] = val; _save(L)
def get_or_create(model, key, domain, vals, ctx=None):
    L = ledger()
    for kind in ('created', 'reused'):
        if key in L.get(kind, {}).get(model, {}): return L[kind][model][key]
    r = x(model, 'search', domain, context=dict(ctx or {}, active_test=False))
    if r: record('reused', model, key, r[0]); return r[0]
    rid = x(model, 'create', vals, context=ctx or {}); record('created', model, key, rid); print('created', model, key, rid, flush=True); return rid
