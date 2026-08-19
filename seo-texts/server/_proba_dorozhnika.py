# -*- coding: utf-8 -*-
r"""Контрольный разбор: ловится ли теперь «Дорожник-2» из справки."""
import json
import os
import sqlite3
import sys

for _p in (r'C:\sender\server',):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import site_facts as SF  # noqa: E402

ИНН = sys.argv[1] if len(sys.argv) > 1 else '2263030778'
c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
r = c.execute("select facts_json from site_facts where inn=?", (ИНН,)).fetchone()
c.close()
if not r:
    print(json.dumps({'нет паспорта': ИНН}, ensure_ascii=False))
    raise SystemExit
ф = json.loads(r[0])
print(json.dumps({
    'инн': ИНН,
    'продукция': ф.get('продукция'),
    'оборудование_линии': ф.get('оборудование_линии'),
    'цитата': ф.get('цитата'),
    'было': ф.get('разбор_КЦ'),
    'стало': SF.razlozhit_energohozyaystvo(ф),
}, ensure_ascii=False, indent=1))
