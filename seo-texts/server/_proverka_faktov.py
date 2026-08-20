# -*- coding: utf-8 -*-
r"""Проверка ночного прогона фактов: жив ли, что делает, во что обходится.

Владелец 20.08 попросил проверить три раза с промежутком в пять минут — этот
скрипт и есть одна проверка. Смотрим не «крутится ли процесс», а РЕЗУЛЬТАТ:
сколько паспортов прибавилось, сколько сбоев, какого качества выходят карточки
и сколько потрачено на шлюзе.
"""
import json
import os
import sqlite3
import sys
import time

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
os.chdir(DIR)
BD = r'C:\sender\enrich.db'
ЛОГ = r'C:\sender\server\fakty_cikl.log'
СНИМОК = r'C:\sender\server\_proverka_faktov.snimok.json'

итог = {'время': time.strftime('%Y-%m-%d %H:%M:%S')}
try:
    import storozh as S
    итог['крутится'] = bool(S._крутится(S._живые(), 'fakty_cikl.py'))
except Exception as e:  # noqa: BLE001
    итог['крутится'] = 'сбой: %s' % str(e)[:80]

c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
паспортов = c.execute('select count(*) from site_facts').fetchone()[0]
свежих = c.execute(
    "select count(*) from site_facts where ts >= datetime('now','-1 hour')"
).fetchone()[0] if 'ts' in [r[1] for r in c.execute('pragma table_info(site_facts)')] else None
итог['паспортов'] = паспортов
итог['за_час'] = свежих
# качество последних
ув = {}
for (js,) in c.execute("select facts_json from site_facts "
                       "where coalesce(facts_json,'')<>'' "
                       'order by rowid desc limit 40'):
    try:
        ув[json.loads(js).get('уверенность') or '?'] = \
            ув.get(json.loads(js).get('уверенность') or '?', 0) + 1
    except Exception:  # noqa: BLE001
        ув['битый'] = ув.get('битый', 0) + 1
итог['качество_последних_40'] = ув
c.close()

if os.path.exists(ЛОГ):
    with open(ЛОГ, encoding='utf-8', errors='replace') as f:
        строки = [s.strip() for s in f if s.strip()]
    итог['хвост'] = строки[-4:]
    свои = [s for s in строки if s[:2].isdigit()]
    итог['сбоев_в_логе'] = sum(1 for s in свои if 'сбой' in s)

# прирост с прошлой проверки — durable, переживает рестарт песочницы
прошлое = {}
if os.path.exists(СНИМОК):
    try:
        прошлое = json.load(open(СНИМОК, encoding='utf-8'))
    except Exception:  # noqa: BLE001
        pass
if прошлое.get('паспортов') is not None:
    прошло = max(1.0, time.time() - float(прошлое.get('t', time.time())))
    прибыло = паспортов - int(прошлое['паспортов'])
    итог['с_прошлой_проверки'] = {
        'минут': round(прошло / 60, 1), 'паспортов': прибыло,
        'в_час': round(прибыло * 3600 / прошло)}
with open(СНИМОК, 'w', encoding='utf-8') as f:
    json.dump({'паспортов': паспортов, 't': time.time()}, f)
    f.flush()
    os.fsync(f.fileno())
print(json.dumps(итог, ensure_ascii=False, indent=1))
