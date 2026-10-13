# -*- coding: utf-8 -*-
"""Повторные по новому паспорту (журнал partiya-9000, последняя заливка):
когда им писали в последний раз и сколько уже прошло 90 дней."""
import io
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
посл_ts = 0
записи = []
for с in io.open(r"C:\sender\_ops\partiya-9000.jsonl", encoding="utf-8"):
    з = json.loads(с)
    посл_ts = max(посл_ts, int(з.get("ts") or 0))
    записи.append(з)
повт = {з["inn"]: з for з in записи if з.get("ts") == посл_ts and з.get("povtor")}
print("повторных в последней заливке: %d" % len(повт))
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
сейчас = datetime.now(timezone.utc)
мес, дни, писем, ответили = Counter(), Counter(), Counter(), 0
for инн in повт:
    р = c.execute("SELECT max(m.sent_at), count(*) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                  "WHERE m.status='sent' AND r.inn=?", (инн,)).fetchone()
    if not р or not р[0]:
        мес["(не нашли отправки)"] += 1
        continue
    t = datetime.fromisoformat(str(р[0]).replace("Z", "+00:00"))
    t = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    д = (сейчас - t).days
    мес[str(р[0])[:7]] += 1
    дни["90+ дней (можно писать)" if д >= 90 else "60-89" if д >= 60 else "30-59" if д >= 30 else "<30"] += 1
    писем[min(р[1], 4)] += 1
    if c.execute("SELECT 1 FROM leads WHERE inn=? LIMIT 1", (инн,)).fetchone():
        ответили += 1
print("последнее письмо компании по месяцам: %s" % dict(sorted(мес.items())))
print("сколько прошло: %s" % dict(дни))
print("писем компании отправлено (4 = 4+): %s" % dict(sorted(писем.items())))
print("из них отвечали нам (есть лид): %d" % ответили)
print("=== ПОВТОРНЫЕ: КОГДА ПИСАЛИ ===")
