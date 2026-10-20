# -*- coding: utf-8 -*-
"""Какие стоп-флаги держат карточки на подтверждении (confirm_hold): коды и
тексты флагов, по кампаниям, с примерами. Только чтение."""
import json
import sqlite3
from collections import Counter, defaultdict

c = sqlite3.connect(r"C:\sender\sender.db")
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
сч, по_кам, прим = Counter(), defaultdict(Counter), {}
n = 0
for rid, cid, em, pj in c.execute("SELECT id, campaign_id, email, panel_json FROM confirm_reviews "
                                  "WHERE status='pending' AND COALESCE(kind,'outbound')!='reply'"):
    p = json.loads(pj or "{}")
    if not (p.get("actions") or {}).get("confirm_hold"):
        continue
    n += 1
    флаги = p.get("stop_flags") or []
    коды = []
    for ф in флаги:
        к = ф.get("code") if isinstance(ф, dict) else str(ф)
        т = (ф.get("text") or ф.get("label") or "") if isinstance(ф, dict) else ""
        коды.append(к)
        прим.setdefault(к, (rid, em, str(т)[:140]))
    ключ = "+".join(sorted(set(коды))) or "без кода"
    сч[ключ] += 1
    по_кам[кам.get(cid, cid)][ключ] += 1
print("карточек со стоп-флагом:", n)
for k, v in сч.most_common():
    print("  %4d  %s" % (v, k))
print("по кампаниям:")
for k, v in по_кам.items():
    print("  ", k, dict(v.most_common()))
print("примеры:")
for k, v in прим.items():
    print("  ", k, v)
