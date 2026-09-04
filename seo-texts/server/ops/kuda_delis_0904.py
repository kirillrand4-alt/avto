# -*- coding: utf-8 -*-
"""Только чтение: что происходит с письмами партии 13 прямо сейчас."""
import datetime as dt
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
мск = dt.datetime.now()
print("сейчас %s МСК" % мск.strftime("%H:%M:%S"))

print("\n=== ПАРТИЯ 13: СТАТУСЫ ===")
for р in c.execute("SELECT status, COUNT(*) k FROM messages WHERE campaign_id=13"
                   " GROUP BY status"):
    print("  %-14s %d" % (р["status"], р["k"]))

print("\n=== ПАРТИЯ 13: СРОКИ ===")
for р in c.execute("SELECT substr(scheduled_at,1,13) ч, COUNT(*) k FROM messages"
                   " WHERE campaign_id=13 GROUP BY ч ORDER BY ч"):
    print("  %-16s %d" % (р["ч"], р["k"]))

print("\n=== КОГДА ИХ ПОСЛЕДНИЙ РАЗ ТРОГАЛИ ===")
for р in c.execute("SELECT substr(updated_at,1,16) м, COUNT(*) k FROM messages"
                   " WHERE campaign_id=13 GROUP BY м ORDER BY м DESC LIMIT 8"):
    print("  %-18s %d" % (р["м"], р["k"]))
print("  с claimed_at: %d"
      % c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=13"
                  " AND claimed_at IS NOT NULL").fetchone()[0])
print("  с попытками>0: %d"
      % c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=13"
                  " AND attempt_count>0").fetchone()[0])

print("\n=== ВСЯ БАЗА: ЧТО ДВИГАЛОСЬ ЗА ПОСЛЕДНИЕ 30 МИНУТ ===")
п30 = (мск - dt.timedelta(minutes=30)).isoformat()
for р in c.execute("SELECT status, COUNT(*) k FROM messages WHERE updated_at>=?"
                   " GROUP BY status ORDER BY k DESC", (п30,)):
    print("  %-14s %d" % (р["status"], р["k"]))

print("\n=== ЗАВИСШИЕ В sending ===")
for р in c.execute("SELECT id, campaign_id, claimed_at, updated_at FROM messages"
                   " WHERE status='sending' ORDER BY claimed_at"):
    print("  msg#%-6s к%-3s взято %s" % (р["id"], р["campaign_id"],
                                         str(р["claimed_at"])[:19]))

print("\n=== ПОСЛЕДНИЕ ОШИБКИ ===")
for р in c.execute("SELECT last_error, COUNT(*) k, MAX(updated_at) п FROM messages"
                   " WHERE last_error IS NOT NULL AND last_error<>''"
                   " AND updated_at>=? GROUP BY last_error ORDER BY п DESC LIMIT 6",
                   ((мск - dt.timedelta(hours=6)).isoformat(),)):
    print("  %s | %s | %d" % (str(р["п"])[:19], str(р["last_error"])[:56], р["k"]))
