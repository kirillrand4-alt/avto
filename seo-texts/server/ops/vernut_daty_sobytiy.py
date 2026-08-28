# -*- coding: utf-8 -*-
"""Проставить входящим событиям их НАСТОЯЩЕЕ время получения.

Починка опроса по UID открыла письма, которые раньше глушил совпавший ключ
дедупликации: сегодня в 10:33–11:08 в журнал легли ответы и отбивки от 5, 18,
19, 20, 21, 24–27 августа. event_ts им проставился «когда заметили», и сводка
«Динамика 7 дней» приписала сегодняшнему дню 87 отбивок и 75 ответов чужих
дней — BR% 8.76% вместо реальных.

Берём дату из заголовка Date самого письма, переводим в UTC (журнал ведётся в
UTC) и пишем её в event_ts. Исходную отметку сохраняем в detail.zapisano_ts —
когда мы письмо увидели, тоже факт, и он не должен потеряться.
"""
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
БАЗА = r"C:\sender\sender.db"
ТИПЫ = ("bounce", "reply", "reply_auto", "complaint", "dsn")
СЕГОДНЯ = time.strftime("%Y-%m-%d")
ЖУРНАЛ = r"C:\sender\_ops\vernut-daty-sobytiy.jsonl"

c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
правки, беззаголовка, кривые, свои = [], 0, 0, 0
метки = ",".join("?" * len(ТИПЫ))
for r in c.execute("SELECT id, event_type, event_ts, detail_json FROM events "
                   " WHERE event_type IN (%s) AND event_ts LIKE ?" % метки,
                   list(ТИПЫ) + [СЕГОДНЯ + "%"]):
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:
        d = {}
    if not isinstance(d, dict):
        d = {}
    if d.get("zapisano_ts"):
        continue                      # уже переставляли
    дата = str((d.get("headers") or {}).get("Date") or "").strip()
    if not дата:
        беззаголовка += 1
        continue
    try:
        т = parsedate_to_datetime(дата)
    except Exception:
        кривые += 1
        continue
    if т is None:
        кривые += 1
        continue
    if т.tzinfo is None:
        т = т.replace(tzinfo=timezone.utc)
    т = т.astimezone(timezone.utc).replace(tzinfo=None)
    # здравый смысл: не раньше начала работы и не в будущем
    if т < datetime(2026, 1, 1) or т > datetime.utcnow():
        кривые += 1
        continue
    новый = т.strftime("%Y-%m-%dT%H:%M:%S")
    if новый[:10] == СЕГОДНЯ:
        свои += 1                     # письмо и правда сегодняшнее
        continue
    правки.append((r["id"], r["event_type"], str(r["event_ts"]), новый))

по_типам = {}
по_дням = {}
for _, тип, _, новый in правки:
    по_типам[тип] = по_типам.get(тип, 0) + 1
    по_дням[новый[:10]] = по_дням.get(новый[:10], 0) + 1
print("сегодня в журнале событий этих типов — разбор:")
print("  переставить (письмо чужого дня): %d" % len(правки))
print("  настоящие сегодняшние:           %d" % свои)
print("  без заголовка Date:              %d" % беззаголовка)
print("  дата не разобралась:             %d" % кривые)
print("  по типам: %s" % ", ".join("%s=%d" % кv for кv in sorted(по_типам.items())))
print("  разъедутся по дням: %s"
      % ", ".join("%s→%d" % кv for кv in sorted(по_дням.items())))
c.close()

if not КАТИТЬ:
    print("\n[сухой прогон] с --katit проставлю")
    raise SystemExit(0)

from sender.config import Config                                   # noqa: E402
from sender.store import Store                                     # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", БАЗА))
сделано = 0
ж = open(ЖУРНАЛ, "a", encoding="utf-8")
try:
    with store.transaction() as conn:
        for eid, тип, старый, новый in правки:
            строка = conn.execute("SELECT detail_json FROM events WHERE id=?",
                                  (eid,)).fetchone()
            try:
                d = json.loads(строка["detail_json"] or "{}")
            except Exception:
                d = {}
            if not isinstance(d, dict):
                d = {}
            d["zapisano_ts"] = старый
            conn.execute("UPDATE events SET event_ts=?, detail_json=? WHERE id=?",
                         (новый, json.dumps(d, ensure_ascii=False), eid))
            ж.write(json.dumps(
                {"id": eid, "tip": тип, "bylo": старый, "stalo": новый},
                ensure_ascii=False) + "\n")
            сделано += 1
    ж.flush()
    os.fsync(ж.fileno())
finally:
    ж.close()
print("\nпереставлено событий: %d (журнал %s)" % (сделано, ЖУРНАЛ))

c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
print("\n=== ДИНАМИКА 7 ДНЕЙ ПОСЛЕ ПРАВКИ ===")
print("%-12s %6s %7s %8s %7s %8s" % ("день", "отпр", "bounce", "жалобы",
                                     "ответы", "BR%"))
for i in range(6, -1, -1):
    д = datetime.utcfromtimestamp(time.time() - i * 86400).strftime("%Y-%m-%d")
    зн = {}
    for тип in ("sent", "bounce", "complaint", "reply"):
        зн[тип] = c.execute("SELECT COUNT(*) FROM events WHERE event_type=? "
                            "  AND event_ts LIKE ?", (тип, д + "%")).fetchone()[0]
    br = (100.0 * зн["bounce"] / зн["sent"]) if зн["sent"] else 0.0
    print("%-12s %6d %7d %8d %7d %7.2f%%"
          % (д, зн["sent"], зн["bounce"], зн["complaint"], зн["reply"], br))
c.close()
