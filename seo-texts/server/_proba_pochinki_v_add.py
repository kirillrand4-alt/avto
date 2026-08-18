# -*- coding: utf-8 -*-
"""Проверка: add_email теперь чинит адрес на входе (на временной копии базы)."""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, r'C:\sender\server')
sys.stdout.reconfigure(encoding='utf-8')
врем = os.path.join(tempfile.gettempdir(), 'proba_enrich.db')
shutil.copy(r'C:\sender\enrich.db', врем)
os.environ['ENRICH_DB'] = врем
import enrich_db as ED  # noqa: E402

db = ED.EnrichDB(врем)
проба = [('9999999901', 'ba%6d_%74%70@proba.ru'), ('9999999902', 'sаturn@proba.ru'),
         ('9999999903', 'rys yatov@proba.ru'), ('9999999904', '-mailinfo@proba.ru'),
         ('9999999905', 'normal@proba.ru')]
for инн, адрес in проба:
    db.upsert_company(инн, name='проба')
    db.add_email(инн, адрес, source='проба')
из = []
import sqlite3
c = sqlite3.connect(врем)
for инн, было in проба:
    r = c.execute("select email, coalesce(pometka,'') from emails where inn=?",
                  (инн,)).fetchone()
    из.append({'было': было, 'стало': r[0] if r else None,
               'пометка': (r[1] if r else '')[:40]})
c.close()
try:
    db.cx.close()
except Exception:
    pass
print(json.dumps(из, ensure_ascii=False, indent=1))
