# -*- coding: utf-8 -*-
"""У скольких забракованных писем кампании 14 сохранился текст."""
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
всего, с_текстом = 0, 0
for р in c.execute("SELECT body FROM ai_letter_log WHERE campaign_id=14 "
                   "AND status!='ok'"):
    всего += 1
    if (р[0] or "").strip():
        с_текстом += 1
print("брак кампании 14: %d, с сохранённым текстом: %d" % (всего, с_текстом))
print("=== БРАК С ТЕКСТОМ ===")
