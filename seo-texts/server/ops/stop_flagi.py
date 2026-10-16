# -*- coding: utf-8 -*-
"""Карточки на подтверждении со стоп-флагом: какие флаги, по кампаниям. Только чтение."""
import json, sqlite3
from collections import Counter, defaultdict
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
сч, прим, покамп, всего = Counter(), defaultdict(list), Counter(), 0
for rid, cid, pj, email in c.execute("SELECT id, campaign_id, panel_json, email FROM confirm_reviews WHERE status='pending'"):
    всего += 1
    try: p = json.loads(pj or "{}")
    except ValueError: p = {}
    if not (p.get("actions") or {}).get("confirm_hold"): continue
    покамп[кам.get(cid, cid)] += 1
    for f in p.get("stop_flags") or []:
        k = (f.get("code") or f.get("kind") or "") if isinstance(f, dict) else ""
        t = (f.get("text") or f.get("title") or f.get("message") or json.dumps(f, ensure_ascii=False)) if isinstance(f, dict) else str(f)
        ключ = k or t[:60]
        сч[ключ] += 1
        if len(прим[ключ]) < 2: прим[ключ].append("#%d %s: %s" % (rid, email, t[:160]))
print("на подтверждении:", всего, "| со стоп-флагом по кампаниям:", dict(покамп))
for k, v in сч.most_common():
    print("%4d  %s" % (v, k))
    for x in прим[k]: print("        " + x)
