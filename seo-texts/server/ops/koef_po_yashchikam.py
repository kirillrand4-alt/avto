# -*- coding: utf-8 -*-
"""Коэффициент ответов по ящикам за 30 дней: первые письма (без in_reply_to), ответы клиентов (reply, без автоответов)
по паре получатель+кампания после письма; плюс отбивки и отказы «спам». Только чтение."""
import re, sqlite3
from collections import defaultdict
from datetime import datetime
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
отв = defaultdict(list)
for rid, camp, ts in c.execute("SELECT recipient_id, campaign_id, event_ts FROM events WHERE event_type='reply' AND event_ts>='2026-10-10'"):
    отв[(rid, camp)].append(str(ts)[:19])
отб = defaultdict(int)
for mid, in c.execute("SELECT message_id FROM events WHERE event_type IN ('bounce','reject_spam') AND event_ts>='2026-10-14' AND message_id IS NOT NULL"):
    отб[mid] += 1
т = defaultdict(lambda: [0, 0, 0, 0])
for mid, rid, camp, mb, s, err in c.execute("SELECT id, recipient_id, campaign_id, mailbox_id, sent_at, COALESCE(last_error,'') FROM messages WHERE sent_at>='2026-10-14' AND status='sent' AND COALESCE(in_reply_to,'')=''"):
    т[mb][0] += 1; т[mb][1] += any(x >= str(s)[:19] for x in отв.get((rid, camp), [])); т[mb][2] += bool(отб.get(mid))
for mb, n in c.execute("SELECT mailbox_id, COUNT(*) FROM messages WHERE (lower(last_error) LIKE '%spam%' OR last_error LIKE '%спам%') AND updated_at>='2026-10-14' GROUP BY 1"):
    т[mb][3] += n
for напр, рег in (("КЦ", r"kompressor|compressor"), ("Meyer", r"sort|rentgen|inspection|optic")):
    print("\n== %s: ящик, писем, ответов, %%, отбивок, спам-отказов" % напр)
    for mb, (п, о, б, сп) in sorted(((m, v) for m, v in т.items() if re.search(рег, m or "")), key=lambda x: x[1][1] / max(1, x[1][0])):
        print("  %-44s %5d %4d %5.2f%% %4d %3d" % (mb, п, о, 100 * о / max(1, п), б, сп))
