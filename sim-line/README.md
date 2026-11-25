# sim-line (RC-9)

Simulated high-mix / low-volume drone line on **cdrone-test only** (Odoo 20 Enterprise trial). Plan: `PLAN.md`.
Approved by Chang 25 Nov 2026 10:54 ICT: comfortable sizing (65 labour stations, 1 shift Mon–Fri 08:00–16:00, no OT),
shared composite shop + Line A (quad) / Line B (hexa, VTOL, interceptor), batch rule (QX4 ≤4, HX6/INT ≤2, VT2 1),
components stocked up front, serial tracking on the 10 finished SKUs, Product Unit precision 3, MTO route active, 1-week run.
All times, costs and the family mix are ASSUMPTIONS; raw materials are real SAP codes reused unchanged; electronics are SIM placeholders.

| File | Purpose |
|---|---|
| `model.py` | capacity + lead-time model behind PLAN.md |
| `spec.py` | work-centre types, station counts per line, minutes per op, BoM content, SKUs |
| `odoo_sim.py` | paced RPC (≥1 s, one call in flight) via `../sap-loadtest/odoo_test.py` (refuses anything but cdrone-test); `created_ids.json` ledger |
| `build.py` | stages `setup`, `wc`, `products`, `boms`, `stock`, `customers`, `orders1`, `orders` (idempotent through the ledger) |
| `plan.py` | MO tree helper (SO → FG MO → AF/HAR/PRP/AVI → LAM) |
| `sched.py` | finite-capacity scheduler that writes station + dates onto every SIM work order (see deviations); `--write` |
| `verify.py` | reads the week back: counts, lead times, lateness, load per work-centre group |
| `diagram/candidate.json` | Archify source of the line diagram |

Run order: `build.py setup → wc → products → boms → stock → customers → orders`, then `sched.py --write`, then `verify.py`.

## Deviations from a plain Odoo setup
- **Planning:** Odoo 20's Plan button always schedules from "now" and does not wait for child MOs, so `sched.py` applies the same rules
  (station calendars, alternatives = earliest finish, capacity per cycle, efficiency, setup/cleanup, child MOs before parent) and writes
  `workcenter_id`, `date_start`, `date_finished`, `duration_expected` to each work order. Odoo then shows it in its Gantt/load views.
- **Batch ovens/racks:** Odoo runs one work order per work centre at a time, so the 2 ovens are 6 zones of 4 sets and the rack is 4 zones of 10.
  Total work centres 75 (65 labour + 10 zones).
- **One laminate set per family** (instead of one MO per laminate) to keep the oven model honest.
- **MTO** splits per sale-order line, so order lines are pre-split to the batch rule.
- **2-person cells** use Odoo capacity lines (capacity 2 per product) with the work centre's setup/cleanup copied onto them.
- Settings changed outside SIM objects (approved): Product Unit precision 2→3, MTO route + its Stock→Customers rule active. Recorded in `_changed_settings`.

## Undo (test only)
Ledger `created_ids.json` (not committed). Reverse order: unplan + cancel SIM MOs and the 25 SOs, delete them; reverse the stock
adjustment (quants in the ledger); archive SIM products, BoMs, work centres (capacity lines go with them); delete DEMO partners,
SIM categories, SIM 24/7 calendar, tags; re-archive MTO route/rule; precision may stay 3. The trial expiry (3 Dec 2026) also removes everything.
