# -*- coding: utf-8 -*-
"""КЦ, 05–12.11: письма и ответы ≤6ч по кампании и дню — отделить «упал текст/аудитория» от «упала доставляемость». Только чтение."""
import re, sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
отв = defaultdict(list)
for rid, camp, ts in c.execute("SELECT recipient_id, campaign_id, event_ts FROM events WHERE event_type='reply' AND event_ts>='2026-11-05'"):
    отв[(rid, camp)].append(datetime.fromisoformat(str(ts)[:19]))
т = defaultdict(lambda: [0, 0])
for rid, camp, mb, s in c.execute("SELECT recipient_id, campaign_id, mailbox_id, sent_at FROM messages WHERE status='sent' AND sent_at>='2026-11-05' AND COALESCE(in_reply_to,'')=''"):
    if re.search(r"sort|rentgen|inspection|optic", mb or ""): continue
    d = datetime.fromisoformat(str(s)[:19])
    т[(camp, str(s)[:10])][0] += 1
    т[(camp, str(s)[:10])][1] += any(d <= x <= d + timedelta(hours=6) for x in отв.get((rid, camp), []))
for (camp, д), (п, о) in sorted(т.items()):
    print("  #%s %s писем %4d  ответ ≤6ч %3d (%.2f%%)" % (camp, д, п, о, 100 * о / п))
