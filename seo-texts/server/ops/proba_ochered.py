# -*- coding: utf-8 -*-
"""Проба адресов у живых писем (на подтверждении и запланированных): вердикт addr_probe. Только чтение."""
import sqlite3
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
вер = {str(e).lower(): v for e, v in c.execute("SELECT email, verdict FROM addr_probe")}
сч = Counter()
for cid, st, em in c.execute("SELECT m.campaign_id, m.status, r.email FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                             "WHERE m.status IN ('pending_review','approved','scheduled')"):
    сч[(кам.get(cid, cid), "запланировано" if st in ("approved", "scheduled") else "на подтверждении",
        вер.get(str(em).lower(), "НЕ ПРОВЕРЕН"))] += 1
for k, v in sorted(сч.items()): print(v, k)
