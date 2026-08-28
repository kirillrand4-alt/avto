# -*- coding: utf-8 -*-
"""Что за 143 письма ждут подтверждения."""
import io
import json
import sqlite3
from collections import Counter

наши = {}
for ф, п in ((r"C:\sender\_ops\vtorye-adresa.jsonl", 1),
             (r"C:\sender\_ops\vtorye-adresa-2.jsonl", 2)):
    try:
        for с in io.open(ф, encoding="utf-8"):
            d = json.loads(с)
            if "review" in d:
                наши[int(d["review"])] = п
    except FileNotFoundError:
        pass
вердикт = {}
for ф in (r"C:\sender\_ops\sud-vtoryh.jsonl", r"C:\sender\_ops\sud-vtoryh-2.jsonl"):
    try:
        for с in io.open(ф, encoding="utf-8"):
            d = json.loads(с)
            вердикт[int(d["id"])] = str(d.get("verdikt") or "").replace(
                "o", "о").replace("p", "р")
    except FileNotFoundError:
        pass

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
строки = c.execute(
    "SELECT id, inn, email, campaign_id, kind, created_at, panel_json, "
    "       recipient_id, message_id "
    "  FROM confirm_reviews WHERE status='pending' ORDER BY id").fetchall()
print("всего pending: %d" % len(строки))
откуда = Counter()
флаги = Counter()
верд = Counter()
дни = Counter()
камп = Counter()
без_письма = 0
for r in строки:
    i = int(r["id"])
    откуда["партия %d" % наши[i] if i in наши else "не из партий"] += 1
    верд[вердикт.get(i, "не судили")] += 1
    дни[str(r["created_at"])[:10]] += 1
    камп[str(r["campaign_id"])] += 1
    if not r["message_id"]:
        без_письма += 1
    try:
        п = json.loads(r["panel_json"] or "{}") or {}
    except Exception:                                            # noqa: BLE001
        п = {}
    коды = sorted({(f.get("code") if isinstance(f, dict) else str(f))
                   for f in (п.get("stop_flags") or [])})
    держ = bool((п.get("actions") or {}).get("confirm_hold"))
    флаги["%s%s" % ("+".join(коды) or "без флагов",
                    " [держит]" if держ else "")] += 1
print("")
print("=== откуда ===")
for к, n in откуда.most_common():
    print("   %-22s %4d" % (к, n))
print("")
print("=== вердикт судьи ===")
for к, n in верд.most_common():
    print("   %-22s %4d" % (к, n))
print("")
print("=== стоп-флаги ===")
for к, n in флаги.most_common(8):
    print("   %-52s %4d" % (к, n))
print("")
print("=== когда заведены ===")
for к, n in sorted(дни.items())[-6:]:
    print("   %s  %4d" % (к, n))
print("")
print("кампании: %s | карточек без письма: %d" % (dict(камп), без_письма))
c.close()
