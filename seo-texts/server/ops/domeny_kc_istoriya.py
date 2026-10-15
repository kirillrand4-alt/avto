# -*- coding: utf-8 -*-
"""История доменов КЦ: отправки и спам-отказы по дням и доменам."""
import sqlite3
from collections import defaultdict
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
т = defaultdict(lambda: [0, 0])
for мб, тип, д in c.execute("SELECT mailbox_id, event_type, substr(event_ts,1,10) FROM events WHERE event_type IN ('sent','reject_spam') "
                            "AND (mailbox_id LIKE '%compressor-%' OR mailbox_id LIKE '%kompressor-%')"):
    дом = мб.split("@")[1]
    т[(д, дом)][0 if тип == "sent" else 1] += 1
for (д, дом), (s, r) in sorted(т.items())[-60:]:
    print("%s %-28s отправлено %4d  спам-отказ %3d" % (д, дом, s, r))
print("=== ИСТОРИЯ ДОМЕНОВ КЦ ===")
