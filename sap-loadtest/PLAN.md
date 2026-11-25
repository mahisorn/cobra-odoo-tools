# cdrone-test SAP load test — plan (draft, not approved) 24 Nov 2026 ICT
Target: https://cdrone-test.odoo.com db `cdrone-test` (Odoo 20.0+e trial, created 17 Nov, expires 3 Dec 2026 17:02 ICT, 9 products, no Merops categories). Prod untouched.
Source: ../big.csv sha256 fc43f884…; 257,974 materials after expanding 115 rows pasted inside 2 corrupt cells; 0 dupes.
Scope A (Chang's words: raw + semi): ZSM 175,106 + ZSMN 7,053 + ZRM 1,516 + ZRMN 14,540 = 198,215 new.
Scope B (all types): 257,971 new (3 Merops skins already exist).
Steps on approval: 1) create 9 count UoMs (Pack, Set, Pair, Roll, Carton, Can, Bottle, Drum, Bag = 1 Unit)
2) create Goods/Cobra SAP + one child per MTyp  3) pilot 1 batch of 1,000, time it  4) run remaining batches sequentially,
1 call in flight, >=1 s gap, tracking off, resumable via skip-existing  5) time UI/search/list checks.
Undo: archive or unlink everything under Goods/Cobra SAP (test only).
