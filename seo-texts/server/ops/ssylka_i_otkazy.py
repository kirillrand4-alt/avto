# -*- coding: utf-8 -*-
"""Связаны ли отказы «подозрение на спам» со ссылкой в теле письма.

43 отказа 554 5.7.1 - это НАШ почтовик не принял письмо. Доля растёт:
0.2% -> 2.1% -> 2.7% -> 7.6%. Из 43 двадцать два в кампании 11 (Meyer), а
у мейеровских писем в теле стоит ссылка на видео rutube. Голая ссылка на
видеохостинг в холодном письме - классический триггер спам-фильтра.

Считаем долю отказов отдельно для писем СО ссылкой и БЕЗ неё. Если разрыв
кратный - причина найдена и лечится текстом, а не паузой.
"""
import re
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT m.id, m.status, m.campaign_id, COALESCE(m.last_error,'') err, "
    "       COALESCE(cr.edited_body, cr.body, '') тело "
    "  FROM messages m LEFT JOIN confirm_reviews cr ON cr.message_id=m.id "
    " WHERE m.status IN ('sent','failed') "
    "   AND substr(COALESCE(m.updated_at,m.created_at),1,10) >= '2026-08-18'"
).fetchall()

def ссылки(т):
    т = str(т or "")
    return {
        "rutube": bool(re.search(r"rutube\.ru", т, re.I)),
        "любая ссылка": bool(re.search(r"https?://", т)),
    }

счёт = {}
for р in ряды:
    п = ссылки(р["тело"])
    спам = "554" in р["err"] and "suspicion of SPAM" in р["err"]
    for имя, есть in п.items():
        к = счёт.setdefault(имя, {True: Counter(), False: Counter()})
        к[есть]["отказ" if спам else "прошло"] += 1

for имя, к in счёт.items():
    print(f"\n=== {имя} ===")
    for есть in (True, False):
        о, п = к[есть]["отказ"], к[есть]["прошло"]
        всего = о + п
        print(f"  {'есть' if есть else 'нет ':<5}: писем {всего:>5}, отказов {о:>4}, "
              f"доля {(100.0*о/всего if всего else 0):>5.2f}%")

# и по кампаниям - у Meyer и КЦ письма разные
print("\n=== по кампаниям ===")
по_камп = {}
for р in ряды:
    спам = "554" in р["err"] and "suspicion of SPAM" in р["err"]
    к = по_камп.setdefault(int(р["campaign_id"] or 0), Counter())
    к["отказ" if спам else "прошло"] += 1
for камп in sorted(по_камп):
    о, п = по_камп[камп]["отказ"], по_камп[камп]["прошло"]
    всего = о + п
    print(f"  камп{камп:<3}: писем {всего:>5}, отказов {о:>4}, "
          f"доля {(100.0*о/всего if всего else 0):>5.2f}%")
