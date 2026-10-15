# -*- coding: utf-8 -*-
"""Письма КЦ (кампания 15) стояли в общей очереди за ~1000 письмами Meyer того же
часа: автоотправка берёт по scheduled_at, id, а у КЦ id старше. Ящики у них свои
(pool_kc), так что ставим срок КЦ на минуту раньше — пойдут первыми, Meyer
не теряет ни одного слота своих ящиков."""
import sqlite3
from datetime import datetime, timedelta, timezone
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
т = (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S")
with c:
    n = c.execute("UPDATE messages SET scheduled_at=? WHERE campaign_id=15 AND status='scheduled' "
                  "AND scheduled_at<=?", (т, (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S"))).rowcount
print("писем КЦ поднято в начало очереди: %d" % n)
print("=== КЦ ВПЕРЁД ===")
