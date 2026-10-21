# -*- coding: utf-8 -*-
r"""fixKR (21.10): комментарии user3 в панели КЦ и сколько его компаний скрыто целиком. Только чтение.

    python3 zapusk_na_servere.py fixKR_kommentarii.py
"""
import re
import sqlite3

s = sqlite3.connect(r'file:C:\seostat\data\centro_sales.db?mode=ro', uri=True)
print('компаний user3, скрытых ЦЕЛИКОМ (kind=company):', s.execute(
    "SELECT COUNT(DISTINCT inn) FROM hidden_item WHERE kind='company' AND inn IN (SELECT inn FROM company_assignment WHERE username='user3')").fetchone()[0])
print('компаний user1/user2, скрытых целиком:', s.execute(
    "SELECT a.username, COUNT(DISTINCT h.inn) FROM hidden_item h JOIN company_assignment a ON a.inn=h.inn WHERE h.kind='company' GROUP BY 1").fetchall())
k = None
for p in (r'C:\seostat\data\centro.db', r'C:\seostat\data\centrifugal.db'):
    try:
        k = sqlite3.connect('file:%s?mode=ro' % p, uri=True)
        k.execute('SELECT 1 FROM company LIMIT 1')
        break
    except sqlite3.Error:
        k = None
for inn, body, kogda, kto in s.execute("SELECT inn, body, created_at, username FROM company_comment WHERE username='user3' ORDER BY created_at"):
    naz = ''
    if k:
        try:
            r = k.execute('SELECT name FROM company WHERE inn=?', (inn,)).fetchone()
            naz = r[0] if r else ''
        except sqlite3.Error:
            pass
    body = re.sub(r'(\+7|\b8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}', '[номер]', body or '')
    print('\n%s %s | %s\n   %s' % (str(kogda)[:16], inn, naz, body.replace('\n', ' / ')[:500]))
