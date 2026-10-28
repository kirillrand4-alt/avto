# -*- coding: utf-8 -*-
"""Карточки на удержании site_mismatch: кампания, адрес, сайт компании, текст флага. Только чтение."""
import json
import sqlite3
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
ПУБЛ = ("mail.ru", "yandex.ru", "gmail.com", "bk.ru", "list.ru", "inbox.ru", "rambler.ru", "ya.ru", "yandex.by", "mail.com")
сч, прим = Counter(), []
for kid, cid, em, pj in c.execute("SELECT id, campaign_id, lower(email), panel_json FROM confirm_reviews WHERE status='pending' AND panel_json LIKE '%site_mismatch%'"):
    п = json.loads(pj or "{}")
    фл = [f for f in (п.get("stop_flags") or []) if f.get("code") == "site_mismatch"]
    дом = em.split("@")[-1]
    вид = "публичная почта" if дом in ПУБЛ else "корпоративный домен"
    сч[(кам.get(cid), вид)] += 1
    if len(прим) < 25:
        прим.append("%s | %s | %s | %s" % (kid, кам.get(cid), em, (фл[0].get("text") or фл[0].get("why") or json.dumps(фл[0], ensure_ascii=False))[:160] if фл else ""))
for k, n in сч.most_common():
    print(n, k)
print()
print("\n".join(прим))
