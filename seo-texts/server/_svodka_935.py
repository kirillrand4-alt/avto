# -*- coding: utf-8 -*-
r"""Сколько компаний с паспортом ещё НЕ в «Партии 935» и почему."""
import json
import sqlite3

s = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True, timeout=60)
в_группе, в_панели = set(), set()
for инн, ex in s.execute("select coalesce(inn,''), coalesce(extra_json,'') "
                         'from recipients'):
    ц = ''.join(c for c in str(инн) if c.isdigit())
    if not ц:
        continue
    в_панели.add(ц)
    if 'Партия 935' in ex:
        в_группе.add(ц)
d = {'в_группе_компаний': len(в_группе),
     'строк_в_группе': s.execute(
         "select count(*) from recipients where extra_json like '%Партия 935%'"
     ).fetchone()[0]}
s.close()

e = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
с_паспортом = {str(r[0]) for r in e.execute(
    "select inn from site_facts where coalesce(facts_json,'')<>'' "
    'and coalesce(format,0)>=2')}
с_продукцией = {str(r[0]) for r in e.execute(
    "select inn from site_facts where coalesce(format,0)>=2 "
    "and facts_json like '%\"продукция\": [\"%'")}
чистый_адрес = {str(r[0]) for r in e.execute(
    "select distinct e.inn from emails e where (e.source in ('own-site','zenno') "
    "or e.source like 'сайт:%') and coalesce(e.pometka,'') not like '%спам-ловушк%' "
    "and coalesce(e.pometka,'') not like '%скрыт%' "
    "and coalesce(e.pometka,'') not like '%не использовать%'")}
e.close()
d['паспортов_всего'] = len(с_паспортом)
d['из_них_с_продукцией'] = len(с_продукцией)
d['с_паспортом_и_чистым_адресом'] = len(с_паспортом & чистый_адрес)
d['с_продукцией_и_адресом'] = len(с_продукцией & чистый_адрес)
d['НЕ_в_группе_с_продукцией_и_адресом'] = len(
    (с_продукцией & чистый_адрес) - в_группе)
d['НЕ_в_группе_с_паспортом_и_адресом'] = len(
    (с_паспортом & чистый_адрес) - в_группе)
d['без_чистого_адреса_из_паспортных'] = len(с_паспортом - чистый_адрес)
print(json.dumps(d, ensure_ascii=False, indent=1))
