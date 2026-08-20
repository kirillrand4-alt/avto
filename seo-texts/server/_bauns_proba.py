# -*- coding: utf-8 -*-
r"""Уходили ли в отправку адреса, которых проба уже признала мёртвыми."""
import json, os, sqlite3

итог = {}
c = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
c.row_factory = sqlite3.Row
# где вообще живут результаты пробы
c2 = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True)
c2.row_factory = sqlite3.Row
for имя, con in (('sender.db', c), ('enrich.db', c2)):
    t = [r[0] for r in con.execute(
        "select name from sqlite_master where type='table' and "
        "(name like '%probe%' or name like '%suppress%' or name like '%addr%')")]
    итог.setdefault('таблицы', {})[имя] = t
# сегодняшние баунсы
итог['баунсы_сегодня'] = [dict(r) for r in c.execute(
    "select e.id, e.event_ts, r.email, r.inn, "
    "substr(coalesce(e.detail_json,''),1,90) d "
    "from events e left join recipients r on r.id=e.recipient_id "
    "where e.event_type='bounce' and e.event_ts >= date('now','-2 day') "
    "order by e.event_ts desc limit 12")]
итог['баунсов_всего'] = c.execute(
    "select count(*) from events where event_type='bounce'").fetchone()[0]
c.close(); c2.close()
print(json.dumps(итог, ensure_ascii=False, indent=1))
