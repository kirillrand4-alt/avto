# -*- coding: utf-8 -*-
"""Снятия автоотправкой «уже писали» по дням и кампаниям; копия auto_send.py на дроп."""
import shutil
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
for день, камп, n in c.execute(
        "SELECT substr(updated_at,1,10), campaign_id, count(*) FROM messages "
        "WHERE status='skipped' AND last_error LIKE 'auto_send:уже писали%' "
        "AND updated_at >= '2026-10-10' GROUP BY 1,2 ORDER BY 1,2"):
    print("%s кампания %s: %d" % (день, камп, n))
shutil.copy2(r"C:\sender\sender\auto_send.py", r"C:\seostat\drop\drop-storage\auto_send_server_1410.py")
print("=== УЖЕ ПИСАЛИ ПО ДНЯМ ===")
