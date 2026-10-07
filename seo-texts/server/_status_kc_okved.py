# -*- coding: utf-8 -*-
import glob, io, json, os
DIR = r'C:\sender\server'
o = {}
п = os.path.join(DIR, 'kc-okved-fns.jsonl')
if os.path.exists(п):
    сч = {}
    for s in io.open(п, encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        к = '%s:%s' % (з.get('источник'), з.get('итог'))
        сч[к] = сч.get(к, 0) + 1
    o['строк'] = сч
логи = sorted(glob.glob(os.path.join(DIR, 'kc_okved_fns_*.log')), key=os.path.getmtime)
if логи:
    o['лог'] = os.path.basename(логи[-1])
    o['хвост'] = io.open(логи[-1], encoding='utf-8', errors='replace').read()[-700:]
o['скрипт_есть'] = os.path.exists(os.path.join(DIR, 'kc_okved_fns.py'))
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
