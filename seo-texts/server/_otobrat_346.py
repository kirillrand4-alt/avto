# -*- coding: utf-8 -*-
"""Сузить очередь приговора до боевых: несудимые с кэшем И в группе «Партия 935».

Пишем их в C:\\sender\\server\\prigovor-ochered.jsonl — судья смотрит этот путь
ПЕРВЫМ (рядом с собой), полная очередь остаётся в _tmp на будущее.
"""
import json
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
ПОЛНАЯ = r'C:\sender\_tmp\prigovor-ochered.jsonl'
БОЕВАЯ = r'C:\sender\server\prigovor-ochered.jsonl'
KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')

очередь = [json.loads(l) for l in open(ПОЛНАЯ, encoding='utf-8') if l.strip()]
e = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
судимые = {(str(r[0]), r[1]) for r in e.execute(
    "select inn, domen from prigovor_domenov "
    "where verdikt in ('свой','группа','чужой','не_понять')")}
e.close()
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
в_группе = set()
for инн, ex in s.execute("select coalesce(inn,''), coalesce(extra_json,'') "
                         "from recipients where extra_json like '%gruppy%'"):
    try:
        if 'Партия 935' in (json.loads(ex).get('gruppy') or []):
            в_группе.add(''.join(c for c in инн if c.isdigit()))
    except Exception:  # noqa: BLE001
        pass
s.close()
боевые = [з for з in очередь
          if (з['inn'], з['домен']) not in судимые
          and з['inn'] in в_группе
          and os.path.exists(os.path.join(KESH, '%s.json.gz' % з['inn']))]
with open(БОЕВАЯ, 'w', encoding='utf-8') as f:
    for з in боевые:
        f.write(json.dumps(з, ensure_ascii=False) + '\n')
    f.flush()
    os.fsync(f.fileno())
print(json.dumps({'боевых_в_очереди': len(боевые), 'файл': БОЕВАЯ},
                 ensure_ascii=False))
