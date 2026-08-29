# -*- coding: utf-8 -*-
"""Запись в стоп-листе появилась РАНЬШЕ письма или после?

Прошлый замер сравнивал ДАТЫ (первые 10 знаков) — письмо, написанное в 02:00
и отбившееся в 09:00 того же дня, попадало в «стоп-лист был раньше». Здесь
сравниваем полные отметки времени.
"""
import sqlite3
from collections import Counter
БАЗА = r"C:\sender\sender.db"
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
кол = {r["name"] for r in c.execute("PRAGMA table_info(confirm_reviews)")}
поле = "created_at" if "created_at" in кол else "updated_at"
print("время создания черновика берём из %s" % поле)
строки = list(c.execute(
    "SELECT cr.id, cr.status, cr.email, cr.%s AS sozdan, "
    "       s.reason, s.created_at AS v_stope "
    "  FROM confirm_reviews cr "
    "  JOIN suppression s ON s.value = LOWER(TRIM(cr.email)) "
    " WHERE s.scope='email'" % поле))
раньше, позже, неясно = [], [], []
for r in строки:
    a, b = str(r["v_stope"] or ""), str(r["sozdan"] or "")
    if not a or not b:
        неясно.append(r)
    elif a < b:
        раньше.append(r)
    else:
        позже.append(r)
print("черновиков на адрес из стоп-листа: %d" % len(строки))
print("   стоп-лист РАНЬШЕ письма (знали и всё равно писали): %d" % len(раньше))
print("   стоп-лист ПОЗЖЕ письма (отбилось после генерации):  %d" % len(позже))
print("   не сравнить: %d" % len(неясно))
пр, ст = Counter(), Counter()
for r in раньше:
    пр[str(r["reason"])[:30]] += 1
    ст[r["status"]] += 1
print("\nте, где знали заранее — причины: %s" % dict(пр.most_common(6)))
print("                        статусы: %s" % dict(ст.most_common(6)))
print("\n   примеры (свежие):")
for r in sorted(раньше, key=lambda x: str(x["sozdan"]))[-10:]:
    print("      review=%-7s %-28s создан %s, в стопе с %s (%s)"
          % (r["id"], str(r["email"])[:28], str(r["sozdan"])[:19],
             str(r["v_stope"])[:19], str(r["reason"])[:18]))
c.close()
