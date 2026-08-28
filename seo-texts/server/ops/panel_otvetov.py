# -*- coding: utf-8 -*-
"""Какие ключи в панели у карточек ответа без ящика — чей это путь."""
import json
import sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
for r in c.execute("SELECT id, email, status, kind, reason, dedup_key, panel_json, "
                   "       created_at FROM confirm_reviews WHERE kind='reply' "
                   " ORDER BY id DESC LIMIT 11"):
    try:
        п = json.loads(r["panel_json"] or "{}") or {}
    except Exception:
        п = {}
    я = п.get("mailbox_id") or п.get("inbox_mailbox")
    print("rev %-6s %-9s %-24s ящик: %s" % (r["id"], r["status"],
                                            str(r["email"])[:24],
                                            (я or "НЕТ")[:34]))
    print("    ключи панели: %s" % ", ".join(sorted(п.keys()))[:110])
    print("    dedup: %-30s создана %s" % (str(r["dedup_key"])[:30],
                                           str(r["created_at"])[:16]))
c.close()
