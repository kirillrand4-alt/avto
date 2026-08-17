# -*- coding: utf-8 -*-
"""У компаний с чистой почтой с сайта — какой версией собран паспорт."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
САЙТОВЫЕ = "(e.source in ('own-site','zenno') or e.source like 'сайт:%')"
ЧИСТЫЕ = ("coalesce(e.pometka,'') not like '%спам-ловушк%' "
          "and coalesce(e.pometka,'') not like '%скрыт%' "
          "and coalesce(e.pometka,'') not like '%не использовать%'")
БАЗА = ("select distinct e.inn from emails e where %s and %s" % (САЙТОВЫЕ, ЧИСТЫЕ))
итог = {}
итог['компаний_с_чистой_почтой_с_сайта'] = c.execute(
    'select count(*) from (%s)' % БАЗА).fetchone()[0]
итог['паспорт_текущей_версии'] = c.execute(
    "select count(*) from (%s) b join site_facts f on f.inn=b.inn "
    "where coalesce(f.facts_json,'')<>'' and coalesce(f.format,0)>=2" % БАЗА).fetchone()[0]
итог['паспорт_старой_версии'] = c.execute(
    "select count(*) from (%s) b join site_facts f on f.inn=b.inn "
    "where coalesce(f.facts_json,'')<>'' and coalesce(f.format,0)<2" % БАЗА).fetchone()[0]
итог['паспорта_нет_вовсе'] = c.execute(
    "select count(*) from (%s) b where not exists(select 1 from site_facts f "
    "where f.inn=b.inn and coalesce(f.facts_json,'')<>'')" % БАЗА).fetchone()[0]
итог['текущей_версии_и_с_продукцией'] = c.execute(
    "select count(*) from (%s) b join site_facts f on f.inn=b.inn "
    "where coalesce(f.format,0)>=2 and f.facts_json like '%%\"продукция\": [\"%%'" % БАЗА
).fetchone()[0]
итог['текущей_версии_и_признак_наш'] = c.execute(
    "select count(*) from (%s) b join companies k on k.inn=b.inn "
    "join site_facts f on f.inn=b.inn where coalesce(f.format,0)>=2 "
    "and coalesce(k.nash_priznak,'') not in ('', 'нет', 'неизвестно')" % БАЗА).fetchone()[0]
c.close()
print(json.dumps(итог, ensure_ascii=False, indent=1))
