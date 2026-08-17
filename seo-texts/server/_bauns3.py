# -*- coding: utf-8 -*-
"""Где вообще живут события доставки: ищем таблицу по всем базам рассыльщика."""
import glob
import json
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
базы = [p for p in glob.glob(r'C:\sender\*.db')] + [p for p in glob.glob(r'C:\sender\**\*.db')]
for b in sorted(set(базы)):
    try:
        c = sqlite3.connect('file:%s?mode=ro' % b.replace('\\', '/'), uri=True)
        т = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
        интерес = [x for x in т if any(k in x.lower() for k in
                                       ('bounce', 'event', 'delivery', 'sent', 'log'))]
        строк = {}
        for x in интерес[:8]:
            try:
                строк[x] = c.execute('select count(*) from %s' % x).fetchone()[0]
            except Exception:
                pass
        c.close()
        итог[os.path.basename(b)] = {'размер_мб': round(os.path.getsize(b) / 1e6, 1),
                                     'таблицы': строк}
    except Exception as e:  # noqa: BLE001
        итог[os.path.basename(b)] = {'ошибка': str(e)[:60]}
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
