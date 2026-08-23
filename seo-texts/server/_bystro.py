# -*- coding: utf-8 -*-
r"""Быстрая сводка без обхода razobrano (там 460 тысяч файлов)."""
import json
import os
import sqlite3
import time

ZENNO = r'C:\seostat\drop\zenno'
KESH = r'C:\seostat\drop\pagecache'
d = {}
оч = os.path.join(ZENNO, 'ochered.txt')
d['очередь_строк'] = sum(1 for s in open(оч, encoding='utf-8', errors='replace')
                         if s.strip()) if os.path.exists(оч) else 0
d['gotovo'] = sum(1 for _ in os.scandir(os.path.join(ZENNO, 'gotovo')))
n = св = 0
порог = time.time() - 3600
with os.scandir(KESH) as it:
    for e in it:
        if not e.name.endswith('.json.gz'):
            continue
        n += 1
        try:
            if e.stat().st_mtime >= порог:
                св += 1
        except OSError:
            pass
d['кэш'] = {'файлов': n, 'за_час': св}
c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
d['паспорта'] = {
    'ГОТОВЫХ_формат2': c.execute(
        "select count(*) from site_facts where coalesce(facts_json,'')<>'' "
        'and coalesce(format,0)>=2').fetchone()[0],
    'ПОЛНЫХ_с_продукцией': c.execute(
        "select count(*) from site_facts where coalesce(format,0)>=2 "
        "and facts_json like '%\"продукция\": [\"%'").fetchone()[0],
    'за_час': c.execute(
        "select count(*) from site_facts where ts > ? and coalesce(facts_json,'')<>''",
        (time.strftime('%Y-%m-%dT%H:%M:%S',
                       time.localtime(time.time() - 3600)),)).fetchone()[0]}
d['роли_прогон'] = {
    'стадия_пройдена': c.execute(
        "select count(*) from stage_log where stage='phone_podpis'").fetchone()[0],
    'строк_от_подписи': c.execute(
        "select count(*) from phone_contacts where source like '%подпись со стран%'"
    ).fetchone()[0],
    'с_ролью': c.execute(
        "select count(*) from phone_contacts where source like '%подпись со стран%' "
        "and coalesce(role,'') not in ('','общий')").fetchone()[0]}
c.close()
print(json.dumps(d, ensure_ascii=False, indent=1))
