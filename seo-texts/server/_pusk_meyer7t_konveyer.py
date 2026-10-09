# -*- coding: utf-8 -*-
# Тестовая партия Meyer (план Б3): конвейер набора meyer7t. Сам ждёт «готово» в meyer7t_poisk_*.log.
# KC_AGENT_LIMIT=40 — не больше 40 агентов на проход (Sol и Luna), самые крупные по выручке.
# Продолжить с шага N: PILOT_S_SHAGA=N в окружении раннера (по умолчанию 0).
import json, os, subprocess, sys, time
DIR = r'C:\sender\server'
НАБОР = 'meyer7t'
ЛОГ = os.path.join(DIR, '%s_konveyer_%s.log' % (НАБОР, time.strftime('%d%m-%H%M')))
python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python): python = sys.executable
выход = open(ЛОГ, 'wb')
p = subprocess.Popen([python, '-u', os.path.join(DIR, 'pilot_konveyer.py')],
                     cwd=DIR, creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL,
                     stdout=выход, stderr=subprocess.STDOUT, close_fds=False,
                     env=dict(os.environ, POISK_NABOR=НАБОР, KC_NABOR=НАБОР, POISK_REGIONY_SVERKI='все',
                              KC_AGENT_LIMIT='40', PILOT_S_SHAGA=os.environ.get('PILOT_S_SHAGA', '0')))
выход.close()
time.sleep(20)
o = {'pid': p.pid, 'лог': os.path.basename(ЛОГ)}
отч = os.path.join(DIR, НАБОР + '-konveyer.json')
if os.path.exists(отч):
    with open(отч, encoding='utf-8', errors='replace') as f:
        o['статус'] = f.read()[-600:]
if os.path.exists(ЛОГ) and os.path.getsize(ЛОГ):
    with open(ЛОГ, encoding='utf-8', errors='replace') as f:
        o['хвост'] = f.read()[-600:]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
