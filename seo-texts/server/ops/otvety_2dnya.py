# -*- coding: utf-8 -*-
"""Входящие за 2 дня по типам событий и новые лиды — для сверки «всё ли дошло»."""
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
print(c.execute("SELECT event_type, count(*) FROM events WHERE event_ts >= date('now','-2 day') "
                "AND event_type NOT IN ('sent','delivered','open','click') GROUP BY 1").fetchall())
print("лиды за 2 дня:", c.execute("SELECT count(*), group_concat(reply_kind) FROM leads WHERE created_at >= date('now','-2 day')").fetchone())
print("=== ОТВЕТЫ 2 ДНЯ ===")
