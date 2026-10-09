# -*- coding: utf-8 -*-
# Полный прогон Meyer (план Б5): поиск набора meyer7. Резерв xmlriver PILOT_REZERV — по плану 350 ₽.
import json, os, subprocess, sys, time
DIR = r'C:\sender\server'
НАБОР = 'meyer7'
ЛОГ = os.path.join(DIR, '%s_poisk_%s.log' % (НАБОР, time.strftime('%d%m-%H%M')))
python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python): python = sys.executable
выход = open(ЛОГ, 'wb')
p = subprocess.Popen([python, '-u', os.path.join(DIR, 'pilot_poisk.py')],
                     cwd=DIR, creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL,
                     stdout=выход, stderr=subprocess.STDOUT, close_fds=False,
                     env=dict(os.environ, POISK_NABOR=НАБОР, KC_NABOR=НАБОР, POISK_REGIONY_SVERKI='все',
                              PILOT_REZERV=os.environ.get('PILOT_REZERV', '350')))
выход.close()
time.sleep(90)
o = {'pid': p.pid, 'лог': os.path.basename(ЛОГ)}
отч = os.path.join(DIR, НАБОР + '-serp.jsonl')
o['строк serp'] = sum(1 for _ in open(отч, encoding='utf-8', errors='replace')) if os.path.exists(отч) else 0
if os.path.exists(ЛОГ) and os.path.getsize(ЛОГ):
    with open(ЛОГ, encoding='utf-8', errors='replace') as f:
        o['хвост'] = f.read()[-600:]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
