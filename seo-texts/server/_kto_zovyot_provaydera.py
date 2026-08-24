# -*- coding: utf-8 -*-
r"""Кто и сколько ходит к провайдеру: паспорта, разбор моста, мои прогоны.

Вопрос владельца 24.08 — «нету от тебя запросов к провайдеру? включая зенку».
Считаем по следам в базе и журналах, а не по памяти.
"""
import json
import os
import re
import sqlite3
import time

d = {}
c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
сегодня = time.strftime('%Y-%m-%d')
d['паспорта_за_сегодня'] = c.execute(
    "select count(*) from site_facts where ts like ? and coalesce(facts_json,'')<>''",
    (сегодня + '%',)).fetchone()[0]
d['паспорта_за_сутки'] = c.execute(
    "select count(*) from site_facts where ts >= datetime('now','-1 day') "
    "and coalesce(facts_json,'')<>''").fetchone()[0]
d['сбои_провайдера_в_карточках'] = c.execute(
    "select count(*) from site_facts where coalesce(note,'') like 'провайдер:%'"
).fetchone()[0]
c.close()

# журнал разбора, который поднимает мост Зенки
ж = r'C:\sender\server\zenno_razbor.jsonl'
if os.path.exists(ж):
    всего = провайдером = сегодня_n = 0
    with open(ж, encoding='utf-8', errors='replace') as f:
        for s in f:
            if not s.strip():
                continue
            всего += 1
            if '"extract": "provider"' in s or "'extract': 'provider'" in s:
                провайдером += 1
            if сегодня in s:
                сегодня_n += 1
    d['zenno_razbor'] = {'строк_всего': всего, 'из_них_провайдером': провайдером,
                         'строк_с_сегодняшней_датой': сегодня_n,
                         'обновлён_мин_назад': int(
                             (time.time() - os.path.getmtime(ж)) / 60)}
# что сейчас крутится
import subprocess
out = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "%{ $_.CommandLine } | Select-String -Pattern "
     "'fakty_cikl|enrich_contacts|zenno_most|roli_telefonov|poisk_saytov' "
     '| %{ $_.ToString().Trim() }'],
    capture_output=True, text=True, timeout=120)
d['живые_процессы'] = [re.sub(r'.*\\\\', '', s.strip())[:90]
                       for s in (out.stdout or '').splitlines() if s.strip()][:10]
# холды
for флаг in ('HOLD-FAKTY.flag', 'HOLD-POISK.flag'):
    d.setdefault('холды', {})[флаг] = os.path.exists(
        os.path.join(r'C:\sender\server', флаг))
print(json.dumps(d, ensure_ascii=False, indent=1)[:2600])
