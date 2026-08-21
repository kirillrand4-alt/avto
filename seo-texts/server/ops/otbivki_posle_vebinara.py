# -*- coding: utf-8 -*-
"""Что за отбивки прилетели после вебинарной отправки: разбор по событиям.

Владелец показал ленту: bounce/suppress по кампаниям 10 и 11 с ящиков
i.kuznetsova@sort-systems.ru, a.kozlov@zernosort.ru,
o.tseyzer@kompressor-pro-expert.ru. Надо понять: это мёртвые адреса
(жёсткие), временные (мягкие) или отказ нашего почтовика по спаму - от
этого зависит, что делать с доменами.
"""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
колонки = [р[1] for р in c.execute("PRAGMA table_info(events)")]
print("колонки events:", ", ".join(колонки))

ряды = c.execute(
    "SELECT * FROM events WHERE substr(COALESCE(event_ts,created_at),1,10)"
    "='2026-08-21' ORDER BY id DESC LIMIT 400").fetchall()
print(f"\nсобытий сегодня: {len(ряды)}")
print("типы:", dict(Counter(str(р["event_type"]) for р in ряды)))

интерес = [р for р in ряды if str(р["event_type"]) in
           ("bounce", "suppress", "complaint", "send_failed", "spam")]
print(f"\nотбивки/стоп-листы сегодня: {len(интерес)}")
поле = "detail" if "detail" in колонки else (
    "payload" if "payload" in колонки else None)
for р in интерес[:30]:
    д = dict(р)
    текст = " ".join(str(д.get(k) or "") for k in
                     ("reason", "detail", "payload", "note", "error", "meta"))
    print(f"  #{д.get('id')} {д.get('event_type'):<10} камп{д.get('campaign_id')} "
          f"{str(д.get('mailbox_id') or '-'):<38} {str(д.get('event_ts'))[:16]}")
    if текст.strip():
        print(f"       {текст[:150]}")
