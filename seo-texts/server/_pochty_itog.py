# -*- coding: utf-8 -*-
"""Точные числа по почтам с сайтов: сколько адресов, компаний, что отсеивается."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
САЙТОВЫЕ = "(source in ('own-site','zenno') or source like 'сайт:%')"
ЧИСТЫЕ = ("coalesce(pometka,'') not like '%спам-ловушк%' "
          "and coalesce(pometka,'') not like '%скрыт%' "
          "and coalesce(pometka,'') not like '%не использовать%'")
итог = {}
итог['адресов_с_сайтов'] = c.execute(
    'select count(*) from emails where %s' % САЙТОВЫЕ).fetchone()[0]
итог['компаний_с_почтой_с_сайта'] = c.execute(
    'select count(distinct inn) from emails where %s' % САЙТОВЫЕ).fetchone()[0]
итог['адресов_чистых'] = c.execute(
    'select count(*) from emails where %s and %s' % (САЙТОВЫЕ, ЧИСТЫЕ)).fetchone()[0]
итог['компаний_чистых'] = c.execute(
    'select count(distinct inn) from emails where %s and %s' % (САЙТОВЫЕ, ЧИСТЫЕ)).fetchone()[0]
итог['отсеяно_ловушек_и_скрытых'] = c.execute(
    "select count(*) from emails where %s and (coalesce(pometka,'') like '%%спам-ловушк%%' "
    "or coalesce(pometka,'') like '%%скрыт%%')" % САЙТОВЫЕ).fetchone()[0]
итог['отсеяно_холдингов'] = c.execute(
    "select count(*) from emails where %s and coalesce(pometka,'') like '%%не использовать%%'"
    % САЙТОВЫЕ).fetchone()[0]
итог['из_них_best_email_проставлен'] = c.execute(
    "select count(*) from companies k where coalesce(k.best_email,'')<>'' "
    'and exists(select 1 from emails e where e.inn=k.inn and %s and %s)'
    % (САЙТОВЫЕ, ЧИСТЫЕ)).fetchone()[0]
итог['почта_из_обзвона_без_сайта'] = c.execute(
    "select count(*) from companies k where coalesce(k.best_email,'')<>'' "
    'and not exists(select 1 from emails e where e.inn=k.inn and %s)' % САЙТОВЫЕ).fetchone()[0]
c.close()
print(json.dumps(итог, ensure_ascii=False, indent=1))
