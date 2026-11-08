# -*- coding: utf-8 -*-
"""Статусы карточек и писем по кампаниям «КЦ по имени 06.11» и «КЦ закупщики 08.11»."""
import sqlite3
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=30)
for (имя,) in [("КЦ по имени 06.11",), ("КЦ закупщики 08.11",)]:
    к = c.execute("SELECT id FROM campaigns WHERE name=?", (имя,)).fetchone()
    if not к: print(имя, "нет кампании"); continue
    print("==", имя)
    print("  карточки:", c.execute("SELECT status, COUNT(*) FROM confirm_reviews WHERE campaign_id=? GROUP BY 1", (к[0],)).fetchall())
    print("  письма:  ", c.execute("SELECT status, COUNT(*) FROM messages WHERE campaign_id=? GROUP BY 1", (к[0],)).fetchall())
    print("  причины skipped:", c.execute("SELECT substr(COALESCE(reason,''),1,40), COUNT(*) FROM confirm_reviews WHERE campaign_id=? AND status='skipped' GROUP BY 1 ORDER BY 2 DESC LIMIT 6", (к[0],)).fetchall())
