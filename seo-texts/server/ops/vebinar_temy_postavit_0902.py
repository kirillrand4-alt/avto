# -*- coding: utf-8 -*-
"""Проставить темы владельца по всем письмам кампании 12.
Правим оба места: решение оператора и само письмо. argv: проба | делать"""
import datetime as dt
import sqlite3
import sys
from collections import Counter

ДЕЛАТЬ = (sys.argv[1] if len(sys.argv) > 1 else "проба") == "делать"
ТЕМЫ = [
    "Контроль качества на производстве: в продолжение вебинара про ИИ в пищевке",
    "В продолжение вебинара со Стартом качества",
    "Контроль посторонних включений на производстве: в продолжение вебинара про ИИ в пищевке",
]
for т in ТЕМЫ:
    if len(т.split()) > 12:
        raise SystemExit("тема длиннее 12 слов, гейт не пропустит: %s" % т)

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = list(c.execute("SELECT id, message_id, subject FROM confirm_reviews"
                      " WHERE campaign_id=12 ORDER BY id"))
print("писем: %d" % len(ряды))
план = [(р["id"], р["message_id"], ТЕМЫ[i % len(ТЕМЫ)]) for i, р in enumerate(ряды)]
print("раскладка: %s" % Counter(т[:34] for _, _, т in план).most_common())

if not ДЕЛАТЬ:
    print("ничего не изменено (режим пробы)")
    raise SystemExit(0)

сейчас = dt.datetime.now().isoformat()
о1 = о2 = 0
for рид, мид, тема in план:
    c.execute("UPDATE confirm_reviews SET subject=?, updated_at=? WHERE id=?",
              (тема, сейчас, рид))
    о1 += 1
    if мид:
        о2 += c.execute("UPDATE messages SET subject=?, updated_at=? WHERE id=?"
                        " AND status NOT IN ('sent','skipped','failed')",
                        (тема, сейчас, мид)).rowcount
c.commit()
print("обновлено решений %d, писем %d" % (о1, о2))

print("\n=== ПРОВЕРКА ===")
for р in c.execute("SELECT subject, COUNT(*) n FROM messages WHERE campaign_id=12"
                   " GROUP BY subject ORDER BY n DESC"):
    print("  %3d | %s" % (р["n"], р["subject"]))
чужих = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12"
                  " AND subject NOT IN (?,?,?)", ТЕМЫ).fetchone()[0]
print("  писем с посторонней темой: %d" % чужих)
