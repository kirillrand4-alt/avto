# -*- coding: utf-8 -*-
# Тестовая партия Meyer (план Б3): поиск набора meyer7t. Лог meyer7t_poisk_*.log — по нему конвейер ждёт «готово».
# PILOT_REZERV: план — 150 ₽; здесь выше, чтобы поиск сам не вышел за лимит пробы 100 ₽ (старт пробы 385,8 ₽,
# поиск ~51 ₽ по расчёту; при 315 ₽ поиск встанет, потратив ~71 ₽ — остаток лимита сайтам по названию и агентам).
import json, os, subprocess, sys, time
DIR = r'C:\sender\server'
НАБОР = 'meyer7t'
ЛОГ = os.path.join(DIR, '%s_poisk_%s.log' % (НАБОР, time.strftime('%d%m-%H%M')))
python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python): python = sys.executable
выход = open(ЛОГ, 'wb')
p = subprocess.Popen([python, '-u', os.path.join(DIR, 'pilot_poisk.py')],
                     cwd=DIR, creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL,
                     stdout=выход, stderr=subprocess.STDOUT, close_fds=False,
                     env=dict(os.environ, POISK_NABOR=НАБОР, KC_NABOR=НАБОР, POISK_REGIONY_SVERKI='все',
                              PILOT_REZERV=os.environ.get('PILOT_REZERV', '315')))
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
