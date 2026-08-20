# -*- coding: utf-8 -*-
r"""Успевает ли проба до отправки: покрытие очереди автоотправки вердиктами."""
import json, sqlite3
c = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
c.row_factory = sqlite3.Row
итог = {}
итог['вердикты'] = dict(c.execute(
    'select verdict, count(*) from addr_probe group by verdict '
    'order by count(*) desc').fetchall())
итог['по_источнику'] = dict(c.execute(
    "select coalesce(source,''), count(*) from addr_probe group by 1 "
    'order by 2 desc').fetchall())
# отправленные: был ли вердикт ДО отправки
итог['отправлено_всего'] = c.execute(
    'select count(*) from send_log').fetchone()[0]
r = c.execute("""
  select
    sum(case when p.email is null then 1 else 0 end) as без_вердикта,
    sum(case when p.email is not null and p.ts < s.ts then 1 else 0 end) as вердикт_был_до,
    sum(case when p.email is not null and p.ts >= s.ts then 1 else 0 end) as вердикт_после,
    count(*) as всего
  from send_log s left join addr_probe p on lower(p.email)=lower(s.email)
""").fetchone()
итог['отправки_и_проба'] = dict(r)
# сколько получателей в панели вообще имеют вердикт
итог['получателей'] = c.execute('select count(*) from recipients').fetchone()[0]
итог['получателей_с_вердиктом'] = c.execute(
    'select count(*) from recipients r join addr_probe p '
    'on lower(p.email)=lower(r.email)').fetchone()[0]
c.close()
print(json.dumps(итог, ensure_ascii=False, indent=1))
