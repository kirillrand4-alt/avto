# -*- coding: utf-8 -*-
"""Сколько каждый ящик отправил сегодня (МСК) против лимита панели; ящики с auth failed за 3 часа. Только чтение."""
import json, sqlite3
from collections import Counter
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
лим = (json.loads(c.execute("SELECT value FROM panel_settings WHERE key='send_limits'").fetchone()[0]) or {}).get("per_mailbox") or {}
сег = Counter(mb for (mb,) in c.execute("SELECT mailbox_id FROM messages WHERE status='sent' AND sent_at>=datetime('now','start of day','-3 hours') AND COALESCE(in_reply_to,'')=''"))
пауз = {r[0] for r in c.execute("SELECT mailbox_id FROM mailbox_state WHERE paused=1")}
расп = Counter(mb for (mb,) in c.execute("SELECT mailbox_id FROM messages WHERE status='scheduled'"))
for mb in sorted(set(лим) | set(сег)):
    print("%-44s сегодня %3d / лимит %s %s | в расписании %d" % (mb, сег[mb], лим.get(mb), "ПАУЗА" if mb in пауз else "", расп[mb]))
print("auth failed:", c.execute("SELECT mailbox_id, COUNT(*) FROM messages WHERE last_error LIKE '%auth%' AND updated_at>=datetime('now','-180 minutes') GROUP BY 1").fetchall())
