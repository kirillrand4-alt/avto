# -*- coding: utf-8 -*-
"""Есть ли телефоны «Росткрана» в базе и на самой странице."""
import gzip
import json
import os
import re
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
ИНН = None
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
r = s.execute("select inn from leads where lower(email)='chernyavin@rostkran.ru'").fetchone()
s.close()
ИНН = ''.join(c for c in str(r[0] or '') if c.isdigit()) if r else ''
итог = {'инн': ИНН}
c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
c.row_factory = sqlite3.Row
комп = c.execute('select * from companies where inn=?', (ИНН,)).fetchone()
if комп:
    d = dict(комп)
    итог['companies.phones'] = d.get('phones')
    итог['companies_поля_с_данными'] = {k: (str(v)[:70]) for k, v in d.items()
                                        if v not in (None, '', 0)}
итог['phone_contacts'] = [dict(x) for x in c.execute(
    'select * from phone_contacts where inn=?', (ИНН,))]
итог['people'] = [dict(x) for x in c.execute(
    'select * from people where inn=?', (ИНН,))]
итог['emails_с_людьми'] = [{'email': x['email'], 'role': x['role'],
                            'person': x['person']}
                           for x in c.execute(
    "select email, coalesce(role,'') role, coalesce(person,'') person "
    'from emails where inn=?', (ИНН,))]
c.close()
# что на странице
kesh = os.path.join(os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache'),
                    '%s.json.gz' % ИНН)
итог['кэш_есть'] = os.path.exists(kesh)
if os.path.exists(kesh):
    d = json.loads(gzip.open(kesh, 'rb').read().decode('utf-8', 'replace'))
    текст = ' '.join(re.sub(r'<[^>]+>', ' ', (p.get('html') or ''))
                     for p in (d.get('pages') or []))
    номера = re.findall(r'(?:\+7|8)[\s(\-]*\d{3}[\s)\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}', текст)
    итог['номеров_на_страницах'] = len(номера)
    итог['примеры_номеров'] = sorted(set(номера))[:6]
    итог['страниц_в_кэше'] = len(d.get('pages') or [])
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
