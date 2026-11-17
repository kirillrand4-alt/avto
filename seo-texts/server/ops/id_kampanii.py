# -*- coding: utf-8 -*-
"""id кампании по имени и счёт карточек по статусам: id_kampanii.py "<имя>". Только чтение."""
import sqlite3, sys
к = sqlite3.connect(r"file:C:\sender\sender.db?mode=ro", uri=True)
for i, н in к.execute("SELECT id, name FROM campaigns WHERE name=?", (sys.argv[1],)):
    print(i, н, dict(к.execute("SELECT status, COUNT(*) FROM confirm_reviews WHERE campaign_id=? GROUP BY status", (i,)).fetchall()))
