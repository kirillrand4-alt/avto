# -*- coding: utf-8 -*-
"""Отбивки за сегодня (UTC-день): кому, кампания, когда отправлено, вердикт пробы и его
время во всех трёх базах, текст причины. Только чтение."""
import json
import sqlite3
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
cols = [r[1] for r in c.execute("PRAGMA table_info(addr_probe)")]
тс = next((x for x in ("checked_at", "ts", "probed_at", "updated_at") if x in cols), None)
отпр = c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at >= date('now')").fetchone()[0]
сч, по_камп, по_дом = Counter(), Counter(), Counter()
строки = []
for rid, mid, ts, dj in c.execute("SELECT recipient_id, message_id, event_ts, detail_json FROM events WHERE event_type='bounce' AND event_ts >= date('now')"):
    em = (c.execute("SELECT lower(email) FROM recipients WHERE id=?", (rid,)).fetchone() or [""])[0]
    м = c.execute("SELECT campaign_id, sent_at FROM messages WHERE id=?", (mid,)).fetchone() if mid else None
    пр = c.execute("SELECT verdict%s FROM addr_probe WHERE lower(email)=?" % ((", " + тс) if тс else ""), (em,)).fetchone()
    д = json.loads(dj or "{}")
    по_камп[кам.get(м[0]) if м else "?"] += 1
    по_дом[em.split("@")[-1]] += 1
    строки.append("%s | %s | отпр %s | проба: %s | %s" % (ts[11:16], em, (м[1] or "")[11:16] if м else "?", пр, str(д.get("diagnostic") or д.get("reason") or д.get("code") or "")[:70]))
print("отправлено сегодня:", отпр, "| отбивок:", len(строки))
print("по кампаниям:", по_камп.most_common())
print("по доменам:", по_дом.most_common(8))
print("\n".join(строки[:40]))
