# -*- coding: utf-8 -*-
"""Только чтение: что легло в кампанию 13."""
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
print("=== КАМПАНИЯ 13 ===")
р = c.execute("SELECT name, status, config_json FROM campaigns WHERE id=13").fetchone()
print("  %s | %s | %s" % (р["name"], р["status"], str(р["config_json"])[:130]))
for x in c.execute("SELECT status, COUNT(*) k FROM confirm_reviews WHERE campaign_id=13"
                   " GROUP BY status"):
    print("  решений %-12s %d" % (x["status"], x["k"]))
print("  писем (messages): %d"
      % c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=13").fetchone()[0])
print("  с пометкой «повтор разрешён»: %d"
      % c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=13"
                  " AND reason LIKE '%повтор разрешён%'").fetchone()[0])

print("\n=== ПРОВЕРКИ ТЕКСТА ===")
n = c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=13").fetchone()[0]
м = c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=13"
              " AND body LIKE '%ИМЯ_ОТПРАВИТЕЛЯ%'").fetchone()[0]
print("  всего %d, с меткой отправителя %d, без метки %d" % (n, м, n - м))
for сл in ("вебинар", "августа", "завтра"):
    k = c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=13"
                  " AND (body LIKE ? OR subject LIKE ?)",
                  ("%" + сл + "%", "%" + сл + "%")).fetchone()[0]
    print("  писем со словом «%s»: %d" % (сл, k))
д = c.execute("SELECT COUNT(*) FROM (SELECT email FROM confirm_reviews"
              " WHERE campaign_id=13 GROUP BY email HAVING COUNT(*)>1)").fetchone()[0]
print("  повторов адреса: %d" % д)
ди = c.execute("SELECT COUNT(*) FROM (SELECT inn FROM confirm_reviews"
               " WHERE campaign_id=13 AND inn<>'' GROUP BY inn"
               " HAVING COUNT(*)>1)").fetchone()[0]
print("  повторов компании: %d" % ди)
пис = c.execute("SELECT COUNT(*) FROM confirm_reviews cr WHERE cr.campaign_id=13"
                " AND EXISTS (SELECT 1 FROM messages m JOIN recipients r"
                " ON r.id=m.recipient_id WHERE m.status='sent'"
                " AND LOWER(r.email)=LOWER(cr.email))").fetchone()[0]
print("  адресов, которым мы уже писали раньше: %d (должно быть 0)" % пис)

print("\n=== ОДНО ПИСЬМО ЦЕЛИКОМ ===")
об = c.execute("SELECT email, subject, body FROM confirm_reviews WHERE campaign_id=13"
               " LIMIT 1").fetchone()
print("  кому: %s" % об["email"])
print("  тема: %s" % об["subject"])
print("  ---")
print("  " + "\n  ".join(str(об["body"]).splitlines()))
