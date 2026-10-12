# -*- coding: utf-8 -*-
"""Из-за чего бракуются письма партии 500 (кампания #14).

Причины лежат в ai_letter_log.rounds_json: по каждой попытке — список
замечаний гейта/рецензента. Группируем по смыслу и показываем примеры.
"""
import json
import re
import sqlite3
import sys
from collections import Counter

КАМП = int(sys.argv[1]) if len(sys.argv) > 1 else 14
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
статусы = Counter()
причины = Counter()
примеры = {}
перестав = Counter()
for р in c.execute("SELECT email, status, rounds_json FROM ai_letter_log "
                   "WHERE campaign_id=?", (КАМП,)):
    статусы[р["status"]] += 1
    if р["status"] == "ok":
        continue
    try:
        раунды = json.loads(р["rounds_json"] or "[]") or []
    except Exception:  # noqa: BLE001
        раунды = []
    for рд in раунды:
        if рд.get("perestavleno"):
            перестав[рд["perestavleno"]] += 1
        for пр in (рд.get("rejected") or []):
            т = str(пр)
            # ключ — начало замечания до двоеточия/скобки, без конкретики
            ключ = re.split(r"[:(«\[]", т, 1)[0].strip()[:70] or т[:70]
            причины[ключ] += 1
            примеры.setdefault(ключ, (р["email"], т[:220]))

print("статусы писем кампании %d:" % КАМП)
for к, n in статусы.most_common():
    print("   %-22s %4d" % (к, n))
print("")
print("--- причины брака (по частоте) ---")
for к, n in причины.most_common(14):
    print("   %4d  %s" % (n, к))
print("")
print("--- примеры ---")
for к, _ in причины.most_common(6):
    почта, т = примеры[к]
    print("   [%s] %s" % (почта, т))
if перестав:
    print("")
    print("переставлено в другое направление: %s" % dict(перестав))
print("=== ПРИЧИНЫ БРАКА ===")
