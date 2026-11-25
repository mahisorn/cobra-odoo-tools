# RC-9 — Simulated drone line + demo BoMs on cdrone-test (plan; approved 25 Nov 2026 10:54 ICT: comfortable 65 stations, 1-week run — see README for build deviations)
25 Nov 2026 ICT · target **cdrone-test only** (Odoo 20.0+e trial, expires 3 Dec 2026 17:02 ICT) · production cdrone untouched · no Odoo writes yet.
Model: `model.py` (numbers below are its output, `model_output.txt`); demand sample `demand.json`.
Legend: **REAL** = read from cdrone-test / Cobra data · everything else = **ASSUMPTION** (edit `model.py` and re-run).

## 0. What cdrone-test has today (read-only probe, REAL)
- Installed: mrp, mrp_workorder (shop floor + tablet timer on), work orders/routings ON, by-products ON, mrp_mps, quality / quality_control / quality_mrp, planning, project, hr, sale_mrp, purchase_mrp, mrp_account, mrp_subcontracting, web_gantt. **Not installed:** mrp_plm, maintenance.
- Companies: 1 CCS, 2 COBRA INTERNATIONAL (THB). One warehouse `cdrone` (WH, CCS, manufacture 1 step).
- Calendars: "Work Center 40 hours/week" (Mon–Fri 08:00–16:00, 8 h), two "40 hours/week" (per company), "Appointment Resource Default Calendar" (24 h). No 24/7 work-centre calendar.
- Work centres: `Laminate` (125 THB/h) and `Laminate - drone` (145 THB/h), both CCS. BoMs: 2 (Skin Set; 12201047 Merops skin upper with 1 op "Laminate skin" 40 min). MOs 0, SOs 3 (real customers), 225 partners.
- Routes: MTO route exists but **archived**; Manufacture, Buy active.
- Products: 257,961 SAP materials under Goods/Cobra SAP. Real composite raw materials with SAP cost are available (table §2). **No drone electronics in SAP** (motors/ESC/FC/GPS/batteries) → SIM placeholders.
- Odoo 20 behaviour that shapes the design: a work centre runs one work order at a time; "capacity" = units per cycle (a 2-person cell or 2-part fixture = capacity 2); parallel stations = separate work centres linked as **alternative work centres** (planner picks the first free one). Work orders of one MO run in sequence, so MO lot size drives lead time.
- Product Unit precision in **cdrone-test is still 2 decimals** (prod is 3) → 0.263 kg hardener would round to 0.26.

## 1. Work centres (14 types) — ASSUMPTIONS
Labour WCs on the REAL "Work Center 40 hours/week" calendar (1 shift 08–16). Passive WCs (cure/dry) on a new 24/7 calendar so cures run overnight (calendar time, no labour).

| Code | Work centre | Cap/cycle | Eff % | Setup+cleanup min/WO | THB/h (station) | Stations, comfortable (≤90%, no OT) | Stations, lean (1 shift + OT ≤1 h/day) | Lean OT h/day/station |
|---|---|---|---|---|---|---|---|---|
| LAY | Composite layup & vacuum bag (2-person cell) | 2 | 90 | 15+15 | 290 | 7 | 6 | 0.0 |
| CUR | Cure oven, batch 12 airframe sets, 4 h cycle (24/7) | 12 | 100 | 20+10 | 300 | 2 ovens | 2 ovens | n/a |
| CNC | CNC trim & drill | 1 | 95 | 20+10 | 450 | 6 | 5 | 0.13 |
| BND | Bonding & structural assembly (2 fixtures) | 2 | 90 | 15+10 | 300 | 5 | 4 | 0.33 |
| RCK | Bond-cure / paint-dry rack, 40 slots (24/7) | 40 | 100 | 0 | 10 | 1 | 1 | n/a |
| PNT | Surface prep & paint booth (2 parts/booth) | 2 | 90 | 20+20 | 500 | 5 | 4 | 0.0 |
| HAR | Wiring harness | 1 | 90 | 10+5 | 150 | 9 | 8 | 0.0 |
| PRP | Motor & propulsion assembly | 1 | 90 | 10+5 | 150 | 6 | 5 | 0.0 |
| AVI | Avionics integration | 1 | 90 | 10+5 | 200 | 8 | 6 | **0.53** |
| FAS | Final assembly (2-person cell) | 2 | 90 | 15+10 | 300 | 6 | 5 | 0.12 |
| CAL | Calibration & firmware (2 jigs) | 2 | 95 | 10+0 | 200 | 2 | 2 | 0.0 |
| TST | Functional & flight test (2 bays) | 2 | 90 | 15+10 | 600 | 4 | 3 | 0.0 |
| QC | Final QC inspection | 1 | 95 | 5+5 | 200 | 3 | 2 | **0.87** |
| PCK | Packing | 1 | 95 | 10+10 | 120 | 4 | 3 | 0.0 |
| | **Total labour stations** | | | | | **65** | **53** | |

THB/h reference: REAL test-db laminate WCs are 125–145 THB/h per operator; 2-person cells are priced ×2. Machine WCs (CNC, oven, booth, test range) include equipment.

## 2. Demo drone families & SKUs (10 finished SKUs) — ASSUMPTIONS
| Family | SKUs | Mix | Labour min/unit | Structure |
|---|---|---|---|---|
| QX4 quad, 2–5 kg class | SIM-QX4-STD, SIM-QX4-THM (thermal), SIM-QX4-MAP (mapping) | 45% | 440 | 4 arm + 1 body laminates |
| HX6 hexa heavy-lift | SIM-HX6-AG10 (10 L spray), SIM-HX6-AG30 (30 L), SIM-HX6-LOG (delivery) | 25% | 705 | 6 arm + body laminates |
| VT2 VTOL fixed-wing | SIM-VT2-SRV (survey), SIM-VT2-LR (long range) | 15% | 835 | wing, fuselage, tail laminates |
| INT interceptor (structure modelled on the REAL Merops RJ2 flow: skin → CNC skin → laminate → glass/resin/hardener/pigment) | SIM-INT-STD, SIM-INT-EXT | 15% | 540 | upper/lower/main skin laminates |

BoM levels (same pattern per family):
```
L0  SIM-<SKU>                 ops: FAS → CAL → TST → QC → PCK
L1  SIM-<FAM>-AF  airframe    ops: CNC → BND → RCK(bond cure 120 min) → PNT → RCK(paint dry 90 min)
L2    SIM-<FAM>-LAM-*  laminates   ops: LAY → CUR(240 min oven)
L3      raw: REAL SAP codes (below)
L1  SIM-<FAM>-HAR harness (HAR) · SIM-<FAM>-PRP propulsion (PRP) · SIM-<SKU>-AVI avionics incl. payload (AVI)
L2    SIM purchased placeholders: motors, ESCs, props, FC, GPS, radio, payloads, wire/connector kits
L1  SIM battery pack (buy) + packing: REAL carton/foam/bubble
```
Minutes per op per unit (labour; CUR/RCK = cycle duration):

| Op | QX4 | HX6 | VT2 | INT |
|---|---|---|---|---|
| LAY | 60 | 120 | 150 | 90 |
| CUR (oven cycle) | 240 | 240 | 240 | 240 |
| CNC | 30 | 45 | 60 | 40 |
| BND | 45 | 75 | 90 | 60 |
| RCK bond cure / paint dry | 120 / 90 | 120 / 90 | 120 / 90 | 120 / 90 |
| PNT | 30 | 45 | 60 | 45 |
| HAR | 60 | 90 | 90 | 45 |
| PRP | 30 | 60 | 45 | 30 |
| AVI | 45 | 60 | 75 | 60 |
| FAS | 60 | 90 | 120 | 75 |
| CAL | 20 | 30 | 30 | 25 |
| TST | 30 | 45 | 60 | 30 |
| QC | 15 | 20 | 25 | 20 |
| PCK | 15 | 25 | 30 | 20 |

REAL SAP raw materials to reuse (code, name, UoM, SAP cost THB):
- 14001386 GLASS CLOTH 200 GR/SQM ×1000 mm, m, 19.55 · 14001821 EPOXY RESIN SR 1280, kg, 197.45 · 14001576 HARDENER SD 4993(CB), kg, 385.14 · 24019690 PIGMENT BLUE, kg, 2,900 — INT laminate recipe copied from RC-7 Merops laminate (4 plies × 2.32–2.43 m glass, 0.75 kg resin, 0.263 kg hardener, 0.025 kg pigment).
- 14000031 Carbon 205 gsm twill T300, m², 465 · 14001685 PVC FOAM H80 5 mm, m², 963.03 · 15002649 PEEL PLY 70 g, m², 13.73 · 14003507 vacuum bagging film 48", m², 35.02 (QX4/HX6/VT2 laminates; quantities ASSUMED).
- 24010253 PLEXUS MA 425 490 ml, Units, 1,086 (bonding) · 14001908 SS316 screw D4.2×9.5, Units, 5.24 · 14001069 Primer 108400, kg, 454.78 · 14002652 PAINT PU NX 194 WHITE, kg, 2,092.24.
- Packing: 24007572 CARTON BOX 1000×600×550, Units, 80 · 24008369 WHITE EPE FOAM 2 mm, m, 4.60 · 24001823 Air Bubble 1.3 m, m, 3.25 (REAL RC-7 packing materials).

## 3. Capacity verdict (1,000 units/month, 22 days × 8 h = 176 h/station)
- Total load ≈ 9,250 station-hours ≈ 13,400 operator-hours/month (≈ 76 operator FTE at 100%, ~84 at 90%).
- **1 shift is enough at 1,000/month if the line has parallel stations; no 2nd shift needed.**
  - Comfortable set: **65 stations**, every WC ≤ 90% utilised, **0 OT**.
  - Lean set: **53 stations**, OT only on 5 WCs, max **0.87 h/day/station (QC)**, then AVI 0.53, BND 0.33, CNC 0.13, FAS 0.12 → all within 1 h/day (≤12.5%).
- Bottleneck (lean set): QC → AVI → BND. Ceiling of the lean set at 1 shift + 1 h OT: QC ~1,015 units/month, AVI ~1,055, BND ~1,080, CNC/FAS ~1,105, LAY ~1,120.
- **When 2 shifts become unavoidable:** only when a WC cannot get another station (floor space, capex, staff, or a single test range). With the lean set, 1 shift + 1 h OT tops out at **~1,015 units/month**; above that add 1 QC station (→ ~1,050, then AVI binds). If stations can keep being added, 1 shift holds; the hard limits are ovens (2 ovens × 3 loads/day incl. one overnight ≈ 1,580 units/month) and a single outdoor flight-test range/daylight.
- Cure is calendar time: 2 ovens, 83 loads/month (12 sets/load), loads at ~08:00, ~12:30 and 16:00 (overnight). Rack holds bond-cure and paint-dry 24/7.
- Lead time (critical path, labour Mon–Fri 08–16, cures overnight, no queue): lot 1–2 → **57–62 h** (VT2 lot 2: 81 h); QX4 lot 4 → 64 h; lot 6 → 87–203 h. **Rule: MO lot ≤4 for QX4, ≤2 for HX6/VT2/INT** (VT2 lot 1 for strict 72 h). Queues at 80–90% load add roughly 0.5–1 day, so 48–72 h holds for small lots, not for 20–60 unit orders as one MO.
- Parallel lines option (Chang: OK): keep a shared composite shop (LAY/CUR/CNC/BND/PNT) and split assembly into (indicative split, to re-check per line) **Line A = QX4** (HAR 4, PRP 3, AVI 3, FAS 2, CAL 1, TST 1, QC 1, PCK 1) and **Line B = HX6/VT2/INT** (HAR 4, PRP 2, AVI 3, FAS 3, CAL 1, TST 2, QC 1, PCK 2). Same 53 stations, fewer changeovers; in Odoo each line's stations are alternatives of each other only.

## 4. Demand simulation
- 100 OEM orders/month, avg ~10 units, mix by order size: 1–2 units 30%, 3–5 25%, 6–10 20%, 11–20 15%, 21–60 10%. Sample (seed 7): 100 orders, 991 units; 32 / 27 / 15 / 13 / 13 orders per bucket; by SKU QX4-STD 185, -THM 178, -MAP 194, HX6-AG10 53, -AG30 74, -LOG 65, VT2-SRV 84, -LR 25, INT-STD 36, -EXT 97.
- Customers: 20 demo partners `SIM-OEM Customer 01–20`, partner tag **DEMO**.
- Orders: **sale orders** (shows the real flow SO → MTO → MO → child MOs), commitment dates spread over the month, order lines split into lots (≤4 / ≤2) so MOs follow the lot rule → ~393 FG MOs/month, ≈2,500 MOs incl. children, ≈6,000 work orders (also a good load test).
- Routes: un-archive MTO; SIM finished/semi products = Manufacture + MTO; purchased placeholders + REAL raw = **stocked** via one inventory adjustment (recommended, MOs are ready so the sim shows capacity, not purchasing). Alternative: Buy route + SIM vendor with 5-day lead (adds ~hundreds of RFQs).
- Planning: script confirms SOs, then Plan on MOs (work orders scheduled on WC calendars, alternatives used).
- Where Chang looks: Manufacturing → Planning → Work Orders Gantt (by work centre), Manufacturing Orders Gantt, Work Centre Overview (load/OEE), Reporting → Work Center Load; MPS (mrp_mps) for the monthly 1,000-unit plan; Planning app optional for operator shifts.
- Start small: 1 week (~25 orders) first, check views, then the full month.

## 5. Odoo objects (cdrone-test only), order of writes, undo
Everything named `SIM-` or tagged SIM/DEMO; ids logged to `sim_ids.json`.
1. Settings/data: raise Product Unit precision 2 → 3 (needed for 0.263); un-archive MTO route; calendar `SIM 24/7` (passive WCs) and optional `SIM 1 shift + OT 08–17` for QC/AVI/BND.
2. Categories: Goods/SIM Demo/{Finished, Semi, Purchased}. Work-centre tag `SIM`. Partner tag `DEMO`.
3. Work centres: 53 labour stations `SIM-LAY-01…` + `SIM-CUR-01/02` + `SIM-RCK-01` = **56**, company CCS, alternatives set within each type (or per line).
4. Products: 10 finished + 4 airframes + ~10 laminates + 16 subassemblies (4 harness, 4 propulsion, 8 avionics) + ~28 purchased placeholders = **~68 SIM products**, shared, no tracking (or serial on finished — question). REAL raw codes reused as components (~12, not modified).
5. BoMs: **~40** (10 FG, 4 airframe, ~10 laminate, 16 subassembly), **~106 operations**, CCS, Manufacture type.
6. Stock: one inventory adjustment for placeholders + used REAL raw in WH/Stock (creates valuation entries in test).
7. Demo partners (20) → sale orders (100, split lines) → confirm → plan MOs. Week 1 first, then the rest.
Undo (reverse order, test only): cancel + delete SIM MOs and SOs; archive SIM products/BoMs/WCs (or delete where no moves); reverse the stock adjustment or leave archived; delete DEMO partners, SIM categories/calendars; re-archive MTO; precision can stay 3. Trial expiry (3 Dec) also wipes everything unless extended.

## 6. Open questions for Chang
1. Approve the assumptions (14 WC types, times, THB/h, family mix 45/25/15/15) or send real ones (esp. cure cycle, layup minutes, test time)?
2. Lean (53 stations + ≤1 h OT) or comfortable (65 stations, no OT) as the demo baseline? Shared pool or Line A/B?
3. Lot rule (MOs of ≤4 / ≤2) to hit 48–72 h, accepting ~2,500 MOs/month — or bigger MOs and longer lead time?
4. OK to base the INT family on the real Merops flow and real SAP raw codes (structure only, SIM- products)?
5. Stock components (recommended) or simulate purchasing too?
6. Serial numbers on finished drones in the demo (more realistic, slower) — yes/no?
7. Writes needed outside SIM objects: raise test Product Unit precision to 3 and un-archive MTO — OK? And extend the trial past 3 Dec?
