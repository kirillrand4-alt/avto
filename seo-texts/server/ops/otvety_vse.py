# -*- coding: utf-8 -*-
"""Живые ответы по кампаниям (владелец 20.10): отправлено, ответили люди (без
автоответов), %, и по виду ответа (из лидов). Направление: ящик/имя кампании.
Стиль КЦ: «старый» — август (Партия 935, Металлообработка, КЦ-1 август — тот же
канон), «новый» — октябрьский канон (Россия 9000 — КЦ, КЦ тест). Только чтение."""
import sqlite3
from collections import Counter, defaultdict

c = sqlite3.connect(r"C:\sender\sender.db")
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}


def напр(cid, mb):
    и = str(кам.get(cid, "")).lower()
    if "meyer" in и or "мейер" in и:
        return "Meyer"
    return "КЦ" if "ompressor" in str(mb) or "кц" in и or "935" in и or "металл" in и else "Meyer" if mb else "?"


отпр = defaultdict(set)
период = defaultdict(list)
rid_к = defaultdict(set)
for cid, mb, rid, sa in c.execute("SELECT campaign_id, mailbox_id, recipient_id, sent_at FROM messages WHERE status='sent'"):
    к = (напр(cid, mb), кам.get(cid, cid))
    отпр[к].add(rid)
    rid_к[rid].add(к)
    период[к].append(str(sa)[:10])
отв, авто = defaultdict(set), defaultdict(set)
for rid, et in c.execute("SELECT recipient_id, event_type FROM events WHERE event_type IN ('reply','reply_auto')"):
    for к in rid_к.get(rid, ()):
        (отв if et == "reply" else авто)[к].add(rid)
вид = defaultdict(Counter)
email_rid = defaultdict(set)
for rid, em in c.execute("SELECT id, lower(email) FROM recipients"):
    email_rid[em].add(rid)
for em, kind in c.execute("SELECT lower(email), reply_kind FROM leads"):
    for rid in email_rid.get(em, ()):
        for к in rid_к.get(rid, ()):
            if rid in отв[к]:
                вид[к][kind or "?"] += 1
print("%-6s %-32s %-23s %6s %6s %6s %5s" % ("напр", "кампания", "период", "получ.", "люди", "%", "авто"))
итог = defaultdict(lambda: [0, 0])
for к in sorted(отпр, key=lambda k: (k[0], min(период[k]))):
    n, r = len(отпр[к]), len(отв[к])
    if n < 20:
        continue
    print("%-6s %-32s %s..%s %6d %6d %5.1f%% %5d  %s" % (к[0], str(к[1])[:32], min(период[к]), max(период[к]), n, r,
                                                      100 * r / n, len(авто[к]), dict(вид[к].most_common(4))))
    итог[к[0]][0] += n
    итог[к[0]][1] += r
for н, (n, r) in итог.items():
    print("ВСЕГО %-6s получателей %6d, ответили люди %4d (%.2f%%)" % (н, n, r, 100 * r / n if n else 0))
