# -*- coding: utf-8 -*-
"""Темп отправки сегодня: по часам UTC x направление ящика; по ящикам Meyer —
сколько и когда последнее; очередь наступивших approved по направлению и
первые в очереди (что стоит впереди Meyer). Только чтение."""
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
нап = {mb.mailbox_id: mb.division for mb in cfg.mailboxes()}
c = sqlite3.connect(r"C:\sender\sender.db")
ч = defaultdict(Counter)
посл = {}
for mb, sa in c.execute("SELECT mailbox_id, sent_at FROM messages WHERE status='sent' AND sent_at>='2026-10-22'"):
    ч[str(sa)[11:13]][нап.get(mb, "?")] += 1
    посл[mb] = max(посл.get(mb, ""), str(sa)[11:19])
for h in sorted(ч):
    print("  %s:00 UTC  %s" % (h, dict(ч[h])))
print("\nящики Meyer: последнее письмо сегодня")
for mb, d in нап.items():
    if d == "meyer":
        print("   %-38s %s" % (mb, посл.get(mb, "—")))
сейчас = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
очередь = c.execute("""SELECT m.id, m.campaign_id, m.scheduled_at, r.tz FROM messages m JOIN recipients r ON r.id=m.recipient_id
    WHERE m.status='scheduled' AND m.scheduled_at<=? AND (SELECT cr.status FROM confirm_reviews cr WHERE cr.message_id=m.id
    ORDER BY cr.id DESC LIMIT 1) IN ('approved','edited') ORDER BY m.scheduled_at, m.id""", (сейчас,)).fetchall()
print("\nнаступивших одобренных:", len(очередь), Counter(кам.get(x[1]) for x in очередь))
print("пояса Meyer в очереди:", Counter(x[3] for x in очередь if x[1] in (13, 14, 18)))
print("первые 10 в очереди:", [(x[0], кам.get(x[1])[:12], x[2][:16]) for x in очередь[:10]])
