# -*- coding: utf-8 -*-
"""Куда делись письма прогона: новые карточки, переписанные и очередь.

Новых карточек после старта только 415, а по логам блоки написали 369 + 445
= 814 писем. Разница не потерялась: блок КЦ пошёл по компаниям, которые уже
имели карточку (те самые 943, возвращённые в пул), и ПЕРЕПИСАЛ их, а не
завёл новые. Считаем оба множества и смотрим, почему очередь отправки не
растёт.
"""
import sqlite3
from collections import Counter

СТАРТ = "2026-08-25 10:41"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row

новые = c.execute(
    "SELECT COUNT(*) FROM confirm_reviews WHERE created_at >= ?",
    (СТАРТ,)).fetchone()[0]
переписаны = c.execute(
    "SELECT COUNT(*) FROM confirm_reviews "
    " WHERE updated_at >= ? AND created_at < ?", (СТАРТ, СТАРТ)).fetchone()[0]
print("карточек ЗАВЕДЕНО прогоном:    %d" % новые)
print("карточек ПЕРЕПИСАНО прогоном:  %d" % переписаны)
print("итого тронуто:                 %d" % (новые + переписаны))

print("\n=== СОСТОЯНИЕ ВСЕХ ТРОНУТЫХ ===")
for р in c.execute(
        "SELECT cr.status cs, COALESCE(m.status,'нет письма') ms, COUNT(*) n "
        "  FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id "
        " WHERE cr.updated_at >= ? OR cr.created_at >= ? "
        " GROUP BY cs, ms ORDER BY n DESC", (СТАРТ, СТАРТ)):
    print("   карта %-10s / письмо %-16s %5d" % (р["cs"], р["ms"], р["n"]))

print("\n=== ПОЧЕМУ ОЧЕРЕДЬ ОТПРАВКИ НЕ РАСТЁТ ===")
print("   письмо попадает в отправку (scheduled) только после подтверждения:")
print("   генерация кладёт карточку в 'ждут подтверждения' (pending),")
print("   письмо при этом лежит в pending_review и автоотправке не видно.")
for р in c.execute("SELECT status, COUNT(*) n FROM messages "
                   " WHERE status IN ('pending_review','scheduled') "
                   " GROUP BY status"):
    print("   письма %-16s %5d" % (р["status"], р["n"]))
ждут = c.execute("SELECT COUNT(*) FROM confirm_reviews "
                 " WHERE status IN ('pending','edited')").fetchone()[0]
print("   карточек ждут подтверждения: %d" % ждут)

print("\n=== ЧТО ИМЕННО ЖДЁТ ПОДТВЕРЖДЕНИЯ (последние 8) ===")
for р in c.execute(
        "SELECT cr.id, substr(cr.created_at,6,11) когда, r.company_name, "
        "       m.subject FROM confirm_reviews cr "
        "  LEFT JOIN recipients r ON r.id=cr.recipient_id "
        "  LEFT JOIN messages m ON m.id=cr.message_id "
        " WHERE cr.status='pending' ORDER BY cr.id DESC LIMIT 8"):
    print("   #%-6s %s %-30s %s" % (р["id"], р["когда"],
                                    str(р["company_name"] or "")[:30],
                                    str(р["subject"] or "")[:44]))
