# -*- coding: utf-8 -*-
"""Ответы без ящика в карточке — с какого ящика они реально ушли."""
import json
import sqlite3
from collections import Counter

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
сч = Counter()
for r in c.execute(
        "SELECT id, email, recipient_id, panel_json, message_id, status "
        "  FROM confirm_reviews WHERE kind='reply' AND status='sent' "
        " ORDER BY id DESC LIMIT 40"):
    try:
        п = json.loads(r["panel_json"] or "{}") or {}
    except Exception:                                            # noqa: BLE001
        п = {}
    предпочт = п.get("mailbox_id") or п.get("inbox_mailbox")
    # ящик исходной переписки
    исход = None
    if r["recipient_id"]:
        x = c.execute(
            "SELECT mailbox_id FROM messages WHERE recipient_id=? AND status='sent' "
            "   AND id <> COALESCE(?, -1) ORDER BY sent_at ASC LIMIT 1",
            (r["recipient_id"], r["message_id"])).fetchone()
        исход = x[0] if x else None
    # ящик, с которого ушёл сам ответ
    ответ = None
    if r["message_id"]:
        x = c.execute("SELECT mailbox_id FROM messages WHERE id=?",
                      (r["message_id"],)).fetchone()
        ответ = x[0] if x else None
    метка = ("ящик был указан" if предпочт else "ящика в карточке не было")
    if исход and ответ:
        метка += " / " + ("ушёл С ТОГО ЖЕ" if ответ == исход else "ушёл С ДРУГОГО")
    elif not ответ:
        метка += " / письма ответа не нашлось"
    сч[метка] += 1
    if исход and ответ and ответ != исход:
        print("   РАСХОЖДЕНИЕ rev %-6s %-26s переписка %-30s ответ %s"
              % (r["id"], str(r["email"])[:26], str(исход)[:30], ответ))
print("")
for к, n in сч.most_common():
    print("   %-52s %4d" % (к, n))
c.close()
