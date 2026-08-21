# -*- coding: utf-8 -*-
"""Сырое тело одного события отбивки - когда оно ни к чему не привязано.

Отбивка без message_id значит, что письмо по ней не нашлось: либо DSN
пришёл на письмо, которого у нас нет, либо разборщик принял за отбивку
что-то другое. Разбираться можно только по сырым заголовкам.
"""
import json
import sqlite3
import sys

eid = int(sys.argv[1]) if len(sys.argv) > 1 else 0
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
р = c.execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()
if р is None:
    print("события нет")
    raise SystemExit(0)
print({k: р[k] for k in р.keys() if k != "detail_json"})
try:
    д = json.loads(р["detail_json"] or "{}")
except Exception:                                              # noqa: BLE001
    print("detail_json не разобрался:", str(р["detail_json"])[:500])
    raise SystemExit(0)
print("\nключи detail:", list(д))
for ключ in ("snippet", "privyazka", "kind", "in_reply_to_hdr",
             "inbox_mailbox"):
    if ключ in д:
        значение = д[ключ]
        печать = json.dumps(значение, ensure_ascii=False)[:1200] \
            if isinstance(значение, (dict, list)) else str(значение)[:1200]
        print(f"\n--- {ключ} ---\n{печать}")
