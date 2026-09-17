# -*- coding: utf-8 -*-
import json, sqlite3
c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=30)
ИНН='2222849751'
o={'компания': c.execute(
    "select coalesce(name,''), coalesce(site,''), coalesce(division,''), coalesce(best_email,'') "
    'from companies where inn=?', (ИНН,)).fetchall(),
   'адреса': c.execute(
    "select email, coalesce(role,''), coalesce(source,'') from emails where inn=? limit 10",
    (ИНН,)).fetchall(),
   'телефонов_всего': c.execute('select count(*) from phone_contacts where inn=?', (ИНН,)).fetchone()[0]}
c.close()
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1, default=str)[:2500])
