# -*- coding: utf-8 -*-
"""Сверка после возврата: вся вечерняя партия 24.08 должна сойтись без остатка,
и каждое возвращённое письмо обязано иметь одобренную карточку — иначе
автоотправка его просто не увидит.
"""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT cr.status st, COALESCE(m.status,'нет письма') ms, "
    "       COALESCE(NULLIF(m.last_error,''),'') le "
    "  FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id "
    " WHERE cr.decided_by='kirill' AND substr(cr.decided_at,1,10)='2026-08-24' "
    "   AND substr(cr.decided_at,12,2) >= '11'").fetchall()
print("вечерняя партия владельца 24.08: %d" % len(ряды))
for к, н in Counter("карта %s / письмо %s" % (р["st"], р["ms"])
                    for р in ряды).most_common():
    print("   %-40s %5d" % (к, н))
плохо = [р for р in ряды if р["ms"] == "scheduled" and р["st"] != "approved"]
print("возвращено, но карточка не одобрена (автоотправка не увидит): %d" % len(плохо))
осталось = [р for р in ряды if р["ms"] == "skipped"]
print("осталось снятыми: %d" % len(осталось))
for к, н in Counter(р["le"][:56] for р in осталось).most_common(6):
    print("   %-56s %4d" % (к, н))
print("\nочередь отправки целиком: %d"
      % c.execute("SELECT COUNT(*) FROM messages "
                  " WHERE status IN ('scheduled','sending')").fetchone()[0])
