# -*- coding: utf-8 -*-
"""Что мы знаем про человека, чьё имя подтвердил сам адрес: только фамилию или больше."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
c.row_factory = sqlite3.Row
итог = {}
итог['адресов_imya_ok'] = c.execute('select count(*) from emails where imya_ok=1').fetchone()[0]
итог['по_роли'] = [dict(r) for r in c.execute(
    "select coalesce(role,'(пусто)') rol, count(*) skolko from emails where imya_ok=1 "
    'group by 1 order by skolko desc limit 10')]
итог['с_отчеством'] = c.execute(
    "select count(*) from emails where imya_ok=1 and person like '% % %'").fetchone()[0]
итог['только_инициалы'] = c.execute(
    "select count(*) from emails where imya_ok=1 and person like '%.%'").fetchone()[0]
итог['есть_должность_в_people'] = c.execute(
    "select count(*) from emails e where e.imya_ok=1 and exists("
    " select 1 from people p where p.inn=e.inn and coalesce(p.post,'')<>'' "
    " and (p.person=e.person or p.email=e.email))").fetchone()[0]
итог['есть_ссылка_источник'] = c.execute(
    "select count(*) from emails where imya_ok=1 and coalesce(source_url,'')<>''"
).fetchone()[0]
итог['есть_раздел_страницы'] = c.execute(
    "select count(*) from emails where imya_ok=1 and coalesce(razdel,'')<>''").fetchone()[0]
итог['примеры'] = [dict(r) for r in c.execute(
    "select e.inn, e.email, e.person, coalesce(e.role,'') role, "
    "coalesce(e.razdel,'') razdel, substr(coalesce(e.source_url,''),1,50) url, "
    "(select group_concat(p.post,' / ') from people p where p.inn=e.inn "
    "  and (p.person=e.person or p.email=e.email)) dolzhnost "
    'from emails e where e.imya_ok=1 limit 6')]
c.close()
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
