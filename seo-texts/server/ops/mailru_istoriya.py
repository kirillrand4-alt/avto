# -*- coding: utf-8 -*-
"""Когда mail.ru (mail/bk/list/inbox) перестал различать ящики для нашей пробы: вердикты по дням. Только чтение."""
import sqlite3
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
for д, v, n in c.execute("SELECT substr(ts,1,10), verdict, COUNT(*) FROM addr_probe WHERE source='проба' AND (email LIKE '%@mail.ru' OR email LIKE '%@bk.ru' OR email LIKE '%@list.ru' OR email LIKE '%@inbox.ru') "
                         "AND ts>='2026-10-25' GROUP BY 1,2 ORDER BY 1,2"):
    print(д, v, n)
