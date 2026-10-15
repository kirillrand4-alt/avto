# -*- coding: utf-8 -*-
"""Письма КЦ с новым текстом (без шаблонных фраз): сколько отправлено, отказов, в очереди — с утра 15.10."""
import re
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db")
ШАБ = re.compile(r"(?i)КП\s+с\s+цен|успеть\s+до\s+конца\s+года")
from collections import Counter
с = Counter()
for st, тело, тема in c.execute("SELECT m.status, cr.body, m.subject FROM messages m JOIN confirm_reviews cr ON cr.message_id=m.id "
                                "WHERE m.campaign_id IN (15,16) AND m.updated_at>=date('now')"):
    вид = "старый" if (ШАБ.search(тело or "") or re.search(r"(?i)до\s+конца\s+года", тема or "")) else "новый"
    с[(вид, st)] += 1
for к in sorted(с):
    print(к, с[к])
print("=== НОВЫЕ УШЛИ ===")
