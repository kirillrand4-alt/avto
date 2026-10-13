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
# какое письмо было: кампания последнего письма и до/после заливки книг (12.10)
камп = Counter()
до_книг = Counter()
for инн in повт:
    р = c.execute("SELECT m.campaign_id, m.sent_at FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                  "WHERE m.status='sent' AND r.inn=? ORDER BY m.sent_at DESC LIMIT 1", (инн,)).fetchone()
    if not р:
        continue
    имя = {10: "935 КЦ", 11: "935 Meyer", 14: "Россия 9000 Meyer", 9: "Богатые КЦ", 13: "2-е касание Meyer",
           12: "Вебинар Meyer", 5: "Металлообработка КЦ", 6: "Солянка КЦ", 1: "новостные"}.get(р[0], str(р[0]))
    камп[имя] += 1
    до_книг["до 12.10 (паспорта книг ещё не было)" if str(р[1]) < "2026-10-12" else "с 12.10 (уже по книжному паспорту)"] += 1
print("кампания последнего письма: %s" % dict(камп.most_common()))
print("когда: %s" % dict(до_книг))
print("последнее письмо компании по месяцам: %s" % dict(sorted(мес.items())))
print("сколько прошло: %s" % dict(дни))
print("писем компании отправлено (4 = 4+): %s" % dict(sorted(писем.items())))
print("из них отвечали нам (есть лид): %d" % ответили)
print("=== ПОВТОРНЫЕ: КОГДА ПИСАЛИ ===")
