"""Capacity + lead-time model for the SIM- demo line (all numbers are ASSUMPTIONS unless marked real)."""
import math, json
DAYS, SHIFT = 22, 8.0             # working days/month, hours/shift
AVAIL = DAYS * SHIFT              # 176 h per station per month (1 shift)
TARGET = 0.90                     # plan stations so 1-shift utilisation <= 90%, rest of the swing by OT
OT_CAP = 0.125                    # OT cap: 1 h/day = 12.5% (Chang: some OT)
UNITS = 1000
# work centres: code, name, kind(labour/passive), capacity per station (units per cycle), efficiency %, setup, cleanup (min/WO), THB/h
WC = [
 ('LAY','Composite layup & vacuum bag (2-person cell)','labour',2,90,15,15,450),
 ('CUR','Cure oven (24/7, batch)','passive',12,100,20,10,300),
 ('CNC','CNC trim & drill','labour',1,95,20,10,450),
 ('BND','Bonding & structural assembly (2 fixtures)','labour',2,90,15,10,450),
 ('RCK','Bond-cure / paint-dry rack (24/7)','passive',40,100,0,0,20),
 ('PNT','Surface prep & paint booth (2 parts/booth)','labour',2,90,20,20,500),
 ('HAR','Wiring harness','labour',1,90,10,5,150),
 ('PRP','Motor & propulsion assembly','labour',1,90,10,5,150),
 ('AVI','Avionics integration','labour',1,90,10,5,200),
 ('FAS','Final assembly (2-person cell)','labour',2,90,15,10,450),
 ('CAL','Calibration & firmware','labour',2,95,10,0,200),
 ('TST','Functional & flight test (2 bays)','labour',2,90,15,10,550),
 ('QC','Final QC inspection','labour',1,95,5,5,200),
 ('PCK','Packing','labour',1,95,10,10,120),
]
# per-unit cycle minutes by family (passive = cycle duration per batch)
FAM = {
 'QX4': dict(share=.45, LAY=60, CUR=240, CNC=30, BND=45, RCK_BOND=120, PNT=30, RCK_DRY=90, HAR=60, PRP=30, AVI=45, FAS=60, CAL=20, TST=30, QC=15, PCK=15),
 'HX6': dict(share=.25, LAY=120, CUR=240, CNC=45, BND=75, RCK_BOND=120, PNT=45, RCK_DRY=90, HAR=90, PRP=60, AVI=60, FAS=90, CAL=30, TST=45, QC=20, PCK=25),
 'VT2': dict(share=.15, LAY=150, CUR=240, CNC=60, BND=90, RCK_BOND=120, PNT=60, RCK_DRY=90, HAR=90, PRP=45, AVI=75, FAS=120, CAL=30, TST=60, QC=25, PCK=30),
 'INT': dict(share=.15, LAY=90, CUR=240, CNC=40, BND=60, RCK_BOND=120, PNT=45, RCK_DRY=90, HAR=45, PRP=30, AVI=60, FAS=75, CAL=25, TST=30, QC=20, PCK=20),
}
LOTMAX = {'QX4': 4, 'HX6': 2, 'VT2': 2, 'INT': 2}   # MO lot rule so each MO's critical path stays ~<=72 h
SKUS = {'QX4': ['SIM-QX4-STD','SIM-QX4-THM','SIM-QX4-MAP'], 'HX6': ['SIM-HX6-AG10','SIM-HX6-AG30','SIM-HX6-LOG'],
        'VT2': ['SIM-VT2-SRV','SIM-VT2-LR'], 'INT': ['SIM-INT-STD','SIM-INT-EXT']}
SIZE_BUCKETS = [((1, 2), .30), ((3, 5), .25), ((6, 10), .20), ((11, 20), .15), ((21, 60), .10)]  # order-size mix, mean ~10

def demand(seed=7, orders=100):
    import random
    r = random.Random(seed); out = []
    fams = list(FAM); w = [FAM[f]['share'] for f in fams]
    for i in range(orders):
        (lo, hi), = r.choices([b for b, _ in SIZE_BUCKETS], [p for _, p in SIZE_BUCKETS])
        f = r.choices(fams, w)[0]; out.append((f'SIM-OEM-{i+1:03d}', r.choice(SKUS[f]), f, r.randint(lo, hi)))
    tot = sum(o[3] for o in out); k = UNITS / tot   # scale to exactly ~1000 units
    out = [(a, b, f, max(1, round(q * k))) for a, b, f, q in out]
    return out

D = demand(); UNITS_SIM = sum(o[3] for o in D)
MOS = sum(math.ceil(q / LOTMAX[f]) for _, _, f, q in D)   # FG MOs = airframe MOs = HAR/PRP/AVI MOs
wc = {w[0]: dict(zip(['code','name','kind','cap','eff','setup','clean','cost'], w)) for w in WC}

def load():
    out = {}
    for c, w in wc.items():
        if w['kind'] == 'passive':
            continue
        run = sum(UNITS * f['share'] * f[c] for f in FAM.values())  # per-unit minutes x mix
        run = run / (w['eff'] / 100) / w['cap']
        setup = MOS * (w['setup'] + w['clean'])
        out[c] = (run + setup) / 60
    return out

def lean(h):
    n = max(1, math.ceil(h / (AVAIL * (1 + OT_CAP))))
    return n, max(0, h - n * AVAIL)

def stations(h):
    n = max(1, math.ceil(h / (AVAIL * TARGET)))
    util = h / (n * AVAIL); ot = max(0, h - n * AVAIL)
    return n, util, ot

def oven():
    cycles = UNITS / wc['CUR']['cap']                # set-loads per month
    per_day = 2                                      # 1 in-shift load + 1 loaded at end of shift, runs overnight
    return cycles, math.ceil(cycles / (per_day * DAYS))

# lead time: walk the critical path for one MO of `lot` units; labour only Mon-Fri 08-16, passive 24/7
def lead(fam, lot, n_par=None):
    f = FAM[fam]; t = 0.0  # hours since Monday 08:00
    def labour(mins):
        nonlocal t
        rem = mins / 60
        while rem > 1e-9:
            day, hr = divmod(t, 24)
            if day % 7 >= 5: t = (day // 7 + 1) * 168; continue
            if hr < 8: t = day * 24 + 8; continue
            if hr >= 16: t = (day + 1) * 24 + 8; continue
            step = min(rem, 16 - hr); t += step; rem -= step
    def passive(mins):
        nonlocal t
        t += mins / 60
    seq = [('LAY','l'),('CUR','p'),('CNC','l'),('BND','l'),('RCK_BOND','p'),('PNT','l'),('RCK_DRY','p'),('FAS','l'),('CAL','l'),('TST','l'),('QC','l'),('PCK','l')]
    for op, k in seq:
        base = op.split('_')[0]; w = wc[base]
        if k == 'p':
            passive(f[op] + w['setup'] + w['clean'])
        else:
            cycles = math.ceil(lot / w['cap'])
            labour(w['setup'] + cycles * f[op] / (w['eff'] / 100) + w['clean'])
    return t

if __name__ == '__main__':
    L = load(); rows = []
    for c, h in L.items():
        n, u, ot = stations(h); n1, u1, ot1 = (1, h / AVAIL, max(0, h - AVAIL))
        rows.append((c, wc[c]['name'], round(h), n, round(u * 100), round(ot), round(h / AVAIL, 2)))
    tot = sum(L.values())
    print('demand: orders', len(D), 'units', UNITS_SIM, 'FG MOs', MOS, 'by family', {f: sum(q for _, _, ff, q in D if ff == f) for f in FAM})
    print('code,name,cap,load_station_h,operator_h,comfort_stations,util%,lean_stations,lean_OT_h/mo,OT_h/day/station,max_units_lean')
    perunit = {c: sum(f['share'] * f[c] for f in FAM.values()) / (wc[c]['eff'] / 100) / wc[c]['cap'] / 60 + MOS / UNITS * (wc[c]['setup'] + wc[c]['clean']) / 60 for c in L}
    for c, h in L.items():
        n, u, _ = stations(h); nl, ot = lean(h)
        print(','.join(map(str, [c, wc[c]['name'], wc[c]['cap'], round(h), round(h * wc[c]['cap']), n, round(u * 100), nl, round(ot), round(ot / DAYS / nl, 2), int(nl * AVAIL * (1 + OT_CAP) / perunit[c])])))
    json.dump(D, open('demand.json', 'w'), indent=0)
    print('total labour/machine hours', round(tot), 'station-equivalents', round(tot / AVAIL, 1))
    cyc, ovens = oven(); print('oven loads/month', round(cyc), 'ovens needed (2 loads/day/oven)', ovens)
    for fam in FAM:
        print(fam, 'lead h (Mon 08:00 start) lot1/2/4/6:', [round(lead(fam, l)) for l in (1, 2, 4, 6)])
    print('per-unit labour min', {k: sum(v[c] for c in v if c in L) for k, v in FAM.items()})
