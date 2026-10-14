# -*- coding: utf-8 -*-
"""Стоп-флаги карточек в очереди подтверждения (почему автоотправка пропускает)."""
import json
import sqlite3
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
табл = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%confirm%'")]
print("таблицы:", табл)
т = "confirm_reviews" if "confirm_reviews" in табл else табл[0]
кол = [r[1] for r in c.execute("PRAGMA table_info(%s)" % т)]
print("колонки:", кол)
св, прим = Counter(), {}
по_камп = Counter()
for р in c.execute("SELECT * FROM %s WHERE status='pending'" % т):
    д = dict(р)
    try:
        п = json.loads(д.get("panel_json") or д.get("panel") or "{}")
    except Exception:  # noqa: BLE001
        п = {}
    фл = п.get("stop_flags") or []
    hold = (п.get("actions") or {}).get("confirm_hold")
    по_камп[(д.get("campaign_id"), bool(hold))] += 1
    for f in фл:
        к = f.get("code") or f.get("label")
        св[к] += 1
        прим.setdefault(к, f.get("label"))
print("по кампаниям (кампания, hold): %s" % dict(по_камп))
for к, n in св.most_common():
    print("%5d  %s — %s" % (n, к, str(прим[к])[:90]))
print("=== СТОП-ФЛАГИ ===")
