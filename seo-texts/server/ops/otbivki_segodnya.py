# -*- coding: utf-8 -*-
"""Из чего сегодняшние отбивки: мёртвый ящик, политика или домен."""
import json
import sqlite3
import time
from collections import Counter
БАЗА = r"C:\sender\sender.db"
ДЕНЬ = time.strftime("%Y-%m-%d")
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
по_вердикту, по_ящику, по_домену = Counter(), Counter(), Counter()
примеры = {}
всего = 0
for r in c.execute("SELECT e.id, e.mailbox_id, e.detail_json, r.email "
                   "  FROM events e LEFT JOIN recipients r ON r.id=e.recipient_id "
                   " WHERE e.event_type='bounce' AND e.event_ts LIKE ?",
                   (ДЕНЬ + "%",)):
    всего += 1
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:
        d = {}
    dsn = d.get("dsn") if isinstance(d.get("dsn"), dict) else {}
    в = str(dsn.get("verdict") or d.get("verdict") or "—")
    по_вердикту[в] += 1
    по_ящику[str(r["mailbox_id"] or "—")] += 1
    почта = str(r["email"] or "")
    по_домену[почта.split("@")[-1].lower() if "@" in почта else "—"] += 1
    диаг = str(dsn.get("diagnostic") or d.get("snippet") or "").replace("\n", " ")
    примеры.setdefault(в, диаг[:150])
print("отбивок за %s: %d" % (ДЕНЬ, всего))
print("\nпо вердикту:")
for к, v in по_вердикту.most_common():
    print("  %-14s %4d   %s" % (к, v, примеры.get(к, "")[:110]))
print("\nпо нашему ящику (топ-10):")
for к, v in по_ящику.most_common(10):
    print("  %-42s %d" % (к, v))
print("\nпо домену получателя (топ-10):")
for к, v in по_домену.most_common(10):
    print("  %-28s %d" % (к, v))
отпр = c.execute("SELECT COUNT(*) FROM events WHERE event_type='sent' "
                 "  AND event_ts LIKE ?", (ДЕНЬ + "%",)).fetchone()[0]
print("\nотправлено сегодня: %d, BR = %.2f%%"
      % (отпр, 100.0 * всего / отпр if отпр else 0))
c.close()
