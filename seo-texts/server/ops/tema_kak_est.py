# -*- coding: utf-8 -*-
"""Тема партии ровно как она лежит в базе, по символам."""
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

store = Store(r"C:\sender\sender.db")
с = Counter()
with store._lock:
    for р in store._conn.execute(
            "SELECT subject, COUNT(*) c FROM confirm_reviews "
            " WHERE subject LIKE '%ортировк%' GROUP BY subject"):
        с[str(р["subject"])] = int(р["c"])
print("=" * 74)
print("=== ТЕМЫ С «СОРТИРОВК» В ОЧЕРЕДИ ===")
for т, n in с.most_common():
    print("")
    print("   %5d писем | %r" % (n, т))
    print("   по словам: %s" % " | ".join(т.split(" ")))
