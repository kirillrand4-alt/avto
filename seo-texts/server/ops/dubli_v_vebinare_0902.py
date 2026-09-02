# -*- coding: utf-8 -*-
"""Только чтение: кому в кампании 12 ушло больше одного письма."""
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row

print("=== ОДИН И ТОТ ЖЕ АДРЕС В КАМПАНИИ 12 ===")
n = c.execute("SELECT COUNT(*) FROM (SELECT r.email FROM messages m JOIN recipients r"
              " ON r.id=m.recipient_id WHERE m.campaign_id=12"
              " GROUP BY r.email HAVING COUNT(*)>1)").fetchone()[0]
print("  адресов с двумя письмами: %d" % n)

print("\n=== ОДНА КОМПАНИЯ ПО ИНН ===")
for р in c.execute(
        "SELECT r.inn, MAX(r.company_name) им,"
        " SUM(m.status='sent') ушло, SUM(m.status='scheduled') ждёт,"
        " SUM(m.status='skipped') снято, COUNT(*) всего"
        " FROM messages m JOIN recipients r ON r.id=m.recipient_id"
        " WHERE m.campaign_id=12 AND r.inn IS NOT NULL AND r.inn<>''"
        " GROUP BY r.inn HAVING всего>1 ORDER BY ушло DESC, всего DESC"):
    print("  %-12s %-26s всего %d: ушло %d, ждёт %d, снято %d"
          % (р["inn"], str(р["им"])[:26], р["всего"], р["ушло"], р["ждёт"], р["снято"]))

print("\n=== ОДИН ДОМЕН ПОЧТЫ (ловит и тех, у кого ИНН не нашли) ===")
for р in c.execute(
        "SELECT r.domain, SUM(m.status='sent') ушло, SUM(m.status='scheduled') ждёт,"
        " COUNT(*) всего, GROUP_CONCAT(r.email) поч"
        " FROM messages m JOIN recipients r ON r.id=m.recipient_id"
        " WHERE m.campaign_id=12 AND r.domain NOT IN"
        " ('mail.ru','gmail.com','yandex.ru','list.ru','bk.ru','inbox.ru','ya.ru',"
        "  'rambler.ru','icloud.com','yahoo.com','outlook.com','mail.com')"
        " GROUP BY r.domain HAVING всего>1 ORDER BY ушло DESC, всего DESC"):
    print("  %-26s всего %d: ушло %d, ждёт %d"
          % (р["domain"][:26], р["всего"], р["ушло"], р["ждёт"]))
    print("      %s" % str(р["поч"])[:104])

print("\n=== ИТОГ ===")
всего = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12").fetchone()[0]
ушло = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12"
                 " AND status='sent'").fetchone()[0]
д = c.execute("SELECT COUNT(*) FROM (SELECT r.inn FROM messages m JOIN recipients r"
              " ON r.id=m.recipient_id WHERE m.campaign_id=12 AND m.status='sent'"
              " AND r.inn IS NOT NULL AND r.inn<>'' GROUP BY r.inn"
              " HAVING COUNT(*)>1)").fetchone()[0]
дд = c.execute("SELECT COUNT(*) FROM (SELECT r.domain FROM messages m JOIN recipients r"
               " ON r.id=m.recipient_id WHERE m.campaign_id=12 AND m.status='sent'"
               " AND r.domain NOT IN ('mail.ru','gmail.com','yandex.ru','list.ru',"
               " 'bk.ru','inbox.ru','ya.ru','rambler.ru') GROUP BY r.domain"
               " HAVING COUNT(*)>1)").fetchone()[0]
print("  писем в кампании %d, отправлено %d" % (всего, ушло))
print("  компаний, получивших 2+ письма УЖЕ: по ИНН %d, по домену %d" % (д, дд))
