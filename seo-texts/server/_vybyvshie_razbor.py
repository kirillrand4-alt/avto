# -*- coding: utf-8 -*-
"""Кто ИМЕННО выбыл из разбора: разбивка по причине, а не по последней записи."""
import io
import json
import os
import re
import sqlite3
import sys

c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
c.row_factory = sqlite3.Row
выбыли = list(c.execute(
    "select inn, coalesce(note,'') note, coalesce(popytok,0) p, coalesce(ts,'') ts "
    "from site_facts where coalesce(facts_json,'')='' and coalesce(popytok,0) >= 3"))
c.close()
по_нотам = {}
for r in выбыли:
    к = (r['note'][:45] or '(пусто)')
    по_нотам[к] = по_нотам.get(к, 0) + 1

# сколько сбоев провайдера видел сам цикл фактов за последние часы
лог = r'C:\sender\server\fakty_cikl.log'
сбоев, разобрано, пачек = 0, 0, 0
хвост = []
if os.path.exists(лог):
    строки = io.open(лог, encoding='utf-8', errors='replace').read().splitlines()[-60:]
    for s in строки:
        m = re.search(r'\{.*\}', s)
        if not m:
            continue
        try:
            d = json.loads(m.group(0))
        except Exception:
            continue
        пачек += 1
        сбоев += d.get('сбоев', 0)
        разобрано += d.get('разобрано', 0)
    хвост = строки[-4:]
sys.stdout.reconfigure(encoding='utf-8')
print(json.dumps({'выбывших_всего': len(выбыли),
                  'по_последней_записи': sorted(по_нотам.items(), key=lambda x: -x[1])[:10],
                  'цикл_фактов_последние_пачки': пачек,
                  'в_них_разобрано': разобрано, 'в_них_сбоев': сбоев,
                  'хвост_лога': хвост}, ensure_ascii=False, indent=1))
