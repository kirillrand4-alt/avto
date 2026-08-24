# -*- coding: utf-8 -*-
"""Кто перевёл письма в автоотправку и включён ли сам цикл отправки.

За сегодня 76 карточек из 84 стоят approved с причиной «bulk-to-auto» —
это ручка панели POST /confirm/bulk-to-auto: одобряет пачку разом и
ставит в автоотправку, минуя личное подтверждение оператора. По холду
владельца автоматическая рассылка запрещена, разрешена только ручная с
подтверждением каждого письма.

Отправлено сегодня ноль, но одобренная карточка — ровно то, что цикл
автоотправки берёт первым. Поэтому смотрим три вещи: включён ли цикл,
кто и когда жал ручку, и сколько сообщений реально стоит в очереди на
отправку.
"""
import sqlite3
import time

СЕГОДНЯ = time.strftime("%Y-%m-%d")
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row


def _таблицы():
    return {р[0] for р in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


ТАБЛИЦЫ = _таблицы()

print("=== НАСТРОЙКИ ОТПРАВКИ ===")
if "settings" in ТАБЛИЦЫ:
    for р in c.execute("SELECT key, value FROM settings ORDER BY key"):
        к = str(р["key"])
        if any(с in к.lower() for с in
               ("auto", "send", "warm", "ramp", "probe", "enabled", "mayak")):
            print("  %-34s = %s" % (к, str(р["value"])[:70]))
else:
    print("  таблицы settings нет")

print("\n=== КТО ЖАЛ bulk-to-auto (журнал действий) ===")
найдено = False
for имя in ("audit_log", "audit", "actions", "user_actions", "events"):
    if имя not in ТАБЛИЦЫ:
        continue
    кол = {с[1] for с in c.execute("PRAGMA table_info(%s)" % имя)}
    поле = next((п for п in ("action", "event_type", "type") if п in кол), None)
    if not поле:
        continue
    try:
        строки = c.execute(
            "SELECT * FROM %s WHERE %s LIKE '%%bulk%%' "
            "ORDER BY rowid DESC LIMIT 10" % (имя, поле)).fetchall()
    except Exception as e:                                     # noqa: BLE001
        print("  %s: %s" % (имя, str(e)[:70]))
        continue
    if строки:
        найдено = True
        print("  таблица %s:" % имя)
        for р in строки:
            print("    " + " | ".join(
                "%s=%s" % (k, str(р[k])[:40]) for k in р.keys()
                if р[k] not in (None, "")))
if not найдено:
    print("  записей о bulk-to-auto в журналах действий не нашлось")

print("\n=== СООБЩЕНИЯ В ОЧЕРЕДИ НА ОТПРАВКУ ===")
if "messages" in ТАБЛИЦЫ:
    for р in c.execute("SELECT status, COUNT(*) n FROM messages "
                       "GROUP BY status ORDER BY n DESC LIMIT 10"):
        print("  %-14s %d" % (р["status"], р["n"]))
    кол = {с[1] for с in c.execute("PRAGMA table_info(messages)")}
    поле_д = next((п for п in ("scheduled_at", "created_at", "send_after")
                   if п in кол), None)
    if поле_д:
        н = c.execute("SELECT COUNT(*) FROM messages WHERE substr(%s,1,10)=?"
                      % поле_д, (СЕГОДНЯ,)).fetchone()[0]
        print("  за сегодня по полю %s: %d" % (поле_д, н))
else:
    print("  таблицы messages нет")

print("\n=== ОТПРАВЛЕНО ЗА ТРИ ДНЯ ===")
if "events" in ТАБЛИЦЫ:
    кол = {с[1] for с in c.execute("PRAGMA table_info(events)")}
    if "event_type" in кол and "ts" in кол:
        for р in c.execute(
                "SELECT substr(ts,1,10) д, event_type, COUNT(*) n FROM events "
                "WHERE ts >= date('now','-3 day') "
                "GROUP BY д, event_type ORDER BY д DESC, n DESC LIMIT 20"):
            print("  %s %-16s %d" % (р["д"], р["event_type"], р["n"]))
