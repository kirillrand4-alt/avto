# -*- coding: utf-8 -*-
"""Как идёт отправка кампании 22: статусы сообщений, ошибки, отказы «спам» по ящикам и по времени. Только чтение."""
import sqlite3
from collections import Counter
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=60)
кол = [r[1] for r in c.execute("PRAGMA table_info(messages)")]
print("колонки messages:", кол)
print("статусы:", c.execute("SELECT status, COUNT(*) FROM messages WHERE campaign_id=22 GROUP BY status").fetchall())
print("ошибки:", c.execute("SELECT status, substr(COALESCE(last_error,''),1,90), COUNT(*) FROM messages WHERE campaign_id=22 AND status NOT IN ('sent','scheduled','pending_review') "
      "GROUP BY 1,2 ORDER BY 3 DESC LIMIT 15").fetchall())
ящ = next((к for к in ("mailbox_id", "mailbox", "sender_mailbox", "from_addr") if к in кол), None)
вр = next((к for к in ("sent_at", "updated_at", "attempted_at") if к in кол), None)
if ящ:
    print("по ящикам (sent / спам-отказ / прочие ошибки):")
    д = Counter(); с = Counter(); о = Counter()
    for m, st, e in c.execute("SELECT %s, status, COALESCE(last_error,'') FROM messages WHERE campaign_id=22" % ящ):
        if st == "sent": д[m] += 1
        elif "спам" in e.lower() or "spam" in e.lower(): с[m] += 1
        elif st not in ("scheduled", "pending_review", "skipped"): о[m] += 1
    for m in sorted(set(д) | set(с) | set(о), key=lambda x: -с[x]): print("  ", m, д[m], с[m], о[m])
# все кампании сегодня: спам-отказы
print("спам-отказы с 12.11 по всем кампаниям:", c.execute("SELECT campaign_id, COUNT(*) FROM messages WHERE (last_error LIKE '%спам%' OR lower(last_error) LIKE '%spam%') "
      "AND updated_at >= '2026-11-12' GROUP BY 1").fetchall())
print("пример ошибки спам:", c.execute("SELECT last_error FROM messages WHERE campaign_id=22 AND (last_error LIKE '%спам%' OR last_error LIKE '%spam%' OR last_error LIKE '%SPAM%') LIMIT 2").fetchall())
