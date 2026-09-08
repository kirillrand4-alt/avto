# -*- coding: utf-8 -*-
"""Статусы карточек и писем партии прямо сейчас: что можно менять, что уже нет."""
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

ТЕМА = "Для качества: вопрос по сортировке зерна"
store = Store(r"C:\sender\sender.db")
карт = Counter()
писем = Counter()
пары = Counter()
with store._lock:
    for р in store._conn.execute(
            """SELECT c.status AS cst, m.status AS mst
                 FROM confirm_reviews c LEFT JOIN messages m
                      ON c.message_id = m.id
                WHERE c.subject=?""", (ТЕМА,)):
        карт[str(р["cst"])] += 1
        писем[str(р["mst"] or "нет письма")] += 1
        пары[(str(р["cst"]), str(р["mst"] or "нет письма"))] += 1
print("=" * 70)
print("=== ПАРТИЯ СЕЙЧАС ===")
print("карточки:")
for к, в in карт.most_common():
    print("   %-16s %5d" % (к, в))
print("письма:")
for к, в in писем.most_common():
    print("   %-16s %5d" % (к, в))
print("пары карточка/письмо:")
for (a, b), в in пары.most_common(10):
    print("   %-14s / %-16s %5d" % (a, b, в))
