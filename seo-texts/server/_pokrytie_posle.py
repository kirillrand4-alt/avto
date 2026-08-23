# -*- coding: utf-8 -*-
r"""Насколько выросло покрытие телефонами и ролями после прогона."""
import json
import sqlite3

c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
d = {
    'строк_всего': c.execute('select count(*) from phone_contacts').fetchone()[0],
    'компаний_с_номером': c.execute(
        'select count(distinct inn) from phone_contacts').fetchone()[0],
    'компаний_с_ролью': c.execute(
        "select count(distinct inn) from phone_contacts "
        "where coalesce(role,'') not in ('','общий')").fetchone()[0],
    'строк_с_ролью': c.execute(
        "select count(*) from phone_contacts where coalesce(role,'') "
        "not in ('','общий')").fetchone()[0],
}
d['роли_всего'] = {r[0]: r[1] for r in c.execute(
    "select role, count(*) k from phone_contacts where coalesce(role,'') "
    "not in ('','общий') group by role order by k desc limit 12")}
# та же мерка по «Партии 935»
s = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True, timeout=60)
инн935 = set()
for инн, ex in s.execute("select coalesce(inn,''), coalesce(extra_json,'') from recipients"):
    if 'Партия 935' in ex:
        ц = ''.join(x for x in str(инн) if x.isdigit())
        if ц:
            инн935.add(ц)
s.close()
с_номером = {str(r[0]) for r in c.execute('select distinct inn from phone_contacts')}
с_ролью = {str(r[0]) for r in c.execute(
    "select distinct inn from phone_contacts where coalesce(role,'') "
    "not in ('','общий')")}
c.close()
d['партия_935'] = {'компаний': len(инн935),
                   'с_номером_строками': len(инн935 & с_номером),
                   'с_ролью': len(инн935 & с_ролью)}
print(json.dumps(d, ensure_ascii=False, indent=1))
