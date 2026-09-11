# -*- coding: utf-8 -*-
"""На чём упали письма партии: разбор last_error у failed."""
import re, sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server\ops")
from sender.store import Store                                  # noqa: E402
import varianty_pisma as V                                      # noqa: E402

store = Store(r"C:\sender\sender.db")
с = Counter()
по_ящику = Counter()
по_часам = Counter()
примеры = {}
with store._lock:
    for р in store._conn.execute(
            """SELECT m.id, m.last_error, m.mailbox_id, m.updated_at,
                      m.attempt_count, r.email
                 FROM confirm_reviews c
                 JOIN messages m ON c.message_id = m.id
                 LEFT JOIN recipients r ON m.recipient_id = r.id
                WHERE c.subject IN (%s) AND m.status='failed'"""
            % ",".join("?" * len(V.ТЕМЫ)), tuple(V.ТЕМЫ)):
        т = " ".join(str(р["last_error"] or "нет текста ошибки").split())
        ключ = re.sub(r"\d{3,}", "N", т)[:90]
        с[ключ] += 1
        по_ящику[str(р["mailbox_id"] or "не задан")] += 1
        по_часам[str(р["updated_at"] or "")[:13]] += 1
        примеры.setdefault(ключ, (р["id"], str(р["email"] or ""), т))
print("")
print("--- по ящикам ---")
for к, в in по_ящику.most_common(8):
    print("   %-42s %5d" % (к[:42], в))
print("")
print("--- когда падали (топ-10 часов) ---")
for к in sorted(по_часам)[-10:]:
    print("   %s  %5d" % (к, по_часам[к]))
print("")
print("=" * 74)
print("=== FAILED В ПАРТИИ: %d ===" % sum(с.values()))
print("")
print("--- причины падения (топ-6) ---")
for к, в in с.most_common(6):
    i, поч, полный = примеры[к]
    print("   %5d  %s" % (в, полный[:170]))
    print("          пример: письмо %s → %s" % (i, поч[:40]))
