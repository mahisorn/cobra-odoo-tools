"""Paced RPC for cdrone-test ONLY + created-id ledger for undo."""
import os, sys, time, json, socket, xmlrpc.client
for _p in (os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'sap-loadtest'), '/workspace/cobra/cobra-semi-parts/loadtest'):
    sys.path.insert(0, _p)
import odoo_test as T                      # asserts URL/DB == cdrone-test
assert T.DB == 'cdrone-test'
HERE = os.path.dirname(os.path.abspath(__file__)); LEDGER = os.path.join(HERE, 'created_ids.json')
_last = [0.0]
def x(model, method, *a, **k):
    for attempt in range(4):
        w = 1.0 - (time.time() - _last[0])
        if w > 0: time.sleep(w)
        try: return T.x(model, method, *a, **k)
        except (socket.timeout, TimeoutError, ConnectionError, xmlrpc.client.ProtocolError) as e:
            if attempt == 3 or method in ('create', 'action_confirm', 'button_plan'): raise
            print('retry', model, method, e, flush=True); time.sleep(20)
        finally: _last[0] = time.time()
def ledger():
    return json.load(open(LEDGER)) if os.path.exists(LEDGER) else {}
def record(model, key, rid, note=''):
    L = ledger(); L.setdefault(model, {})[key] = rid
    json.dump(L, open(LEDGER, 'w'), indent=1, ensure_ascii=False)
def changed(key, before, after):
    L = ledger(); L.setdefault('_changed_settings', {})[key] = {'before': before, 'after': after}
    json.dump(L, open(LEDGER, 'w'), indent=1, ensure_ascii=False)
def get_or_create(model, key, domain, vals, ctx=None):
    L = ledger()
    if key in L.get(model, {}): return L[model][key]
    r = x(model, 'search', domain, context=dict(ctx or {}, active_test=False))
    if r: record(model, key, r[0]); return r[0]
    rid = x(model, 'create', vals, context=ctx or {}); record(model, key, rid); print('created', model, key, rid, flush=True); return rid
