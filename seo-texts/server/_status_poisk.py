# -*- coding: utf-8 -*-
import glob, io, json, os
DIR = r'C:\sender\server'
o = {}
for маска in ('poisk_*.log', 'konveyer_*.log'):
    for л in sorted(glob.glob(os.path.join(DIR, маска)), key=os.path.getmtime)[-6:]:
        o[os.path.basename(л)] = io.open(л, encoding='utf-8', errors='replace').read()[-300:]
for ф in ('poisk-serp.jsonl', 'poisk-razbor.jsonl', 'poisk-okved.jsonl', 'poisk-kontakty.jsonl', 'poisk-audit.jsonl'):
    п = os.path.join(DIR, ф)
    if os.path.exists(п):
        o[ф] = sum(1 for _ in io.open(п, encoding='utf-8', errors='replace'))
п = os.path.join(DIR, 'poisk-konveyer.json')
if os.path.exists(п):
    o['конвейер'] = json.load(io.open(п, encoding='utf-8'))
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[-5000:])
