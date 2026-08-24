# -*- coding: utf-8 -*-
"""Реально ли уходят письма: отправлено за сегодня и не залипла ли пачка.

В очереди сообщений десять строк в состоянии sending — это ровно размер
пачки цикла (batch=10). Но то же самое видно и когда пачка застряла
после сбоя: статус остаётся, а движения нет. Разница видна только по
времени: свежая пачка живёт секунды, залипшая — часы.

Считаем отправленное за сегодня по факту, смотрим возраст висящих и
последние ошибки.
"""
import sqlite3
import time

СЕГОДНЯ = time.strftime("%Y-%m-%d")
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

кол = [с[1] for с in c.execute("PRAGMA table_info(messages)")]
print("колонки messages:", ", ".join(кол))

поле_в = next((п for п in ("sent_at", "updated_at", "last_attempt_at",
                           "scheduled_at", "created_at") if п in кол), None)
print("считаю по полю времени:", поле_в)

if поле_в:
    print("\n=== ДВИЖЕНИЕ ЗА ТРИ ДНЯ ===")
    for р in c.execute(
            "SELECT substr(%s,1,10) д, status, COUNT(*) n FROM messages "
            "WHERE %s >= date('now','-3 day') GROUP BY д, status "
            "ORDER BY д DESC, n DESC LIMIT 24" % (поле_в, поле_в)):
        print("  %s  %-14s %d" % (р["д"], р["status"], р["n"]))

print("\n=== ВИСЯЩИЕ В sending ===")
поля = [п for п in ("id", "status", "scheduled_at", "updated_at", "sent_at",
                    "mailbox_id", "last_error") if п in кол]
for р in c.execute("SELECT %s FROM messages WHERE status='sending' "
                   "ORDER BY id DESC LIMIT 12" % ", ".join(поля)):
    print("  " + " | ".join("%s=%s" % (п, str(р[п])[:38]) for п in поля
                            if р[п] not in (None, "")))

print("\n=== ПОСЛЕДНИЕ ОТПРАВЛЕННЫЕ ===")
if "sent_at" in кол:
    for р in c.execute("SELECT id, sent_at, mailbox_id FROM messages "
                       "WHERE status='sent' AND sent_at IS NOT NULL "
                       "ORDER BY sent_at DESC LIMIT 8"):
        print("  #%-6s %s  ящик %s" % (р["id"], р["sent_at"], р["mailbox_id"]))
else:
    for р in c.execute("SELECT %s FROM messages WHERE status='sent' "
                       "ORDER BY id DESC LIMIT 8" % ", ".join(поля)):
        print("  " + " | ".join("%s=%s" % (п, str(р[п])[:32]) for п in поля
                                if р[п] not in (None, "")))

print("\n=== ПОСЛЕДНИЕ СБОИ ===")
if "last_error" in кол:
    for р in c.execute("SELECT id, status, last_error FROM messages "
                       "WHERE last_error IS NOT NULL AND last_error<>'' "
                       "ORDER BY id DESC LIMIT 6"):
        print("  #%-6s %-10s %s" % (р["id"], р["status"],
                                    str(р["last_error"])[:110]))

print("\n=== СОБЫТИЯ ОТПРАВКИ ЗА СЕГОДНЯ ===")
табл = {р[0] for р in c.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")}
if "events" in табл:
    ек = [с[1] for с in c.execute("PRAGMA table_info(events)")]
    поле_т = next((п for п in ("ts", "created_at", "at") if п in ек), None)
    поле_с = next((п for п in ("event_type", "type", "kind") if п in ек), None)
    print("  колонки events:", ", ".join(ек))
    if поле_т and поле_с:
        for р in c.execute(
                "SELECT %s с, COUNT(*) n FROM events WHERE substr(%s,1,10)=? "
                "GROUP BY с ORDER BY n DESC LIMIT 12" % (поле_с, поле_т),
                (СЕГОДНЯ,)):
            print("  %-20s %d" % (р["с"], р["n"]))
