# -*- coding: utf-8 -*-
"""Карточки с флагом повтора (recent_contact): какое письмо этой компании ушло
раньше — дата, кампания, тот же адрес или другой. Только чтение."""
import json
import re
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
сч = Counter()
прим = []
for rid, inn, em, pj in c.execute("SELECT id, inn, lower(email), panel_json FROM confirm_reviews WHERE status='pending'"):
    p = json.loads(pj or "{}")
    if not any(isinstance(f, dict) and f.get("code") == "recent_contact" for f in p.get("stop_flags") or []):
        continue
    ц = re.sub(r"\D", "", str(inn or ""))
    r = c.execute("SELECT email, ts, campaign_id FROM send_log WHERE outcome='sent' AND (inn=? OR email=?) ORDER BY ts DESC LIMIT 1",
                  (ц, em)).fetchone()
    if not r:
        сч["прошлого письма не нашёл"] += 1
        continue
    тот_же = str(r[0]).lower() == em
    сч[("тот же адрес" if тот_же else "другой адрес компании", str(r[1])[:10], кам.get(r[2], r[2]))] += 1
    if len(прим) < 8:
        прим.append((em, r[0], str(r[1])[:16], кам.get(r[2], r[2])))
for k, v in сч.most_common():
    print("  %4d  %s" % (v, k))
for x in прим:
    print("   сейчас %s | раньше %s %s %s" % x)
