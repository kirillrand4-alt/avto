# -*- coding: utf-8 -*-
"""Есть ли у панели доступ к enrich.db (контакты, люди) и как он устроен."""
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
for имя in ('company_card.py', 'probe_enrich.py'):
    п = r'C:\sender\sender\%s' % имя
    if not os.path.exists(п):
        continue
    t = io.open(п, encoding='utf-8', errors='replace').read()
    итог[имя] = {
        'enrich_упоминания': [l.strip()[:100] for l in t.splitlines()
                              if re.search(r'enrich|обогащ', l, re.I)][:6],
        'функции': [l.strip()[:90] for l in t.splitlines()
                    if re.match(r'\s*def ', l)][:18],
    }
# что вообще есть в enrich.db про людей и телефоны
import sqlite3
c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
итог['таблицы_enrich'] = [r[0] for r in c.execute(
    "select name from sqlite_master where type='table' order by 1")][:25]
for т in ('people', 'phone_contacts', 'emails'):
    try:
        итог['колонки_' + т] = [r[1] for r in c.execute('pragma table_info(%s)' % т)]
    except Exception:  # noqa: BLE001
        pass
c.close()
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3200])
