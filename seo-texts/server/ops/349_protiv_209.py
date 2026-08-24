# -*- coding: utf-8 -*-
"""Почему виджет пишет «ждут подтверждения 349», а в очереди 209.

Два числа считают разное. Виджет ёмкости берёт сырой счёт по статусу, а
список очереди отдаёт confirm_list — а он умеет прятать письма шторкой
updated_after («показывать только тронутые после метки») и разделять
письма и ответы по kind. Смотрим, что из этого даёт разницу.
"""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

всего = c.execute("SELECT COUNT(*) n FROM confirm_reviews WHERE status='pending'"
                  ).fetchone()["n"]
print("pending всего: %d" % всего)

print("\n=== ПО ВИДУ (kind) ===")
for р in c.execute("SELECT COALESCE(kind,'(пусто)') k, COUNT(*) n "
                   "  FROM confirm_reviews WHERE status='pending' "
                   " GROUP BY k ORDER BY n DESC"):
    print("  %-14s %5d" % (р["k"], р["n"]))

print("\n=== ШТОРКА updated_after ===")
кол = [к[1] for к in c.execute("PRAGMA table_info(panel_settings)")]
for р in c.execute("SELECT key, value FROM panel_settings "
                   " WHERE key LIKE '%confirm%' OR key LIKE '%after%' "
                   "    OR key LIKE '%shtor%' OR key LIKE '%hide%'"):
    print("  %-34s = %s" % (р["key"], str(р["value"])[:40]))

print("\n=== СКОЛЬКО ПРОЙДЁТ ШТОРКУ ПРИ РАЗНЫХ МЕТКАХ ===")
for метка in ("2026-08-24T00:00", "2026-08-24T10:00", "2026-08-24T12:00",
              "2026-08-24T12:30"):
    н = c.execute(
        "SELECT COUNT(*) n FROM confirm_reviews WHERE status='pending' "
        "  AND (updated_at >= ? OR kind='reply')", (метка,)).fetchone()["n"]
    print("  тронутые после %s: %d" % (метка, н))

print("\n=== PENDING ПО ЧАСАМ СОЗДАНИЯ ===")
for р in c.execute(
        "SELECT substr(created_at,1,13) ч, COUNT(*) n FROM confirm_reviews "
        " WHERE status='pending' GROUP BY ч ORDER BY ч DESC LIMIT 10"):
    print("  %s  %d" % (р["ч"], р["n"]))

print("\n=== ЕСТЬ ЛИ У PENDING ПИСЬМО (без него карточку могут не показывать) ===")
for р in c.execute(
        "SELECT CASE WHEN cr.message_id IS NULL THEN 'без письма' "
        "            ELSE COALESCE(m.status,'письма нет в базе') END с, COUNT(*) n "
        "  FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id "
        " WHERE cr.status='pending' GROUP BY с ORDER BY n DESC"):
    print("  %-24s %5d" % (р["с"], р["n"]))

print("\n=== А ЧТО СЧИТАЕТ ВИДЖЕТ «ОЖИДАЕТ ОТПРАВКИ» ===")
for р in c.execute(
        "SELECT status, COUNT(*) n FROM messages "
        " WHERE status IN ('scheduled','queued','sending','pending_review') "
        " GROUP BY status ORDER BY n DESC"):
    print("  письма %-16s %5d" % (р["status"], р["n"]))
