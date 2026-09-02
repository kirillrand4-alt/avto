# -*- coding: utf-8 -*-
"""Поставить письма кампании 12 в начало очереди.

Цикл берёт письма по 10 штук в порядке scheduled_at. Впереди стоят письма
кампании 11, большинству из которых слать некем (в пуле mail.ru нет ни
одного meyer-ящика), и проход тратится на них. Двигаем срок наших писем
раньше, чем у кампании 11: очерёдность это единственное, на что влияет
scheduled_at у уже созревшего письма.

argv: проба | делать
"""
import datetime as dt
import sqlite3
import sys

ДЕЛАТЬ = (sys.argv[1] if len(sys.argv) > 1 else "проба") == "делать"
НОВЫЙ = dt.datetime.now().replace(hour=4, minute=30, second=0, microsecond=0)

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
голова = c.execute("SELECT MIN(scheduled_at) м FROM messages WHERE status='scheduled'"
                   " AND campaign_id=11").fetchone()["м"]
print("самый ранний срок в кампании 11: %s" % голова)
print("новый срок нашим: %s" % НОВЫЙ.isoformat())
n = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12"
              " AND status='scheduled'").fetchone()[0]
print("наших писем к сдвигу: %d" % n)

if not ДЕЛАТЬ:
    print("ничего не изменено (режим пробы)")
    raise SystemExit(0)

cur = c.execute("UPDATE messages SET scheduled_at=?, updated_at=?"
                " WHERE campaign_id=12 AND status='scheduled'",
                (НОВЫЙ.isoformat(), dt.datetime.now().isoformat()))
c.commit()
print("сдвинуто: %d" % cur.rowcount)

now_iso = dt.datetime.now().isoformat()
sql = """SELECT m.campaign_id FROM messages m
         WHERE m.status='scheduled' AND m.scheduled_at <= ?
           AND (SELECT cr.status FROM confirm_reviews cr WHERE cr.message_id=m.id
                 ORDER BY cr.id DESC LIMIT 1) IN ('approved','edited')
         ORDER BY m.scheduled_at, m.id LIMIT 10"""
голова10 = [р["campaign_id"] for р in c.execute(sql, (now_iso,))]
print("первая десятка очереди теперь: кампании %s" % голова10)
