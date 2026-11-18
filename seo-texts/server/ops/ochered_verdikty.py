# -*- coding: utf-8 -*-
"""Вердикты пробы (addr_probe) у карточек в «Подтвердить отправку» (pending) по кампаниям; --napr=meyer|kc — фильтр по
направлению письма (panel_json.letter_division). Только чтение.   ochered_verdikty.py [--napr=meyer]"""
import json, sqlite3, sys
from collections import Counter, defaultdict
Н = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--napr=")), "")
к = sqlite3.connect(r"file:C:\sender\sender.db?mode=ro", uri=True)
вп = {str(e or "").lower(): str(v or "") for e, v in к.execute("SELECT email, verdict FROM addr_probe")}
кам = dict(к.execute("SELECT id, name FROM campaigns").fetchall())
св = defaultdict(Counter)
for кид, em, pj in к.execute("SELECT campaign_id, email, panel_json FROM confirm_reviews WHERE status='pending' AND COALESCE(kind,'outbound')<>'reply'"):
    try: нп = (json.loads(pj or "{}") or {}).get("letter_division", "")
    except Exception: нп = ""
    if Н and нп != Н: continue
    св[кам.get(кид, кид)][вп.get(str(em or "").lower()) or "нет пробы"] += 1
итог = Counter()
for н, c in sorted(св.items(), key=lambda x: -sum(x[1].values())):
    print("%-34s %5d  %s" % (н, sum(c.values()), dict(c.most_common()))); итог.update(c)
print("ИТОГО %d %s" % (sum(итог.values()), dict(итог.most_common())))
