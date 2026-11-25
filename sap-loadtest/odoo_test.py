"""RPC client for the cdrone TEST database only. Refuses any other host/db."""
import os, xmlrpc.client, http.client
URL = "https://cdrone-test.odoo.com"; DB = "cdrone-test"; USER = "mahisorn_w@cobrainter.com"
assert URL == "https://cdrone-test.odoo.com" and DB == "cdrone-test", "test db only"
KEY = os.environ["COBRA_DRONE_ODOO_API_KEY"]

class _T(xmlrpc.client.SafeTransport):
    timeout = 300
    def make_connection(self, host):
        c = super().make_connection(host); c.timeout = self.timeout; return c

common = xmlrpc.client.ServerProxy(URL + "/xmlrpc/2/common", transport=_T())
models = xmlrpc.client.ServerProxy(URL + "/xmlrpc/2/object", allow_none=True, transport=_T())
import time as _t
for _i in range(5):
    try: UID = common.authenticate(DB, USER, KEY, {}); break
    except OSError:
        if _i == 4: raise
        _t.sleep(20)
assert UID, "auth failed"
def x(model, method, *a, **k):
    return models.execute_kw(DB, UID, KEY, model, method, list(a), k)
