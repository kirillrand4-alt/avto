# -*- coding: utf-8 -*-
"""Только чтение: темп отправки с ПРАВИЛЬНЫМ сравнением времени.

events.created_at лежит в ISO с буквой T, а datetime('now') отдаёт строку с
пробелом. Строковое сравнение считает T больше пробела, поэтому фильтр
«за последние N минут» через datetime() захватывает всё подряд. Сравниваем
с ISO-строкой, собранной питоном."""
import sqlite3
from datetime import datetime, timedelta, timezone

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row


def iso(мин):
    return (datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(minutes=мин)).isoformat()


print("=== ОТПРАВЛЕНО (правильное сравнение) ===")
for м in (5, 10, 15, 30, 60):
    n = s.execute("SELECT COUNT(*) n FROM events WHERE event_type='sent'"
                  " AND created_at >= ?", (iso(м),)).fetchone()["n"]
    print("  за последние %3d мин: %4d  (%.1f писем/мин)" % (м, n, n / float(м)))

сег = s.execute("SELECT COUNT(*) n FROM events WHERE event_type='sent'"
                " AND created_at >= ?",
                (datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00"),)).fetchone()["n"]
print("  за сегодня всего   : %4d" % сег)

print("\n=== ПО 5 МИНУТ, последний час ===")
for р in s.execute("SELECT substr(created_at,1,15) м, COUNT(*) n FROM events"
                   " WHERE event_type='sent' AND created_at >= ?"
                   " GROUP BY м ORDER BY м", (iso(60),)):
    print("  %s0  %d" % (р["м"], р["n"]))

print("\n=== ИТОГ ===")
n15 = s.execute("SELECT COUNT(*) n FROM events WHERE event_type='sent'"
                " AND created_at >= ?", (iso(15),)).fetchone()["n"]
темп = n15 / 15.0
оч = s.execute("SELECT COUNT(*) n FROM messages WHERE status='scheduled'").fetchone()["n"]
мск = datetime.now()
до = (14 * 60) - (мск.hour * 60 + мск.minute)
print("  сейчас мск %s, до закрытия окна %d мин" % (мск.strftime("%H:%M"), до))
print("  темп сейчас: %.1f писем/мин" % темп)
print("  за оставшееся время при таком темпе: %d писем" % int(темп * до))
print("  в очереди: %d" % оч)
print("  свободная ёмкость ящиков: 410 (замерена отдельно)")
уйдёт = min(410, int(темп * до), оч)
print("  УЙДЁТ СЕГОДНЯ примерно: %d" % уйдёт)
print("  ОСТАНЕТСЯ: примерно %d" % max(0, оч - уйдёт))
