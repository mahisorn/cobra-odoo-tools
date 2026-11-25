"""SIM line spec (RC-9). All times/costs are ASSUMPTIONS from PLAN.md; raw codes are REAL SAP codes (reused unchanged)."""
import model as M
FAMS = ['QX4', 'HX6', 'VT2', 'INT']
LINE = {'QX4': 'A', 'HX6': 'B', 'VT2': 'B', 'INT': 'B'}
LOT = {'QX4': 4, 'HX6': 2, 'VT2': 1, 'INT': 2}
# work-centre types: (code, name, kind, cap, eff, setup, cleanup, THB/h, stations: shared int or {'A':n,'B':n})
WCT = [
 ('LAY', 'Composite layup & vacuum bag (2-person cell)', 'labour', 2, 90, 15, 15, 290, 7),
 ('CUR', 'Cure oven zone (oven 1-2, 3 zones of 4 sets each, 24/7)', 'passive', 4, 100, 20, 10, 100, 6),
 ('CNC', 'CNC trim & drill', 'labour', 1, 95, 20, 10, 450, 6),
 ('BND', 'Bonding & structural assembly (2 fixtures)', 'labour', 2, 90, 15, 10, 300, 5),
 ('RCK', 'Bond-cure / paint-dry rack zone (10 slots, 24/7)', 'passive', 10, 100, 0, 0, 10, 4),
 ('PNT', 'Surface prep & paint booth (2 parts/booth)', 'labour', 2, 90, 20, 20, 500, 5),
 ('HAR', 'Wiring harness', 'labour', 1, 90, 10, 5, 150, {'A': 3, 'B': 6}),
 ('PRP', 'Motor & propulsion assembly', 'labour', 1, 90, 10, 5, 150, {'A': 2, 'B': 4}),
 ('AVI', 'Avionics integration', 'labour', 1, 90, 10, 5, 200, {'A': 3, 'B': 5}),
 ('FAS', 'Final assembly (2-person cell)', 'labour', 2, 90, 15, 10, 300, {'A': 2, 'B': 4}),
 ('CAL', 'Calibration & firmware (2 jigs)', 'labour', 2, 95, 10, 0, 200, {'A': 1, 'B': 1}),
 ('TST', 'Functional & flight test (2 bays)', 'labour', 2, 90, 15, 10, 600, {'A': 1, 'B': 3}),
 ('QC', 'Final QC inspection', 'labour', 1, 95, 5, 5, 200, {'A': 1, 'B': 2}),
 ('PCK', 'Packing', 'labour', 1, 95, 10, 10, 120, {'A': 1, 'B': 3}),
]
MIN = {f: {k: v for k, v in M.FAM[f].items() if k != 'share'} for f in FAMS}   # minutes per drone per op

# purchased placeholders: code -> (name, assumed THB cost)
PUR = {
 'SIM-P-MOT-2814': ('Motor 2814 (QX4)', 2200), 'SIM-P-MOT-6215': ('Motor 6215 (HX6)', 9500), 'SIM-P-MOT-4120': ('Motor 4120 (VT2)', 4800), 'SIM-P-MOT-3520': ('Motor 3520 (INT)', 3900),
 'SIM-P-ESC-40A': ('ESC 40A', 900), 'SIM-P-ESC-80A': ('ESC 80A', 2600), 'SIM-P-ESC-60A': ('ESC 60A', 1700),
 'SIM-P-PROP-15': ('Propeller 15in pair', 600), 'SIM-P-PROP-30': ('Propeller 30in folding', 2400), 'SIM-P-PROP-16': ('Propeller 16in', 700), 'SIM-P-PROP-12': ('Propeller 12in', 450),
 'SIM-P-FC-STD': ('Flight controller standard', 6500), 'SIM-P-FC-PRO': ('Flight controller pro (redundant)', 18000),
 'SIM-P-GPS-RTK': ('GNSS RTK module', 7500), 'SIM-P-RADIO-STD': ('Datalink radio standard', 5500), 'SIM-P-RADIO-LR': ('Datalink radio long range', 21000),
 'SIM-P-BAT-6S5': ('Battery 6S 5Ah', 3200), 'SIM-P-BAT-6S10': ('Battery 6S 10Ah', 5200), 'SIM-P-BAT-12S16': ('Battery 12S 16Ah', 16500), 'SIM-P-BAT-12S22': ('Battery 12S 22Ah', 22000),
 'SIM-P-WIREKIT-S': ('Wire & cable kit small', 850), 'SIM-P-WIREKIT-L': ('Wire & cable kit large', 1900), 'SIM-P-CONNKIT': ('Connector kit', 1200),
 'SIM-P-CAM-THERMAL': ('Payload thermal camera', 65000), 'SIM-P-CAM-MAP': ('Payload mapping camera', 42000), 'SIM-P-SPRAY-10L': ('Spray kit 10 L', 18000),
 'SIM-P-SPRAY-30L': ('Spray kit 30 L', 32000), 'SIM-P-WINCH-LOG': ('Delivery winch kit', 26000), 'SIM-P-EXT-RANGE': ('Extended range kit', 15000),
}
F = {  # per-family BoM content (quantities per drone, ASSUMED except INT laminate = REAL RC-7 Merops recipe x3 skins)
 'QX4': dict(lam=[('14000031', 1.2), ('14001685', 0.3), ('14001821', 0.9), ('14001576', 0.315), ('15002649', 1.5), ('14003507', 2.0)],
             af=[('24010253', 0.5), ('14001908', 24), ('14001069', 0.1), ('14002652', 0.2)],
             har=[('SIM-P-WIREKIT-S', 1), ('SIM-P-CONNKIT', 1)], prp=[('SIM-P-MOT-2814', 4), ('SIM-P-ESC-40A', 4), ('SIM-P-PROP-15', 2)],
             avi=[('SIM-P-FC-STD', 1), ('SIM-P-GPS-RTK', 1), ('SIM-P-RADIO-STD', 1)], bat=('SIM-P-BAT-6S10', 2), price=180000),
 'HX6': dict(lam=[('14000031', 2.4), ('14001685', 0.6), ('14001821', 1.8), ('14001576', 0.63), ('15002649', 3.0), ('14003507', 4.0)],
             af=[('24010253', 1.0), ('14001908', 36), ('14001069', 0.2), ('14002652', 0.4)],
             har=[('SIM-P-WIREKIT-L', 1), ('SIM-P-CONNKIT', 1)], prp=[('SIM-P-MOT-6215', 6), ('SIM-P-ESC-80A', 6), ('SIM-P-PROP-30', 6)],
             avi=[('SIM-P-FC-PRO', 1), ('SIM-P-GPS-RTK', 1), ('SIM-P-RADIO-STD', 1)], bat=('SIM-P-BAT-12S22', 2), price=420000),
 'VT2': dict(lam=[('14000031', 3.0), ('14001685', 1.2), ('14001386', 6.0), ('14001821', 2.4), ('14001576', 0.84), ('15002649', 4.0), ('14003507', 5.0)],
             af=[('24010253', 1.0), ('14001908', 30), ('14001069', 0.3), ('14002652', 0.5)],
             har=[('SIM-P-WIREKIT-L', 1), ('SIM-P-CONNKIT', 1)], prp=[('SIM-P-MOT-4120', 5), ('SIM-P-ESC-60A', 5), ('SIM-P-PROP-16', 5)],
             avi=[('SIM-P-FC-PRO', 1), ('SIM-P-GPS-RTK', 1), ('SIM-P-RADIO-STD', 1)], bat=('SIM-P-BAT-12S16', 2), price=650000),
 'INT': dict(lam=[('14001386', 28.72), ('14001821', 2.25), ('14001576', 0.789), ('24019690', 0.075)],
             af=[('24010253', 0.75), ('14001908', 20), ('14001069', 0.15), ('14002652', 0.3)],
             har=[('SIM-P-WIREKIT-S', 1), ('SIM-P-CONNKIT', 1)], prp=[('SIM-P-MOT-3520', 1), ('SIM-P-ESC-60A', 1), ('SIM-P-PROP-12', 1)],
             avi=[('SIM-P-FC-STD', 1), ('SIM-P-GPS-RTK', 1), ('SIM-P-RADIO-STD', 1)], bat=('SIM-P-BAT-6S5', 1), price=250000),
}
PACK = [('24007572', 1), ('24008369', 3.0), ('24001823', 5.0)]   # REAL packing codes
SKU = {  # finished SKU -> (family, name, extra payload lines)
 'SIM-QX4-STD': ('QX4', 'SIM Quad QX4 Standard', []), 'SIM-QX4-THM': ('QX4', 'SIM Quad QX4 Thermal', [('SIM-P-CAM-THERMAL', 1)]),
 'SIM-QX4-MAP': ('QX4', 'SIM Quad QX4 Mapping', [('SIM-P-CAM-MAP', 1)]),
 'SIM-HX6-AG10': ('HX6', 'SIM Hexa HX6 Agri 10 L', [('SIM-P-SPRAY-10L', 1)]), 'SIM-HX6-AG30': ('HX6', 'SIM Hexa HX6 Agri 30 L', [('SIM-P-SPRAY-30L', 1)]),
 'SIM-HX6-LOG': ('HX6', 'SIM Hexa HX6 Logistics', [('SIM-P-WINCH-LOG', 1)]),
 'SIM-VT2-SRV': ('VT2', 'SIM VTOL VT2 Survey', [('SIM-P-CAM-MAP', 1)]), 'SIM-VT2-LR': ('VT2', 'SIM VTOL VT2 Long Range', [('SIM-P-RADIO-LR', 1)]),
 'SIM-INT-STD': ('INT', 'SIM Interceptor INT Standard', []), 'SIM-INT-EXT': ('INT', 'SIM Interceptor INT Extended', [('SIM-P-EXT-RANGE', 1)]),
}
REAL = sorted({c for f in F.values() for c, _ in f['lam'] + f['af']} | {c for c, _ in PACK})
