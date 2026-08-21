# -*- coding: utf-8 -*-
"""Почему в ленте все отбивки стоят одним временем 17:00.

В ленте владельца семь строк с одинаковой меткой «21.08.2026, 17:00», и
это само по себе читается как всплеск. Сверяем: event_ts (когда случилось)
против created_at (когда мы записали) - разбор входящей почты идёт опросом
IMAP, и целая пачка отбивок попадает в базу одним заходом.
"""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
for р in c.execute(
        "SELECT id, event_type, event_ts, created_at, mailbox_id "
        "  FROM events "
        " WHERE event_type IN ('bounce','suppress') "
        "   AND substr(COALESCE(event_ts,created_at),1,10)='2026-08-21' "
        " ORDER BY id"):
    print(f"#{р['id']:<7} {р['event_type']:<9} случилось={str(р['event_ts'])[:19]:<19} "
          f"записано={str(р['created_at'])[:19]:<19} {str(р['mailbox_id'] or '-')[:34]}")
