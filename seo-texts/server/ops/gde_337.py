# -*- coding: utf-8 -*-
"""Найти карточки, подтверждённые вчера, и понять, что мешает им уйти."""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
print("сегодня по базе: %s" % c.execute("SELECT date('now')").fetchone()[0])

print("\n=== ОЧЕРЕДЬ ПО СТАТУСАМ ===")
for р in c.execute("SELECT status, COUNT(*) n FROM confirm_reviews "
                   " GROUP BY status ORDER BY n DESC"):
    print("  %-14s %5d" % (р["status"], р["n"]))

print("\n=== ВОЗВРАЩЁННЫЕ МНОЙ (снято по устаревшему правилу 2) ===")
for р in c.execute(
        "SELECT cr.status, COALESCE(m.status,'нет письма') mst, COUNT(*) n "
        "  FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id "
        " WHERE cr.reason LIKE '%устаревшему правилу 2%' "
        " GROUP BY cr.status, mst ORDER BY n DESC"):
    print("  карточка %-10s письмо %-16s %5d" % (р["status"], р["mst"], р["n"]))

print("\n=== ЧТО ЖДЁТ ОТПРАВКИ (письма в нетерминальных статусах) ===")
for р in c.execute(
        "SELECT m.status, COUNT(*) n FROM messages m "
        " WHERE m.status NOT IN ('sent','skipped','failed') GROUP BY m.status"):
    print("  письмо %-16s %5d" % (р["status"], р["n"]))

print("\n=== ПОДТВЕРЖДЕНЫ ВЧЕРА (approved/edited за 24.08) ===")
for р in c.execute(
        "SELECT cr.status, COALESCE(m.status,'нет письма') mst, COUNT(*) n "
        "  FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id "
        " WHERE substr(COALESCE(cr.decided_at,''),1,10)='2026-08-24' "
        "   AND cr.status IN ('approved','edited') "
        " GROUP BY cr.status, mst ORDER BY n DESC"):
    print("  карточка %-10s письмо %-16s %5d" % (р["status"], р["mst"], р["n"]))

print("\n=== ОТПРАВКА ЗА ПОСЛЕДНИЕ СУТКИ ===")
for р in c.execute(
        "SELECT substr(COALESCE(sent_at,''),1,10) д, COUNT(*) n FROM messages "
        " WHERE status='sent' AND sent_at >= datetime('now','-2 days') "
        " GROUP BY д ORDER BY д"):
    print("  %s  %d" % (р["д"], р["n"]))

print("\n=== АВТООТПРАВКА ВКЛЮЧЕНА? ===")
for р in c.execute("SELECT key, value FROM panel_settings "
                   " WHERE key LIKE '%auto%' OR key LIKE '%probe%'"):
    print("  %-30s = %s" % (р["key"], р["value"]))
