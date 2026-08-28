# -*- coding: utf-8 -*-
"""Где обрезан ответ главного механика «Импэкс-Дона» — лид или событие."""
import json
import sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
л = c.execute("SELECT * FROM leads WHERE id=253").fetchone()
print("=== ЛИД 253 ===")
for k in л.keys():
    v = л[k]
    if isinstance(v, str) and len(v) > 60:
        print("  %s: [%d знаков]" % (k, len(v)))
        print("    %s" % v.replace("\n", " | "))
    else:
        print("  %s: %s" % (k, v))
print()
print("=== СОБЫТИЕ 305587 ===")
e = c.execute("SELECT event_ts, mailbox_id, detail_json FROM events "
              " WHERE id=305587").fetchone()
d = json.loads(e["detail_json"] or "{}")
т = str(d.get("snippet") or "")
print("  ключи detail: %s" % sorted(d.keys()))
print("  длина snippet: %d" % len(т))
print("  ---")
print(т)
print("  ---")
print("  заголовки: %s" % json.dumps(d.get("headers") or {}, ensure_ascii=False)[:600])
c.close()
