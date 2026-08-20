# -*- coding: utf-8 -*-
r"""Реально ли перевелись лиды в «не интересно» и что видно в ленте."""
import json, sqlite3
c = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
c.row_factory = sqlite3.Row
d = {}
d['по_статусам'] = dict(c.execute(
    'select status, count(*) from leads group by status order by 2 desc').fetchall())
d['последние_переводы'] = [dict(r) for r in c.execute(
    "select lead_id, action, from_status, to_status, created_at "
    "from lead_events where to_status is not null and from_status<>to_status "
    'order by id desc limit 10')]
d['видно_в_ленте_по_умолчанию'] = c.execute(
    "select count(*) from leads where status not in ('deleted','not_interested')"
).fetchone()[0]
c.close()
print(json.dumps(d, ensure_ascii=False, indent=1)[:2200])
