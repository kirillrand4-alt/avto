# -*- coding: utf-8 -*-
"""Отклик по ящикам за N дней: отправлено (messages sent), живых ответов (events reply), автоответов,
отбивок, % ответов. Направление ящика — по кампаниям его писем. Только чтение.
    otklik_yashchikov.py [дней=30] [meyer|kc]"""
import sqlite3, sys
from collections import Counter, defaultdict
N = int(next((a for a in sys.argv[1:] if a.isdigit()), "30"))
НАПР = next((a for a in sys.argv[1:] if a in ("meyer", "kc")), None)
КАМП = next((a.split("=",1)[1] for a in sys.argv[1:] if a.startswith("kamp=")), None)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
кам = {i: n for i, n in c.execute("SELECT id, name FROM campaigns")}
отпр, напр = Counter(), defaultdict(Counter)
for mb, cid, n in c.execute("SELECT mailbox_id, campaign_id, count(*) FROM messages WHERE status='sent' AND sent_at >= datetime('now', ?) GROUP BY 1,2", ("-%d days" % N,)):
    if not mb: continue
    if КАМП and КАМП not in str(кам.get(cid, "")): continue
    отпр[mb] += n
    имя = str(кам.get(cid, ""))
    напр[mb]["meyer" if ("Meyer" in имя or "ФСА" in имя or "Мейер" in имя) else "kc"] += n
ев = defaultdict(Counter)
for mb, t, cid, n in c.execute("SELECT mailbox_id, event_type, campaign_id, count(*) FROM events WHERE event_type IN ('reply','reply_auto','bounce','dsn') AND event_ts >= datetime('now', ?) GROUP BY 1,2,3", ("-%d days" % N,)):
    if КАМП and КАМП not in str(кам.get(cid, "")): continue
    if mb: ев[mb][t] += n
строки = []
for mb in set(отпр) | set(ев):
    н = (напр[mb].most_common(1) or [("?", 0)])[0][0]
    if НАПР and н != НАПР: continue
    s = отпр[mb]; r = ев[mb]["reply"]; a = ев[mb]["reply_auto"]; b = ев[mb]["bounce"] + ев[mb]["dsn"]
    строки.append((r / s * 100 if s else 0, mb, н, s, r, a, b))
print("за %d дней; ящик | напр | отправлено | живых ответов | автоответов | отбивок | %% ответов" % N)
for p, mb, н, s, r, a, b in sorted(строки):
    print("  %-44s %-5s %6d %5d %5d %5d   %.2f%%" % (mb, н, s, r, a, b, p))
