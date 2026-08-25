# -*- coding: utf-8 -*-
"""Завести карточку ответу, которому не нашлось компании — просто письмом.

Владелец 25.08: «заведи без компании просто письмом». Человек ответил с
адреса, которого нет в базе, References почтовик срезал — привязать не к
чему, но письмо живое: «у нас стоят винтовые компрессоры». В таблице лидов
обязателен только сам адрес, компания и получатель могут пустовать.
"""
import json
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config      # noqa: E402
from sender.leaddesk import LeadDesk  # noqa: E402
from sender.store import Store        # noqa: E402

СОБЫТИЕ = 182154
БАЗА = r"C:\sender\sender.db"
c = sqlite3.connect(БАЗА, timeout=30)
c.row_factory = sqlite3.Row
р = c.execute("SELECT * FROM events WHERE id=?", (СОБЫТИЕ,)).fetchone()
if not р:
    raise SystemExit("события %s нет" % СОБЫТИЕ)
d = json.loads(р["detail_json"] or "{}")
з = d.get("headers") or {}
откуда = str(з.get("From") or "")
адрес = откуда.split("<")[-1].strip("<> ").lower() if "@" in откуда else ""
текст = " ".join(str(d.get("snippet") or "").split())
print("когда:  %s" % р["event_ts"])
print("в ящик: %s" % (d.get("inbox_mailbox") or р["mailbox_id"]))
print("от:     %s" % откуда)
print("тема:   %s" % з.get("Subject"))
print("\n--- письмо ---\n%s\n" % текст[:1200])

уже = c.execute("SELECT id FROM leads WHERE LOWER(email)=?", (адрес,)).fetchone()
if уже:
    print("карточка уже есть: #%s" % уже["id"])
    raise SystemExit(0)

cfg = Config.load(r"C:\sender\sender.yaml")
десk = LeadDesk(cfg, Store(БАЗА))
метка = d.get("reply_kind") or "reply"
# recipient=None законен: в leads обязательны только email и ключ склейки,
# а компания с получателем пустуют — их просто нечем заполнить.
lid = десk.push_warm_lead(None, "", "[%s] %s" % (метка, текст), otvetil=адрес)
print("заведена карточка: %s" % lid)
for х in sqlite3.connect(БАЗА).execute(
        "SELECT id, email, company_name, reply_kind, status, substr(need,1,60) "
        "  FROM leads WHERE id=?", (lid,)):
    print("   %s" % (х,))
