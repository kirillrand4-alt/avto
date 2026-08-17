# -*- coding: utf-8 -*-
"""Сколько почт добыто именно С САЙТОВ компаний, а не из выгрузок."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\sender\server')
import ploshchadki as PL  # noqa: E402

c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
c.row_factory = sqlite3.Row
итог = {'колонки_emails': [r[1] for r in c.execute('pragma table_info(emails)')],
        'колонки_email_sources': [r[1] for r in c.execute('pragma table_info(email_sources)')]}
итог['адресов_всего'] = c.execute('select count(*) from emails').fetchone()[0]
итог['компаний_с_почтой'] = c.execute(
    'select count(distinct inn) from emails').fetchone()[0]
try:
    итог['по_источникам'] = [dict(r) for r in c.execute(
        "select coalesce(source,'(пусто)') istochnik, count(*) skolko "
        'from email_sources group by 1 order by skolko desc limit 12')]
except Exception as e:  # noqa: BLE001
    итог['источники_ошибка'] = str(e)[:80]
c.close()
print(json.dumps(итог, ensure_ascii=False, indent=1)[:2500])
