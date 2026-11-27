"""READ-ONLY snapshot of products from cdrone (prod) or cdrone-test. Only search_read/read are allowed."""
import os, sys, json, time, xmlrpc.client
TARGETS = {"prod": ("https://cdrone.odoo.com", "cdrone"), "test": ("https://cdrone-test.odoo.com", "cdrone-test")}
USER = "mahisorn_w@cobrainter.com"
ALLOWED = {"search_read", "search_count", "read", "fields_get"}
which = sys.argv[1]; URL, DB = TARGETS[which]; KEY = os.environ["COBRA_DRONE_ODOO_API_KEY"]
class _T(xmlrpc.client.SafeTransport):
    def make_connection(self, h):
        c = super().make_connection(h); c.timeout = 300; return c
common = xmlrpc.client.ServerProxy(URL + "/xmlrpc/2/common", transport=_T())
models = xmlrpc.client.ServerProxy(URL + "/xmlrpc/2/object", allow_none=True, transport=_T())
UID = common.authenticate(DB, USER, KEY, {}); assert UID, "auth failed"
def x(model, method, *a, **k):
    assert method in ALLOWED, "read-only"
    time.sleep(1.0); return models.execute_kw(DB, UID, KEY, model, method, list(a), k)
F = ["id", "default_code", "name", "categ_id", "uom_id", "standard_price", "list_price", "type", "active", "product_tmpl_id"]
n = x("product.product", "search_count", [["active", "in", [True, False]]]); print(which, "products", n)
out = []; off = 0; step = 20000 if which == "test" else 5000
while off < n:
    out += x("product.product", "search_read", [["active", "in", [True, False]]], fields=F, offset=off, limit=step, order="id"); off += step
    print(" read", len(out), flush=True)
cats = x("product.category", "search_read", [], fields=["id", "complete_name"])
json.dump({"products": out, "categories": cats}, open(f"snap_{which}.json", "w"), ensure_ascii=False)
print("saved", len(out))
