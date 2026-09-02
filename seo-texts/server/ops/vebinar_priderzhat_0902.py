# -*- coding: utf-8 -*-
"""Придержать письма кампании 12: сдвинуть срок, чтобы claim_due их не брал,
пока разбираемся с подбором ящика. Обратимо: срок возвращается одной правкой.

argv: <часов вперёд, по умолчанию 12> | вернуть
"""
import datetime as dt
import sqlite3
import sys

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
арг = sys.argv[1] if len(sys.argv) > 1 else "12"

сейчас = dt.datetime.now()
if арг == "вернуть":
    когда = сейчас
else:
    когда = сейчас + dt.timedelta(hours=float(арг))

было = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12"
                 " AND status='scheduled' AND scheduled_at<=?",
                 (сейчас.isoformat(),)).fetchone()[0]
cur = c.execute("UPDATE messages SET scheduled_at=?, updated_at=?"
                " WHERE campaign_id=12 AND status='scheduled'",
                (когда.isoformat(), сейчас.isoformat()))
c.commit()
ушло = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12"
                 " AND status='sent'").fetchone()[0]
готовы = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12"
                   " AND status='scheduled' AND scheduled_at<=?",
                   (сейчас.isoformat(),)).fetchone()[0]
print("сдвинуто писем: %d" % cur.rowcount)
print("  новый срок: %s" % когда.isoformat(timespec="seconds"))
print("  успели уйти до этого: %d" % ушло)
print("  созревших прямо сейчас: %d (было %d)" % (готовы, было))
