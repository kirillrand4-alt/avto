# -*- coding: utf-8 -*-
"""Итог перекачки: что получилось и что изменилось в базе."""
import glob, io, json, os, collections, subprocess, time

DIR = r'C:\sender\server'
o = {'сейчас': time.strftime('%H:%M:%S')}
r = subprocess.run(['powershell','-NoProfile','-Command',
     "(Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*dobor_teksta*'}).ProcessId | ConvertTo-Json -Compress"],
    capture_output=True, text=True, timeout=90)
o['процесс'] = (r.stdout or '').strip() or 'завершился'

for п in sorted(glob.glob(os.path.join(DIR,'dobor_teksta_*.log')), key=os.path.getmtime)[-1:]:
    with io.open(п, encoding='utf-8', errors='replace') as f:
        т = f.read()
    o['лог'] = {'файл': os.path.basename(п), 'байт': len(т), 'хвост': т[-700:]}

отч = os.path.join(DIR, 'dobor_teksta.jsonl')
итоги = collections.Counter(); длиннее = сумма_новая = не_капекс = 0
примеры = []
if os.path.exists(отч):
    with io.open(отч, encoding='utf-8', errors='replace') as f:
        for s in f:
            try: з = json.loads(s)
            except Exception: continue
            итоги[з.get('итог','?')] += 1
            if з.get('is_capex') is False: не_капекс += 1
            ново = (з.get('стало_what') or '').strip(); было = (з.get('было_what') or '').strip()
            if ново and len(ново) > len(было)*1.3:
                длиннее += 1
                if len(примеры) < 4:
                    примеры.append({'компания': з.get('компания'),
                                    'было': было[:90], 'стало': ново[:150],
                                    'сумма': з.get('стало_sum')})
            if (з.get('стало_sum') or '').strip() and not (з.get('было_sum') or '').strip():
                сумма_новая += 1
o['по_итогам'] = итоги.most_common()
o['what_стал_содержательнее'] = длиннее
o['появилась_сумма'] = сумма_новая
o['теперь_не_капекс'] = не_капекс
o['примеры'] = примеры
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:4500])
