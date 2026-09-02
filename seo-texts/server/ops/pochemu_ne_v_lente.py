# -*- coding: utf-8 -*-
"""Почему ответ ИМСБ не попал в ленту лидов: есть ли лид и чем он создаётся."""
import io
import json
import os
import re
import sqlite3

БАЗА = r"C:\sender\sender.db"
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=90)
c.row_factory = sqlite3.Row

print("=== СХЕМА leads ===")
for r in c.execute("PRAGMA table_info(leads)"):
    print("   %-3s %-22s %s" % (r[0], r[1], r[2]))

print("")
print("=== ЛИДЫ ПО ЭТОЙ КОМПАНИИ ===")
ряды = c.execute(
    "SELECT * FROM leads WHERE inn='3810320156' OR recipient_id=5552"
).fetchall()
if ряды:
    for r in ряды:
        print("   " + json.dumps({к: str(r[к])[:120] for к in r.keys()
                                  if r[к] not in (None, "")},
                                 ensure_ascii=False)[:600])
else:
    print("   ЛИДА НЕТ")

print("")
print("=== СОБЫТИЯ ПО ПОЛУЧАТЕЛЮ 5552 ===")
for r in c.execute(
        "SELECT id, event_type, mailbox_id, event_ts, rfc_msgid "
        "  FROM events WHERE recipient_id=5552 ORDER BY id"):
    print("   %-8s %-12s %-32s %s" % (r["id"], r["event_type"],
                                      r["mailbox_id"], r["event_ts"]))

print("")
print("=== СКОЛЬКО ВООБЩЕ ОТВЕТОВ И СКОЛЬКО ЛИДОВ ===")
о = c.execute("SELECT COUNT(*) FROM events WHERE event_type='reply'").fetchone()[0]
л = c.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
без_лида = c.execute(
    "SELECT COUNT(DISTINCT e.recipient_id) FROM events e "
    "  LEFT JOIN leads l ON l.recipient_id = e.recipient_id "
    " WHERE e.event_type='reply' AND l.id IS NULL").fetchone()[0]
print("   событий «ответ»: %d; лидов: %d; получателей с ответом БЕЗ лида: %d"
      % (о, л, без_лида))
c.close()

print("")
print("=== КТО СОЗДАЁТ ЛИДЫ (поиск в коде) ===")
найдено = 0
for корень in (r"C:\sender\sender", r"C:\sender\server"):
    for путь, кат, файлы in os.walk(корень):
        кат[:] = [d for d in кат if d not in ("__pycache__", ".git", ".venv",
                                              "tests")]
        for имя in файлы:
            if not имя.endswith(".py"):
                continue
            п = os.path.join(путь, имя)
            try:
                т = io.open(п, encoding="utf-8", errors="replace").read()
            except Exception:                                  # noqa: BLE001
                continue
            for м in re.finditer(r"INSERT\s+(?:OR\s+\w+\s+)?INTO\s+leads",
                                 т, re.I):
                н = т[:м.start()].count("\n") + 1
                print("   %s:%d" % (п.replace("C:\\", ""), н))
                найдено += 1
if not найдено:
    print("   прямых вставок в leads не нашлось — ищем функции")
    for корень in (r"C:\sender\sender", r"C:\sender\server"):
        for путь, кат, файлы in os.walk(корень):
            кат[:] = [d for d in кат if d not in ("__pycache__", ".venv")]
            for имя in файлы:
                if not имя.endswith(".py"):
                    continue
                п = os.path.join(путь, имя)
                try:
                    т = io.open(п, encoding="utf-8", errors="replace").read()
                except Exception:                              # noqa: BLE001
                    continue
                for м in re.finditer(r"def\s+(\w*lead\w*)\s*\(", т, re.I):
                    print("   %s:%d  %s"
                          % (п.replace("C:\\", ""),
                             т[:м.start()].count("\n") + 1, м.group(1)))
