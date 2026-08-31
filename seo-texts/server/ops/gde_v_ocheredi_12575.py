# -*- coding: utf-8 -*-
"""На каком месте в очереди стоит карточка 12575."""
import sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
c.row_factory = sqlite3.Row
всего = c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE status='pending'"
                  ).fetchone()[0]
раньше = c.execute("SELECT COUNT(*) FROM confirm_reviews"
                   " WHERE status='pending' AND id < 12575").fetchone()[0]
print("pending всего: %d; карточек с меньшим id: %d" % (всего, раньше))
print("то есть 12575 стоит на месте %d при сортировке по id ASC" % (раньше + 1))
print("\nразбивка pending по kind и кампании:")
for r in c.execute("SELECT COALESCE(kind,'outbound') k, campaign_id, COUNT(*) n"
                   "  FROM confirm_reviews WHERE status='pending'"
                   " GROUP BY k, campaign_id ORDER BY n DESC"):
    print("   %-9s кампания %-5s %5d" % (r[0], r[1], r[2]))
print("\nпервые пять pending по id ASC (что оператор видит сверху):")
for r in c.execute("SELECT id, COALESCE(kind,'outbound') k, campaign_id,"
                   "       email, substr(created_at,1,16) c"
                   "  FROM confirm_reviews WHERE status='pending'"
                   " ORDER BY id ASC LIMIT 5"):
    print("   %6s %-9s к%-5s %-28s %s" % tuple(r))
print("\nпоследние пять pending по id ASC (хвост):")
for r in c.execute("SELECT id, COALESCE(kind,'outbound') k, campaign_id,"
                   "       email, substr(created_at,1,16) c"
                   "  FROM confirm_reviews WHERE status='pending'"
                   " ORDER BY id DESC LIMIT 5"):
    print("   %6s %-9s к%-5s %-28s %s" % tuple(r))
c.close()
print("\n=== ИТОГ ===")
print("confirm_list сортирует по id ASC и отдаёт страницами; новый ответ")
print("оказывается в самом конце, а не сверху.")
