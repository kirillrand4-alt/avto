# -*- coding: utf-8 -*-
"""Убрать из ленты уже накопленный служебный мусор.

Новый код такие письма в ленту больше не пускает, но 154 записи уже лежат:
106 агрегированных отчётов DMARC и 48 обломков их вложений («PK□□□□□CJ ]юд⊥пЙ»).
Меняем им тип на 'otchet' (из ленты исчезают, в журнале остаются), снимаем
ошибочную привязку к карточке компании и заменяем двоичное тело пометкой.
"""
import json
import os
import re
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
БАЗА = r"C:\sender\sender.db"
ЖУРНАЛ = r"C:\sender\_ops\pochistka-lenty.jsonl"
ТЕМА = re.compile(r"^\s*report[_ -]?domain\s*:", re.I)

c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
правки = []
for r in c.execute("SELECT id, event_type, recipient_id, detail_json FROM events "
                   " WHERE event_type='other'"):
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:
        continue
    if not isinstance(d, dict):
        continue
    h = d.get("headers") or {}
    от = str(h.get("From") or "").lower()
    тема = str(h.get("Subject") or "")
    тип = str(h.get("Content-Type") or "").lower()
    т = str(d.get("snippet") or "")
    печатных = sum(1 for x in т[:300] if x.isprintable()) / max(1, len(т[:300]))
    отчёт = (ТЕМА.match(тема) or "aggregate dmarc" in т.lower()
             or ("dmarc" in от and "report" in тема.lower()))
    двоичное = т and печатных < 0.85
    if not (отчёт or двоичное):
        continue
    новое_тело = т
    if двоичное:
        имя = ""
        м = re.search(r'name="([^"]+)"', тип)
        if м:
            имя = м.group(1)
        новое_тело = "[вложение %s%s]" % (тип.split(";")[0].strip() or "?",
                                          (", " + имя) if имя else "")
    правки.append((r["id"], r["recipient_id"], новое_тело if двоичное else None,
                   "отчёт" if отчёт else "двоичное"))
print("записей «входящее вне переписки» под чистку: %d" % len(правки))
print("   из них отчёты: %d, двоичные обломки: %d"
      % (sum(1 for x in правки if x[3] == "отчёт"),
         sum(1 for x in правки if x[3] == "двоичное")))
print("   с ошибочной привязкой к компании: %d"
      % sum(1 for x in правки if x[1]))
c.close()

if not КАТИТЬ:
    print("\n[сухой прогон] с --katit применю")
    raise SystemExit(0)

from sender.config import Config                                   # noqa: E402
from sender.store import Store                                     # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", БАЗА))
ж = open(ЖУРНАЛ, "a", encoding="utf-8")
сделано = 0
try:
    with store.transaction() as conn:
        for eid, rid, тело, вид in правки:
            строка = conn.execute("SELECT detail_json FROM events WHERE id=?",
                                  (eid,)).fetchone()
            try:
                d = json.loads(строка["detail_json"] or "{}")
            except Exception:
                d = {}
            ж.write(json.dumps({"id": eid, "byl_rid": rid, "vid": вид},
                               ensure_ascii=False) + "\n")
            if тело is not None:
                d["snippet"] = тело
                d["telo_ubrano"] = "двоичное вложение, показывать нечего"
                conn.execute("UPDATE events SET event_type='otchet', "
                             "  recipient_id=NULL, detail_json=? WHERE id=?",
                             (json.dumps(d, ensure_ascii=False), eid))
            else:
                conn.execute("UPDATE events SET event_type='otchet', "
                             "  recipient_id=NULL WHERE id=?", (eid,))
            сделано += 1
    ж.flush()
    os.fsync(ж.fileno())
finally:
    ж.close()
print("\nубрано из ленты: %d (журнал %s)" % (сделано, ЖУРНАЛ))
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
for r in c.execute("SELECT event_type, COUNT(*) n FROM events "
                   " WHERE event_type IN ('other','otchet') GROUP BY 1"):
    print("   %-10s %d" % (r["event_type"], r["n"]))
c.close()
