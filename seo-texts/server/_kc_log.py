# -*- coding: utf-8 -*-
import glob, io, os, json
DIR = r'C:\sender\server'
o = {}
for маска in ('kc_kontakty_*.log', 'kc_okved_fns_*.log'):
    л = sorted(glob.glob(os.path.join(DIR, маска)), key=os.path.getmtime)
    if л:
        o[маска] = io.open(л[-1], encoding='utf-8', errors='replace').read()[-900:]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
