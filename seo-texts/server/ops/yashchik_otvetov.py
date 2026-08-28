# -*- coding: utf-8 -*-
"""С какого ящика уйдут ответы из очереди подтверждения."""
import json
import sqlite3
from collections import Counter

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
строки = c.execute(
    "SELECT id, email, inn, recipient_id, panel_json, thread_id, status, created_at "
    "  FROM confirm_reviews WHERE kind='reply' ORDER BY id DESC LIMIT 60").fetchall()
print("карточек-ответов (последние 60): %d" % len(строки))
сч = Counter()
примеры = []
for r in строки:
    try:
        п = json.loads(r["panel_json"] or "{}") or {}
    except Exception:                                            # noqa: BLE001
        п = {}
    предпочт = п.get("mailbox_id") or п.get("inbox_mailbox")
    настоящий = None
    if r["recipient_id"]:
        x = c.execute(
            "SELECT mailbox_id FROM messages WHERE recipient_id=? AND status='sent' "
            " ORDER BY sent_at DESC LIMIT 1", (r["recipient_id"],)).fetchone()
        настоящий = x[0] if x else None
    if not предпочт:
        сч["ящик в карточке НЕ УКАЗАН"] += 1
    elif настоящий and предпочт != настоящий:
        сч["указан ДРУГОЙ ящик"] += 1
    elif настоящий:
        сч["ящик совпадает с перепиской"] += 1
    else:
        сч["указан, но переписки не нашлось"] += 1
    if len(примеры) < 8:
        примеры.append((r["id"], r["status"], str(r["email"])[:24],
                        str(предпочт or "—")[:30], str(настоящий or "—")[:30]))
print("")
for к, n in сч.most_common():
    print("   %-38s %4d" % (к, n))
print("")
print("   %-6s %-8s %-24s %-30s %s" % ("rev", "статус", "кому", "в карточке", "переписка"))
for i, s_, e, п, н in примеры:
    print("   %-6s %-8s %-24s %-30s %s" % (i, s_, e, п, н))
c.close()
