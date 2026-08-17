# -*- coding: utf-8 -*-
"""Проверка на живых данных: новая строка компании сама получает ОКВЭД из обзвона."""
import json
import sqlite3
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

c = sqlite3.connect(r'C:\sender\enrich.db')
# берём ИНН, который ЕСТЬ в обзвоне и которого НЕТ в companies
o = sqlite3.connect(r'C:\sender\obzvon-index.db')
есть = {str(r[0]) for r in c.execute('select inn from companies')}
кандидат = None
for inn, ок in o.execute("select inn, coalesce(okved_main,'') from obzvon where okved_main<>''"):
    if str(inn) not in есть:
        кандидат = (str(inn), ок)
        break
o.close()
c.close()
if not кандидат:
    print(json.dumps({'некого пробовать': True}, ensure_ascii=False))
    sys.exit(0)
inn, ждём = кандидат
db = EDB.EnrichDB()
db.upsert_company(inn, site='проба-обзвона.example')       # ОКВЭД НЕ передаём
c = sqlite3.connect(r'C:\sender\enrich.db')
r = c.execute("select coalesce(okved,''), coalesce(name,''), coalesce(ogrn,'') "
              "from companies where inn=?", (inn,)).fetchone()
c.execute('delete from companies where inn=? and site=?', (inn, 'проба-обзвона.example'))
c.commit()
c.close()
print(json.dumps({'инн': inn, 'ждали_оквэд': ждём[:40], 'получили_оквэд': r[0][:40],
                  'имя': r[1][:40], 'огрн': r[2],
                  'сработало': bool(r[0]) and r[0][:8] == ждём[:8]}, ensure_ascii=False))
