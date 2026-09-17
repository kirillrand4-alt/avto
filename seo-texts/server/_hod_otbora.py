# -*- coding: utf-8 -*-
"""Ход отбора: сколько размечено, что в логе, сколько сигналов осталось."""
import glob, io, json, os, sqlite3, subprocess, time, collections
DIR = r'C:\sender\server'
o = {'сейчас': time.strftime('%H:%M:%S')}
r = subprocess.run(['powershell','-NoProfile','-Command',
    "(Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
    "Where-Object {$_.CommandLine -like '*otbor_90kvt*'}).ProcessId | ConvertTo-Json -Compress"],
    capture_output=True, text=True, timeout=90)
o['процесс'] = (r.stdout or '').strip() or 'завершился'
отч = os.path.join(DIR, 'otbor_90kvt.jsonl')
св = collections.Counter()
if os.path.exists(отч):
    with io.open(отч, encoding='utf-8', errors='replace') as f:
        for s in f:
            try: з = json.loads(s)
            except Exception: continue
            св['ошибок' if з.get('ошибка') else
               'a_компрессор' if з.get('a') else
               'b_мейер' if з.get('b') else 'ни_то_ни_то'] += 1
o['размечено'] = dict(св); o['всего_строк'] = sum(св.values())
for п in sorted(glob.glob(os.path.join(DIR,'otbor_90kvt_*.log')), key=os.path.getmtime)[-1:]:
    with io.open(п, encoding='utf-8', errors='replace') as f:
        т = f.read()
    o['лог'] = т[-600:] if т else '(пусто)'
c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=30)
o['сигналов_сейчас'] = c.execute('select count(*) from signals').fetchone()[0]
c.close()
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:2500])
