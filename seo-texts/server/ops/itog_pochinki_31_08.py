# -*- coding: utf-8 -*-
"""Только чтение: итоговое состояние после починки."""
import io
import sqlite3

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

print("=== КОД ===")
for ф, метка in ((r"C:\sender\sender\store.py", "уносил с собой ВСЁ, что стоит в sender.send"),
                 (r"C:\sender\sender\sender.py", "счётчик отправки не обновился")):
    t = io.open(ф, encoding="utf-8").read()
    import os
    print("  %-12s правка на месте: %s" % (os.path.basename(ф), метка in t))

print("\n=== СОСТОЯНИЕ ЯЩИКОВ ===")
n = s.execute("SELECT COUNT(*) n FROM mailbox_state").fetchone()["n"]
без = s.execute("SELECT COUNT(*) n FROM mailbox_state WHERE COALESCE(provider,'')=''"
                ).fetchone()["n"]
пауз = s.execute("SELECT COUNT(*) n FROM mailbox_state WHERE paused=1").fetchone()["n"]
print("  строк состояния: %d | на паузе: %d | с пустым provider: %d" % (n, пауз, без))

print("\n=== food-sort.ru ===")
for р in s.execute("SELECT mailbox_id, paused, sent_total FROM mailbox_state"
                   " WHERE mailbox_id LIKE '%food-sort%'"):
    print("  %-24s paused=%s sent_total=%s" % (р["mailbox_id"], р["paused"], р["sent_total"]))

print("\n=== ПИСЬМА ===")
for р in s.execute("SELECT status, COUNT(*) n FROM messages"
                   " WHERE status IN ('sending','scheduled','pending_review')"
                   " GROUP BY status"):
    print("  %-16s %d" % (р["status"], р["n"]))

print("\n=== ИТОГ: ОЧЕРЕДЬ ПОДТВЕРЖДЕНИЙ ===")
for р in s.execute("SELECT campaign_id k, status, COUNT(*) n FROM confirm_reviews"
                   " WHERE campaign_id IN (10,11) AND status IN ('pending','approved')"
                   " GROUP BY k, status ORDER BY k"):
    print("  кампания %-3s %-10s %5d" % (р["k"], р["status"], р["n"]))
