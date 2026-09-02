# -*- coding: utf-8 -*-
"""Только чтение: одинаковые адреса в кампании 12 и откуда взялись лишние письма."""
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row

print("=== ОДИН И ТОТ ЖЕ АДРЕС ПОЛУЧИЛ ДВА ПИСЬМА ===")
ряды = list(c.execute(
    "SELECT r.email, COUNT(*) k, GROUP_CONCAT(m.id) ид,"
    " GROUP_CONCAT(m.status) ст, GROUP_CONCAT(substr(m.sent_at,12,8)) когда,"
    " GROUP_CONCAT(m.mailbox_id) ящики"
    " FROM messages m JOIN recipients r ON r.id=m.recipient_id"
    " WHERE m.campaign_id=12 GROUP BY r.email HAVING k>1 ORDER BY k DESC"))
print("  таких адресов: %d" % len(ряды))
for р in ряды:
    print("  %-34s x%d | письма %s | %s | %s"
          % (р["email"][:34], р["k"], р["ид"], р["ст"], str(р["когда"])))

print("\n=== ОТКУДА ЛИШНИЕ ПИСЬМА ===")
print("  всего писем в кампании: %d (заводили 175)"
      % c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12").fetchone()[0])
print("  решений в кампании: %d"
      % c.execute("SELECT COUNT(*) FROM confirm_reviews"
                  " WHERE campaign_id=12").fetchone()[0])
print("\n  письма по времени создания:")
for р in c.execute("SELECT substr(created_at,1,16) к, COUNT(*) n FROM messages"
                   " WHERE campaign_id=12 GROUP BY к ORDER BY к"):
    print("    %-18s %d" % (р["к"], р["n"]))
print("\n  решения по времени создания:")
for р in c.execute("SELECT substr(created_at,1,16) к, COUNT(*) n FROM confirm_reviews"
                   " WHERE campaign_id=12 GROUP BY к ORDER BY к"):
    print("    %-18s %d" % (р["к"], р["n"]))

print("\n=== ПОХОЖИЕ АДРЕСА (точка против подчёркивания) ===")
поч = [р["email"] for р in c.execute(
    "SELECT DISTINCT r.email FROM messages m JOIN recipients r ON r.id=m.recipient_id"
    " WHERE m.campaign_id=12")]
норм = {}
for e in поч:
    л, _, д = e.partition("@")
    к = л.replace(".", "").replace("_", "").replace("-", "") + "@" + д
    норм.setdefault(к, []).append(e)
for к, сп in норм.items():
    if len(сп) > 1:
        print("  %s" % ", ".join(сп))
