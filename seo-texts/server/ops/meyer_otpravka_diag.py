# -*- coding: utf-8 -*-
"""Почему не уходит Meyer (владелец 22.10: «нажал отправить, ничего не
начало отправляться»). По кампаниям Meyer: письма по статусам, ближайшее и
самое раннее scheduled_at, ящики пула (пауза, лимит, ушло сегодня), последние
ошибки, последние отправки. Только чтение."""
import json
import sqlite3
from collections import Counter
from datetime import datetime

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
сейчас = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
print("сейчас UTC", сейчас)
кам = [r for r in c.execute("SELECT * FROM campaigns") if "meyer" in str(r["name"]).lower() or "мейер" in str(r["name"]).lower()]
for к in кам:
    ст = Counter(r[0] for r in c.execute("SELECT status FROM messages WHERE campaign_id=?", (к["id"],)))
    акт = {k: v for k, v in ст.items() if k not in ("sent", "skipped", "failed", "cancelled")}
    if not акт:
        continue
    print("\n#%s %s | кампания: %s | пул: %s" % (к["id"], к["name"], к["status"], к["provider_pool"]))
    print("   статусы:", dict(ст))
    for st in акт:
        r = c.execute("SELECT MIN(scheduled_at), MAX(scheduled_at), SUM(scheduled_at<=?), COUNT(DISTINCT mailbox_id), "
                      "SUM(mailbox_id IS NULL) FROM messages WHERE campaign_id=? AND status=?", (сейчас, к["id"], st)).fetchone()
        print("   %-14s раннее %s | позднее %s | наступило %s | ящиков %s | без ящика %s" % ((st,) + tuple(r)))
    for r in c.execute("SELECT status, last_error, COUNT(*) FROM messages WHERE campaign_id=? AND last_error IS NOT NULL "
                       "AND status NOT IN ('sent') GROUP BY 1,2 ORDER BY 3 DESC LIMIT 5", (к["id"],)):
        print("   ошибка:", tuple(r))
    r = c.execute("SELECT MAX(sent_at), SUM(sent_at>=?) FROM messages WHERE campaign_id=? AND status='sent'",
                  (сейчас[:10], к["id"])).fetchone()
    print("   последняя отправка:", r[0], "| сегодня:", r[1])
кол = [x[1] for x in c.execute("PRAGMA table_info(mailboxes)")]
print("\nколонки mailboxes:", кол)
for r in c.execute("SELECT * FROM mailboxes"):
    d = dict(r)
    s = json.dumps({k: d[k] for k in d if k in ("id", "email", "status", "paused", "pool", "provider_pool", "division", "daily_limit",
                                                 "sent_today", "warmup_stage", "enabled", "brand")}, ensure_ascii=False)
    if "meyer" in s.lower() or "мейер" in s.lower() or "meyer" in str(d.get("email", "")).lower():
        print("  ", s)
