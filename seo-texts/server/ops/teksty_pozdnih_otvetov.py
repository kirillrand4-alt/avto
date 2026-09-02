# -*- coding: utf-8 -*-
"""Полный текст ответов, пришедших после закрытия лида."""
import json
import re
import sqlite3

СОБЫТИЯ = (295893, 308158, 308153)

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=90)
c.row_factory = sqlite3.Row


def чисто(с):
    с = re.sub(r"[\u034f\u200b\u200c\u200d\ufeff\u00ad]", "", str(с or ""))
    с = re.sub(r"\s+", " ", с)
    return с.strip()


for eid in СОБЫТИЯ:
    r = c.execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()
    if not r:
        print("события %s нет" % eid)
        continue
    print("=" * 78)
    print("СОБЫТИЕ %s | %s | ящик %s | получатель %s"
          % (eid, r["event_ts"], r["mailbox_id"], r["recipient_id"]))
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:                                          # noqa: BLE001
        d = {}
    заг = d.get("headers") or {}
    for к in ("From", "Subject", "Date", "Reply-To"):
        if заг.get(к):
            print("   %-9s %s" % (к, str(заг[к])[:110]))
    тело = ""
    for к in ("text", "body", "plain", "snippet", "text_plain", "content"):
        if d.get(к):
            тело = d[к]
            break
    if not тело:
        for к, v in d.items():
            if isinstance(v, str) and len(v) > 120 and к != "detail_json":
                тело = v
                break
    print("   --- текст ---")
    т = чисто(тело)
    print("   " + (т[:1400] if т else "(текста в событии нет; ключи: %s)"
                   % list(d)[:10]))
    print("")

# заодно карточка лида 138
r = c.execute("SELECT * FROM leads WHERE id=138").fetchone()
if r:
    print("=" * 78)
    print("=== ЛИД 138 ===")
    for к in ("company_name", "inn", "email", "status", "reply_kind",
              "phone", "created_at", "updated_at"):
        print("   %-14s %s" % (к, r[к]))
    print("   need: %s" % чисто(r["need"])[:600])
c.close()
