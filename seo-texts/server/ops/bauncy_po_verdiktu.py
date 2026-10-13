# -*- coding: utf-8 -*-
"""Отбои за сегодня относительно отправленного — по вердикту пробы ДО отправки."""
import io
import json
import sqlite3
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
до = {}
for с in io.open(r"C:\sender\_ops\smtp-proba-partiy.jsonl", encoding="utf-8", errors="replace"):
    try:
        z = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    до.setdefault(z.get("email"), z.get("verdict"))
ушло, отбой = Counter(), Counter()
отбитые = {р[0] for р in c.execute("SELECT DISTINCT message_id FROM events WHERE event_type LIKE '%bounce%' "
                                    "AND created_at >= date('now')")}
for р in c.execute("SELECT m.id, lower(r.email) e, r.extra_json FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                   "WHERE m.status IN ('sent','bounced') AND m.sent_at >= date('now')"):
    в = до.get(р["e"]) or "не проверялся"
    ушло[в] += 1
    if р["id"] in отбитые:
        отбой[в] += 1
for в, n in ушло.most_common():
    print("   %-16s ушло %4d, отбоев %d (%.1f%%)" % (в, n, отбой[в], 100.0 * отбой[в] / n))
print("   ВСЕГО ушло %d, отбоев %d (%.1f%%)" % (sum(ушло.values()), sum(отбой.values()),
      100.0 * sum(отбой.values()) / max(1, sum(ушло.values()))))
print("=== ОТБОИ ПО ВЕРДИКТУ ===")
