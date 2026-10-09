# -*- coding: utf-8 -*-
# Проба meyer7t: доводка после обхода (_dovodka_meyer7t.py) — ждёт конца обхода; доп. ОКВЭД и паспорт фоном;
# агенты Sol и Luna одновременно по 40 потоков.
import json, os, subprocess, sys, time
DIR = r'C:\sender\server'
ЛОГ = os.path.join(DIR, 'meyer7t_dovodka_%s.log' % time.strftime('%d%m-%H%M'))
python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python): python = sys.executable
выход = open(ЛОГ, 'wb')
p = subprocess.Popen([python, '-u', os.path.join(DIR, '_dovodka_meyer7t.py')],
                     cwd=DIR, creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL,
                     stdout=выход, stderr=subprocess.STDOUT, close_fds=False)
выход.close()
time.sleep(20)
o = {'pid': p.pid, 'лог': os.path.basename(ЛОГ)}
if os.path.exists(ЛОГ) and os.path.getsize(ЛОГ):
    with open(ЛОГ, encoding='utf-8', errors='replace') as f:
        o['хвост'] = f.read()[-400:]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
