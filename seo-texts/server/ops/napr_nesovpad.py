# -*- coding: utf-8 -*-
"""Живые письма, где текст не совпадает с направлением кампании: Meyer-текст в КЦ (16) и наоборот. Только чтение."""
import re, sqlite3
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
сч = Counter()
for mid, cid, st, subj, body, ca in c.execute(
        "SELECT m.id, m.campaign_id, m.status, cr.subject, COALESCE(cr.edited_body, cr.body), cr.created_at FROM messages m "
        "JOIN confirm_reviews cr ON cr.message_id=m.id WHERE m.status IN ('pending_review','approved','scheduled') AND m.campaign_id IN (14,16)"):
    т = (subj or "") + " " + (body or "")
    мей = bool(re.search(r"(?i)Meyer|фотосепаратор|рентген", т)); кц = bool(re.search(r"(?i)компрессор", т))
    if cid == 16 and мей and not кц: k = "Meyer-текст в кампании КЦ"
    elif cid == 14 and кц and not мей: k = "КЦ-текст в кампании Meyer"
    else: continue
    сч[(k, st, str(ca)[:10])] += 1
for k, v in sorted(сч.items()): print(v, k)
