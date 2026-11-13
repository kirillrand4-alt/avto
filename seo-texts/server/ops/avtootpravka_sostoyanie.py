# -*- coding: utf-8 -*-
"""Жив ли цикл автоотправки: отправки по часам (UTC) за сутки, письма в 'sending' (с какого времени, какие ящики),
последние строки лога про auto_send. Только чтение."""
import io, os, re, sqlite3
from collections import Counter
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
print("отправки по часам:", c.execute("SELECT substr(sent_at,1,13), COUNT(*) FROM messages WHERE status='sent' AND sent_at>=datetime('now','-20 hours') GROUP BY 1").fetchall())
print("sending:", c.execute("SELECT mailbox_id, campaign_id, claimed_at, attempt_count FROM messages WHERE status='sending' ORDER BY claimed_at LIMIT 25").fetchall())
print("send_log по часам:", c.execute("SELECT substr(ts,1,13), outcome, COUNT(*) FROM send_log WHERE ts>=datetime('now','-6 hours') GROUP BY 1,2").fetchall())
for п in (r"C:\sender\_ops\panel_out.log", r"C:\sender\_ops\panel_err.log"):
    р = os.path.getsize(п)
    with io.open(п, "rb") as f: f.seek(max(0, р - 2000000)); х = f.read().decode("utf-8", "replace").splitlines()
    кл = [x for x in х if re.search(r"auto_send|AutoSend|claim|window|окно|pick_mailbox|лимит", x)]
    print("\n==", п, "строк про автоотправку:", len(кл)); print("\n".join(x[:220] for x in кл[-15:]))
