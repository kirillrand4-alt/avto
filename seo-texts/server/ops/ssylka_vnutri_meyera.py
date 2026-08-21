# -*- coding: utf-8 -*-
"""Та же проверка ВНУТРИ одной кампании - иначе это не причина, а совпадение.

Письма со ссылкой почти все мейеровские, а у Meyer и текст другой, и
домены другие. Чтобы отделить ссылку от «мейеровости», сравниваем со
ссылкой и без неё ВНУТРИ кампании 11, и заодно внутри 10.
"""
import re
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT m.id, m.campaign_id, COALESCE(m.last_error,'') err, "
    "       COALESCE(cr.edited_body, cr.body, '') тело "
    "  FROM messages m LEFT JOIN confirm_reviews cr ON cr.message_id=m.id "
    " WHERE m.status IN ('sent','failed') "
    "   AND substr(COALESCE(m.updated_at,m.created_at),1,10) >= '2026-08-18'"
).fetchall()
св = {}
for р in ряды:
    камп = int(р["campaign_id"] or 0)
    есть = bool(re.search(r"https?://", str(р["тело"] or "")))
    спам = "554" in р["err"] and "suspicion of SPAM" in р["err"]
    к = св.setdefault(камп, {True: Counter(), False: Counter()})
    к[есть]["отказ" if спам else "прошло"] += 1
for камп in sorted(св):
    если = св[камп]
    строки = []
    for есть in (True, False):
        о, п = если[есть]["отказ"], если[есть]["прошло"]
        в = о + п
        if в:
            строки.append(f"{'со ссылкой' if есть else 'без ссылки'}: "
                          f"{в:>4} писем, отказов {о:>3} = "
                          f"{(100.0*о/в):>5.2f}%")
    if строки:
        print(f"камп{камп}:")
        for с in строки:
            print(f"   {с}")
