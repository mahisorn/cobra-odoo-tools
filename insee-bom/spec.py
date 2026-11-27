"""INSEE wing shipset structure inferred from BOM INSEE REV.0.xlsx (sheet 'INSEE (Part Cost)' + 'Est. Std. time').
All quantities per 1 unit of the parent. Usage already includes the sheet's off-cut allowance."""
RAW = {  # SAP code -> (sheet unit cost THB, unit)
    '14001384': (21.95, 'm'),    # GLASS CLOTH 100 GR/SQM.X1000 MM.
    '14003634': (156.09, 'm2'),  # PVC RIGID FOAM H80 3MM
    '14001821': (195.06, 'kg'),  # EPOXY RESIN SR 1280
    '14001576': (369.26, 'kg'),  # HARDENER SD 4993(CB)
    '24020685': (1155.0, 'tube'),  # 3M DP8710NS 45 ml; Odoo/SAP UoM is "ml" but price ~per tube -> qty entered as tubes
}
TBC = {  # placeholders (no SAP code)
    'INSEE-TBC-CROD': dict(name='INSEE TBC carbon rod T700 16 OD / 14 ID (sheet label 15mm x 300mm x 2mm)', cost=400.0,
                           note='spec/price TBC by Chindanai, copied from DrN40 project (BOM INSEE REV.0, INSEE (Part Cost)). No SAP code.'),
    'INSEE-TBC-CONS': dict(name='INSEE TBC process consumables per shipset (20% of material, sheet rule)', cost=955.04,
                           note='Sheet adds Consumable = 20% x material (4,775.22) = 955.04 THB per shipset; vacuum bag, peel ply, breather etc. TBC by Chindanai.'),
}
# resin system: sheet = 1.476 kg resin + 0.738 kg hardener per shipset = 0.75 / 0.375 kg per kg of laminate (glass+PVC weight 1.968 kg)
# split by laminate weight: skin L 0.135 kg, skin R 0.129 kg, spar set 0.360 kg
SEMI = {
  'INSEE-SKIN-LU': ('INSEE left wing skin upper (port)', [('14001384', 0.646), ('14003634', 0.45), ('14001821', 0.101), ('14001576', 0.051)]),
  'INSEE-SKIN-LL': ('INSEE left wing skin lower (port)', [('14001384', 0.646), ('14003634', 0.45), ('14001821', 0.101), ('14001576', 0.051)]),
  'INSEE-SKIN-RU': ('INSEE right wing skin upper (starboard)', [('14001384', 0.586), ('14003634', 0.45), ('14001821', 0.097), ('14001576', 0.048)]),
  'INSEE-SKIN-RL': ('INSEE right wing skin lower (starboard)', [('14001384', 0.586), ('14003634', 0.45), ('14001821', 0.097), ('14001576', 0.048)]),
  'INSEE-SPAR-SET': ('INSEE spar set (main spar + rear spar + 5 ribs)', [('14001384', 1.646), ('14003634', 1.2), ('14001821', 0.270), ('14001576', 0.135)]),
  'INSEE-WING-L': ('INSEE left wing assembly (port)', [('INSEE-SKIN-LU', 1), ('INSEE-SKIN-LL', 1), ('INSEE-SPAR-SET', 2), ('INSEE-TBC-CROD', 2), ('24020685', 0.6)]),
  'INSEE-WING-R': ('INSEE right wing assembly (starboard)', [('INSEE-SKIN-RU', 1), ('INSEE-SKIN-RL', 1), ('INSEE-SPAR-SET', 2), ('INSEE-TBC-CROD', 2), ('24020685', 0.6)]),
  'INSEE-SHIPSET': ('INSEE wing shipset (left + right wing) TEST', [('INSEE-WING-L', 1), ('INSEE-WING-R', 1), ('INSEE-TBC-CONS', 1)]),
}
WC = {  # code: (name, THB/h)  sheet: DL 150 + OH 150 = 300 THB/man-hour; CNC machine 350 THB/h
  'INSEE-LAM': ('INSEE composite layup & vacuum bag', 300.0),
  'INSEE-CNC': ('INSEE CNC core cutting (PVC/plywood)', 350.0),
  'INSEE-ASSY': ('INSEE wing bonding & assembly', 300.0),
  'INSEE-QC': ('INSEE quality check', 300.0),
  'INSEE-PNT': ('INSEE finishing & paint (scope TBC)', 300.0),
}
SKIN_OPS = [('Preparation (fiber cutting, PVC)', 'INSEE-LAM', 15), ('Mould preparation & wax', 'INSEE-LAM', 5),
            ('Laminate (2 workers x 30 min)', 'INSEE-LAM', 60), ('Vacuum', 'INSEE-LAM', 15), ('Demould', 'INSEE-LAM', 10),
            ('Trimming', 'INSEE-LAM', 10), ('QC 1', 'INSEE-QC', 5)]
OPS = {k: SKIN_OPS for k in ('INSEE-SKIN-LU', 'INSEE-SKIN-LL', 'INSEE-SKIN-RU', 'INSEE-SKIN-RL')}
OPS['INSEE-SPAR-SET'] = [('CNC core cutting (machine, 60 min/shipset / 4 sets)', 'INSEE-CNC', 15)]
WING_OPS = [('Gluing 1', 'INSEE-ASSY', 40), ('QC 2', 'INSEE-QC', 10), ('Gluing 2', 'INSEE-ASSY', 40), ('QC 3', 'INSEE-QC', 20),
            ('Sand + putty + coating (scope TBC)', 'INSEE-PNT', 60), ('Primer (scope TBC; top coat 0 min in sheet)', 'INSEE-PNT', 60)]
OPS['INSEE-WING-L'] = OPS['INSEE-WING-R'] = WING_OPS
OPS['INSEE-SHIPSET'] = [('QC 4 final', 'INSEE-QC', 40)]
SHEET_TOTAL = 10980.26  # material 4775.22 + consumables 955.04 + labour 16.33 h x 300 = 4900 + machine 350
