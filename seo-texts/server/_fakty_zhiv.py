# -*- coding: utf-8 -*-
r"""Жив ли цикл фактов после правки: круги, скорость, свежие ошибки."""
import json
import os
import sqlite3
import time

d = {}
c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
d['колонки_stage_log'] = [x[1] for x in c.execute('PRAGMA table_info(stage_log)')]
d['колонки_site_facts'] = [x[1] for x in c.execute('PRAGMA table_info(site_facts)')]
теперь = time.time()
for часов in (1, 3, 12):
    порог = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(теперь - часов * 3600))
    d['паспортов_за_%dч' % часов] = c.execute(
        "select count(*) from site_facts where ts > ? and coalesce(facts_json,'')<>''",
        (порог,)).fetchone()[0]
    d['записей_за_%dч' % часов] = c.execute(
        'select count(*) from site_facts where ts > ?', (порог,)).fetchone()[0]
d['последние_note'] = [dict(zip(('инн', 'когда', 'note'), r)) for r in c.execute(
    "select inn, ts, substr(coalesce(note,''),1,90) from site_facts "
    'order by ts desc limit 6')]
c.close()

for корень in (r'C:\sender\_ops', r'C:\sender\logs', r'C:\sender'):
    if not os.path.isdir(корень):
        continue
    свежие = []
    with os.scandir(корень) as it:
        for e in it:
            if not e.is_file() or not e.name.endswith(('.out', '.log', '.err')):
                continue
            try:
                свежие.append((e.stat().st_mtime, e.name, e.stat().st_size))
            except OSError:
                pass
    свежие.sort(reverse=True)
    d.setdefault('логи', {})[корень] = [
        {'файл': n, 'мин_назад': int((теперь - t) / 60), 'байт': s}
        for t, n, s in свежие[:6]]
print(json.dumps(d, ensure_ascii=False, indent=1))
