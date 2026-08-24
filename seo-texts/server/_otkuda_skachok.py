# -*- coding: utf-8 -*-
r"""Откуда взялся скачок паспортов: по часам ts и кто их пишет."""
import json
import sqlite3

c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
д = {'по_часам': {r[0]: r[1] for r in c.execute(
    "select substr(ts,1,13) ч, count(*) k from site_facts "
    "where ts >= date('now','-1 day') group by ч order by ч desc limit 10")}}
д['формат_по_часам'] = {r[0]: r[1] for r in c.execute(
    "select substr(ts,1,13) ч, count(*) k from site_facts "
    "where coalesce(format,0)>=2 and ts >= date('now','-1 day') "
    'group by ч order by ч desc limit 6')}
д['с_пустой_note_за_час'] = c.execute(
    "select count(*) from site_facts where ts >= datetime('now','-1 hour')"
).fetchone()[0]
д['всего'] = c.execute('select count(*) from site_facts').fetchone()[0]
c.close()
print(json.dumps(д, ensure_ascii=False, indent=1))
