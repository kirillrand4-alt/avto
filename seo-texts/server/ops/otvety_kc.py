# -*- coding: utf-8 -*-
"""Ответы на письма КЦ по кампаниям и месяцам: отправлено, ответов людей, автоответов, лидов по виду. Только чтение."""
import sqlite3
from collections import Counter, defaultdict
c = sqlite3.connect(r"C:\sender\sender.db")
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
def кц(cid, mb): return "ompressor" in str(mb) or not any(w in str(кам.get(cid, "")).lower() for w in ("meyer", "мейер"))
отпр, отв, авто = Counter(), Counter(), Counter()
rid_kc = {}
for mid, cid, mb, sa, rid in c.execute("SELECT id, campaign_id, mailbox_id, substr(sent_at,1,7), recipient_id FROM messages WHERE status='sent'"):
    if кц(cid, mb):
        отпр[(кам.get(cid, cid), sa)] += 1; rid_kc[rid] = (кам.get(cid, cid), sa)
for rid, et in c.execute("SELECT recipient_id, event_type FROM events WHERE event_type IN ('reply','reply_auto')"):
    if rid in rid_kc:
        (отв if et == "reply" else авто)[rid_kc[rid]] += 1
print("кампания | месяц | отправлено | ответов людей | % | автоответов")
for k in sorted(отпр, key=lambda k: (k[1], str(k[0]))):
    o = отпр[k]; r = отв[k]
    print("%-32s %s %6d %5d %5.1f%% %5d" % (str(k[0])[:32], k[1], o, r, 100 * r / o if o else 0, авто[k]))
O, R = sum(отпр.values()), sum(отв.values())
print("ВСЕГО КЦ: отправлено %d, ответов людей %d (%.1f%%), автоответов %d" % (O, R, 100 * R / O if O else 0, sum(авто.values())))
лид = Counter()
for inn, kind, st in c.execute("SELECT l.inn, l.reply_kind, l.status FROM leads l"):
    pass
ки = Counter(); стат = Counter()
for kind, st, rid in c.execute("SELECT l.reply_kind, l.status, r.id FROM leads l JOIN recipients r ON lower(r.email)=lower(l.email)"):
    if rid in rid_kc: ки[kind] += 1; стат[st] += 1
print("лиды КЦ по виду ответа:", dict(ки.most_common())); print("лиды КЦ по статусу:", dict(стат.most_common()))
