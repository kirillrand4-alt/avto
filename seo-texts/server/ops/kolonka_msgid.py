# -*- coding: utf-8 -*-
"""Колонка events.rfc_msgid + индекс + заполнение по уже накопленным письмам.

Ставим ДО выкатки кода: append_event начнёт писать в эту колонку, а прогоны
ops создают Store без init_schema — колонки бы не было.
"""
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")
БАЗА = r"C:\sender\sender.db"
ТИПЫ = ("reply", "reply_auto", "bounce", "complaint", "dsn", "other")
from sender.config import Config                                   # noqa: E402
from sender.store import Store                                     # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", БАЗА))

with store.transaction() as conn:
    try:
        conn.execute("ALTER TABLE events ADD COLUMN rfc_msgid TEXT")
        print("колонка rfc_msgid добавлена")
    except sqlite3.OperationalError as ex:
        print("колонка: %s" % ex)
    conn.execute("CREATE INDEX IF NOT EXISTS ix_events_msgid "
                 "  ON events(mailbox_id, rfc_msgid)")
    print("индекс ix_events_msgid на месте")

метки = ",".join("?" * len(ТИПЫ))
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
надо = []
for r in c.execute("SELECT id, detail_json FROM events "
                   " WHERE event_type IN (%s) AND rfc_msgid IS NULL" % метки,
                   list(ТИПЫ)):
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:
        continue
    шапка = (d.get("headers") or {}) if isinstance(d, dict) else {}
    з = ""
    for имя in ("Message-ID", "Message-Id", "message-id"):
        if шапка.get(имя):
            з = str(шапка[имя]).strip().strip("<>").lower()[:400]
            break
    if з:
        надо.append((з, r["id"]))
c.close()
print("событий без заполненного Message-ID, у которых он есть в заголовках: %d"
      % len(надо))
if надо:
    with store.transaction() as conn:
        conn.executemany("UPDATE events SET rfc_msgid=? WHERE id=?", надо)
print("заполнено: %d" % len(надо))

c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
n = c.execute("SELECT COUNT(*) FROM events WHERE rfc_msgid IS NOT NULL").fetchone()[0]
d = c.execute("SELECT COUNT(*) FROM (SELECT mailbox_id, rfc_msgid FROM events "
              "  WHERE rfc_msgid IS NOT NULL GROUP BY 1,2 HAVING COUNT(*)>1)"
              ).fetchone()[0]
print("итого с Message-ID: %d, из них групп-повторов: %d" % (n, d))
c.close()
