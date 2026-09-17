# -*- coding: utf-8 -*-
"""Что у НАС по ИНН 2222849751 (БЗВС) против карточки из их ЛК."""
import json, sqlite3
c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=30)
ИНН = '2222849751'
o = {}
o['компания'] = c.execute(
    "select inn, coalesce(name,''), coalesce(site,''), coalesce(division,''), "
    "coalesce(region,''), coalesce(best_email,'') from companies where inn=?", (ИНН,)).fetchall()
o['адреса'] = c.execute(
    "select email, coalesce(role,''), coalesce(source,''), coalesce(source_url,'') "
    'from emails where inn=? limit 12', (ИНН,)).fetchall()
o['телефоны'] = c.execute(
    'select * from phone_contacts where inn=? limit 8', (ИНН,)).fetchall()
o['колонки_телефонов'] = [r[1] for r in c.execute('pragma table_info(phone_contacts)')]
o['сигналы'] = c.execute(
    "select source, event_type, substr(what,1,70), coalesce(sum,'') from signals where inn=? limit 5",
    (ИНН,)).fetchall()
c.close()
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1, default=str)[:4000])
